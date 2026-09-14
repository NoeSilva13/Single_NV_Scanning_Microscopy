"""Host coordination for RFSoC-timed NI analog-output lines."""

from __future__ import annotations

from dataclasses import dataclass, field
import threading
from typing import Callable

import numpy as np

from common import utils
from .config import base_nv_config, readout_clock_hz, readout_plan
from .confocal_line import ConfocalLine


@dataclass
class AcquisitionHandle:
    stop_event: threading.Event = field(default_factory=threading.Event)
    task: object | None = None

    def stop(self):
        # QICK 0.2.302 cannot safely abort poll_data().  Stop is cooperative:
        # finish the current line, then prevent the next line from being armed.
        self.stop_event.set()


class RFSoCConfocalBackend:
    def __init__(self, session):
        self.session = session

    def _program_config(self, width, dwell_seconds, n_flyback):
        cfg = base_nv_config(self.session, reps=width)
        ro_clock = readout_clock_hz(self.session.soccfg, cfg.adc_channel)
        plan = readout_plan(dwell_seconds, ro_clock)
        cfg.readout_integration_treg = plan.samples_per_window
        cfg.windows_per_pixel = plan.windows_per_pixel
        cfg.pixel_clock_pmod = utils.RFSOC_PIXEL_CLOCK_PMOD
        cfg.pixel_clock_width_tns = utils.RFSOC_PIXEL_CLOCK_WIDTH_NS
        cfg.pixel_settle_tus = utils.RFSOC_CONFOCAL_SETTLE_US
        cfg.relax_delay_treg = 1
        tproc_hz = float(self.session.soccfg["tprocs"][0]["f_time"]) * 1e6
        cfg.readout_window_tproc_treg = max(
            1, int(round(plan.window_seconds * tproc_hz))
        )
        cfg.n_flyback = int(n_flyback)
        return cfg, plan

    def acquire_line(
        self,
        ao_channels,
        waveform,
        dwell_seconds,
        *,
        n_imaging_points,
        n_flyback=0,
        handle: AcquisitionHandle | None = None,
    ):
        """Arm one NI line, then let one QICK acquire clock and count it."""
        import nidaqmx
        from nidaqmx.constants import AcquisitionType, Edge

        data = np.asarray(waveform, dtype=float)
        if data.ndim == 1:
            data = data[np.newaxis, :]
        expected = int(n_imaging_points) + int(n_flyback)
        if data.shape != (len(ao_channels), expected):
            raise ValueError(
                f"line waveform shape {data.shape}, expected "
                f"({len(ao_channels)}, {expected})"
            )
        handle = handle or AcquisitionHandle()
        if handle.stop_event.is_set():
            raise InterruptedError("scan stopped before line acquisition")

        with self.session.acquisition():
            cfg, plan = self._program_config(
                int(n_imaging_points), dwell_seconds, int(n_flyback)
            )
            program = ConfocalLine(cfg)
            task = nidaqmx.Task()
            handle.task = task
            try:
                for channel in ao_channels:
                    task.ao_channels.add_ao_voltage_chan(channel)
                nominal_rate = 1.0 / (
                    plan.effective_seconds
                    + utils.RFSOC_CONFOCAL_SETTLE_US * 1e-6
                )
                task.timing.cfg_samp_clk_timing(
                    rate=nominal_rate,
                    source=utils.DAQ_RFSOC_CLOCK_INPUT,
                    active_edge=Edge.RISING,
                    sample_mode=AcquisitionType.FINITE,
                    samps_per_chan=expected,
                )
                write_data = data[0] if data.shape[0] == 1 else data
                task.write(write_data, auto_start=False)
                task.start()  # Armed and waiting for RFSoC PMOD edges.
                counts = np.asarray(program.acquire(progress=False), dtype=np.int64)
                timeout = max(
                    10.0,
                    expected
                    * (plan.effective_seconds + utils.RFSOC_CONFOCAL_SETTLE_US * 1e-6)
                    * 2.0,
                )
                task.wait_until_done(timeout=timeout)
            finally:
                handle.task = None
                try:
                    task.stop()
                except Exception:
                    pass
                task.close()

        if counts.shape != (n_imaging_points,):
            raise RuntimeError(
                f"RFSoC returned {counts.shape}, expected ({n_imaging_points},)"
            )
        widths_ps = np.full(
            int(n_imaging_points),
            int(round(plan.effective_seconds * 1e12)),
            dtype=np.int64,
        )
        return counts, widths_ps

    def live_count_rate(self, integration_seconds=0.2):
        """Acquire a free-running PL point unless another RFSoC job is active."""
        if self.session.busy:
            return None, False
        with self.session.acquisition(blocking=False):
            qd = self.session.qd
            cfg = base_nv_config(self.session)
            clock = readout_clock_hz(self.session.soccfg, cfg.adc_channel)
            plan = readout_plan(integration_seconds, clock)
            cfg.readout_integration_treg = plan.samples_per_window
            cfg.relax_delay_treg = 1
            cfg.reps = plan.windows_per_pixel
            counts = int(qd.PLIntensity(cfg).acquire(progress=False))
            return counts / plan.effective_seconds, False


def run_lines(
    backend: RFSoCConfocalBackend,
    ao_channels,
    waveform,
    *,
    width,
    n_lines,
    stride,
    dwell_seconds,
    n_flyback,
    on_line: Callable | None = None,
    stop_check: Callable[[], bool] | None = None,
    handle: AcquisitionHandle | None = None,
):
    """Acquire a flattened raster waveform one line at a time."""
    waveform = np.asarray(waveform, dtype=float)
    counts = np.zeros(n_lines * width, dtype=np.int64)
    widths = np.zeros(n_lines * width, dtype=np.int64)
    handle = handle or AcquisitionHandle()
    for line_index in range(n_lines):
        if handle.stop_event.is_set() or (stop_check and stop_check()):
            raise InterruptedError("scan stopped")
        flyback = n_flyback if line_index < n_lines - 1 else 0
        source_start = line_index * stride
        source_stop = source_start + width + flyback
        line_waveform = waveform[:, source_start:source_stop]
        line_counts, line_widths = backend.acquire_line(
            ao_channels,
            line_waveform,
            dwell_seconds,
            n_imaging_points=width,
            n_flyback=flyback,
            handle=handle,
        )
        dest = slice(line_index * width, (line_index + 1) * width)
        counts[dest] = line_counts
        widths[dest] = line_widths
        if on_line:
            on_line(counts.copy(), widths.copy())
    return counts, widths
