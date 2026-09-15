"""QICK program that clocks and counts one confocal raster line."""

from __future__ import annotations

import numpy as np

try:
    from qickdawg.nvpulsing.nvaverageprogram import NVAveragerProgram
except ImportError:  # Allows geometry/config tests without the hardware package.
    class NVAveragerProgram:  # type: ignore
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("QICK-DAWG is required to compile ConfocalLine")


class ConfocalLine(NVAveragerProgram):
    """Advance NI AO once per pixel and edge-count K windows per pixel.

    ``cfg.reps`` is the number of imaging pixels.  Flyback clocks are emitted
    after the repetitions loop by :meth:`end`, and therefore create no ADC
    readouts.
    """

    required_cfg = [
        "adc_channel",
        "laser_gate_pmod",
        "pixel_clock_pmod",
        "pixel_clock_width_treg",
        "pixel_settle_treg",
        "readout_integration_treg",
        "readout_window_tproc_treg",
        "windows_per_pixel",
        "n_flyback",
        "flyback_period_treg",
        "relax_delay_treg",
        "reps",
    ]

    def initialize(self):
        self.check_cfg()
        if self.cfg.windows_per_pixel < 1:
            raise ValueError("windows_per_pixel must be positive")
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
            + int(self.cfg.windows_per_pixel)
            * int(self.cfg.readout_window_tproc_treg)
            + int(self.cfg.relax_delay_treg)
        )

    def _clock_pulse(self, t=0):
        self._masked_state(clock=True, t=t)
        self._masked_state(clock=False, t=t + self.cfg.pixel_clock_width_treg)

    def body(self):
        self._clock_pulse(0)
        t = int(self.cfg.pixel_settle_treg)
        window = int(self.cfg.readout_window_tproc_treg)
        for _ in range(int(self.cfg.windows_per_pixel)):
            self._masked_state(adc=True, t=t)
            self._masked_state(t=t + window)
            t += window
        self.wait_all()
        self.sync_all(int(self.cfg.relax_delay_treg))

    def end(self):
        # NVAveragerProgram.make_program calls end() after its reps loop.
        # Generate DAQ movement samples only: no readout triggers during flyback.
        period = max(1, int(self.cfg.flyback_period_treg))
        for _ in range(int(self.cfg.n_flyback)):
            self._clock_pulse(0)
            self.synci(period)
        # Explicitly clear the full PMOD word before stopping the tProc.
        self.trigger(pins=[self.cfg.laser_gate_pmod], width=1, adc_trig_offset=0)
        self.synci(2)
        self.append_instruction("end")

    def acquire(self, *args, **kwargs):
        raw = super().acquire(
            readouts_per_experiment=int(self.cfg.windows_per_pixel),
            *args,
            **kwargs,
        )
        data = np.asarray(raw, dtype=np.int64).reshape(
            int(self.cfg.reps), int(self.cfg.windows_per_pixel)
        )
        return data.sum(axis=-1)
