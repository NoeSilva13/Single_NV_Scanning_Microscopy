"""QICK program that clocks and counts a whole block of raster lines."""

from __future__ import annotations

from .confocal_line import ConfocalLine


class ConfocalFrame(ConfocalLine):
    """Nest the pixel loop inside a line loop so one acquire covers many lines.

    ``cfg.reps`` is the number of imaging pixels per line and ``cfg.n_lines``
    the number of lines in this acquire.  Retrace clocks are emitted before the
    first line (``cfg.n_lead``) and after every line (``cfg.n_flyback``); none
    of them trigger the ADC, so the accumulated buffer holds exactly
    ``n_lines * reps`` readouts in raster order.

    The shot counter is incremented inside the pixel loop, which is what QICK's
    data streamer uses to address the buffer, so it stays in step with the
    readouts rather than with the lines.
    """

    required_cfg = ConfocalLine.required_cfg + ["n_lines", "n_lead"]

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
