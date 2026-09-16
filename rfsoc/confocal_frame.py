"""QICK program that clocks and counts a whole confocal frame, plus its readout."""

from __future__ import annotations

import numpy as np

try:
    from qickdawg.nvpulsing.nvaverageprogram import NVAveragerProgram
except ImportError:  # Allows geometry/config tests without the hardware package.
    class NVAveragerProgram:  # type: ignore
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("QICK-DAWG is required to compile ConfocalFrame")

try:
    from rpyc.utils.classic import obtain
except ModuleNotFoundError:  # Same fallback QICK uses when the board is local.
    def obtain(value):
        return value


class ConfocalFrame(NVAveragerProgram):
    """Advance NI AO once per pixel and edge-count one ADC window per pixel.

    ``cfg.reps`` is the number of imaging pixels per line and ``cfg.n_lines``
    the number of lines in the frame.  Retrace clocks are emitted before the
    first line (``cfg.n_lead``) and after every line (``cfg.n_flyback``); none
    of them trigger the ADC, so the accumulated buffer holds exactly
    ``n_lines * reps`` readouts in raster order.

    The shot counter is incremented inside the pixel loop.  QICK's data streamer
    reads that counter both to address the buffer and to decide when a stride of
    measurements is ready, so incrementing it per pixel is what lets the host
    watch the image fill in.
    """

    required_cfg = [
        "adc_channel",
        "laser_gate_pmod",
        "pixel_clock_pmod",
        "pixel_clock_width_treg",
        "pixel_settle_treg",
        "readout_integration_treg",
        "readout_window_tproc_treg",
        "n_lines",
        "n_lead",
        "n_flyback",
        "flyback_period_treg",
        "relax_delay_treg",
        "reps",
    ]

    # Also defined by qickdawg.NVAveragerProgram; repeated so the program can be
    # built and inspected without the hardware package installed.
    COUNTER_ADDR = 1

    def __init__(self, cfg):
        super().__init__(cfg)
        # QICK-DAWG assumes loop_dims == [reps]; this program has two loops.
        self.setup_acquire(
            counter_addr=self.COUNTER_ADDR,
            loop_dims=[int(cfg.n_lines), int(cfg.reps)],
            avg_level=0,
        )

    @property
    def expected_readouts(self):
        return int(self.cfg.n_lines) * int(self.cfg.reps)

    def initialize(self):
        self.check_cfg()
        # The accumulated buffer is circular and the streamer drains it once per
        # stride, so the pixels per acquire are unbounded; only a host stall long
        # enough to lap the buffer loses data, and QICK raises on that.
        self.setup_readout()
        pin_cfg = self.soccfg["tprocs"][0]["output_pins"]
        ports = {
            pin_cfg[self.cfg.laser_gate_pmod][1],
            pin_cfg[self.cfg.pixel_clock_pmod][1],
            self.soccfg["readouts"][self.cfg.adc_channel]["trigger_port"],
        }
        if len(ports) != 1:
            raise ValueError(
                "AOM, pixel clock, and ADC trigger must share one tProc "
                "output port for glitch-free complete-mask writes"
            )
        self.synci(200)

    def _masked_state(self, *, adc=False, clock=False, t=0):
        pins = [self.cfg.laser_gate_pmod]
        if clock:
            pins.append(self.cfg.pixel_clock_pmod)
        self.trigger_no_off(
            adcs=[self.cfg.adc_channel] if adc else [],
            pins=pins,
            adc_trig_offset=0,
            t=int(t),
        )

    @property
    def pixel_period_treg(self):
        return (
            int(self.cfg.pixel_settle_treg)
            + int(self.cfg.readout_window_tproc_treg)
            + int(self.cfg.relax_delay_treg)
        )

    def _clock_pulse(self, t=0):
        self._masked_state(clock=True, t=t)
        self._masked_state(clock=False, t=t + self.cfg.pixel_clock_width_treg)

    def body(self):
        self._clock_pulse(0)
        t = int(self.cfg.pixel_settle_treg)
        window = int(self.cfg.readout_window_tproc_treg)
        self._masked_state(adc=True, t=t)
        self._masked_state(t=t + window)
        self.wait_all()
        self.sync_all(int(self.cfg.relax_delay_treg))

    def _retrace(self, register, n_clocks, label):
        """Emit *n_clocks* pixel clocks without ADC triggers, as a register loop."""
        n_clocks = int(n_clocks)
        if n_clocks < 1:
            return
        period = max(1, int(self.cfg.flyback_period_treg))
        self.regwi(0, register, n_clocks - 1)
        self.label(label)
        self._clock_pulse(0)
        self.synci(period)
        self.loopnz(0, register, label)

    def make_program(self):
        # Registers 13/14 follow the QICK-DAWG convention; 16 is the output
        # word used by trigger_no_off, so the loop counters use 15 and 17.
        rcount, line_reg, pixel_reg, retrace_reg = 13, 14, 15, 17

        self.initialize()
        self.regwi(0, rcount, 0)
        self._retrace(retrace_reg, self.cfg.n_lead, "LOOP_lead")

        self.regwi(0, line_reg, int(self.cfg.n_lines) - 1)
        self.label("LOOP_line")
        self.regwi(0, pixel_reg, int(self.cfg.reps) - 1)
        self.label("LOOP_pixel")
        self.body()
        self.mathi(0, rcount, rcount, "+", 1)
        self.memwi(0, rcount, self.COUNTER_ADDR)
        self.loopnz(0, pixel_reg, "LOOP_pixel")
        self._retrace(retrace_reg, self.cfg.n_flyback, "LOOP_flyback")
        self.loopnz(0, line_reg, "LOOP_line")

        self.end()

    def end(self):
        # Retrace is emitted inside the line loop, so only clear the PMOD word.
        self.trigger(pins=[self.cfg.laser_gate_pmod], width=1, adc_trig_offset=0)
        self.synci(2)
        self.append_instruction("end")


def stream_counts(
    program,
    soc,
    *,
    stride,
    poll_timeout,
    on_armed=None,
    stop_check=None,
):
    """Run *program* and yield its edge counts as the board hands them over.

    This is ``NVAveragerProgram.acquire`` with the parts a scan needs: the
    counts arrive in strides instead of in one lump at the end, so the host can
    draw the image while the tProc keeps counting, and the loop can be abandoned
    mid-frame.  Yields ``(counts, n_filled)`` after every transfer, where
    *counts* is one array filled in place, in raster order.

    *on_armed* runs after the program is loaded and before the readout starts.
    The streamer is what calls ``start_tproc``, so that callback is the only
    place where an external clock consumer can be armed without either missing
    the first pixel clock or idling the tProc while the program uploads.
    """
    program.set_reads_per_shot(1)
    program.config_all(soc, load_mem=False)
    soc.start_src("internal")
    total = int(program.expected_readouts)
    counts = np.zeros(total, dtype=np.int64)

    program.config_bufs(soc, enable_avg=True, enable_buf=False)
    soc.reload_mem()
    if on_armed is not None:
        on_armed()

    filled = 0
    try:
        soc.start_readout(
            total,
            counter_addr=program.counter_addr,
            ch_list=list(program.ro_chs),
            reads_per_shot=program.reads_per_shot,
            stride=int(stride),
        )
        while filled < total:
            new_data = obtain(soc.poll_data(timeout=poll_timeout))
            if not new_data:
                raise RuntimeError(
                    f"RFSoC delivered no counts for {poll_timeout:.3g} s after "
                    f"{filled} of {total} pixels"
                )
            for new_points, (channel_data, _stats) in new_data:
                if filled + new_points > total:
                    raise RuntimeError(
                        f"RFSoC returned {filled + new_points} readouts, "
                        f"expected {total}"
                    )
                # Edge counts land in the I column of the accumulated buffer.
                counts[filled:filled + new_points] = np.asarray(
                    channel_data[0]
                )[:, 0]
                filled += new_points
            yield counts, filled
            if stop_check is not None and stop_check():
                raise InterruptedError("scan stopped")
    finally:
        if filled < total:
            # Leaves the streamer waiting on a counter that will never advance;
            # the next start_readout is what tears it down, as QICK intends.
            soc.stop_tproc()
