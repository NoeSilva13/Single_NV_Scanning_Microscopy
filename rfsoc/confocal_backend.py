"""Host coordination for RFSoC-timed NI analog-output lines."""

from __future__ import annotations

from dataclasses import dataclass, field
import threading
from typing import Callable

import numpy as np

from common import utils
from .config import base_nv_config, readout_clock_hz, readout_plan
from .confocal_line import ConfocalLine


def analog_write_buffer(data):
    """Copy *data* into the C-contiguous layout nidaqmx.Task.write requires.

    Raster lines are column slices of ``(n_channels, N)`` and are not
    C-contiguous. A 1-channel array is flattened to 1-D, matching the
    nidaqmx convention used by :meth:`RFSoCConfocalBackend.acquire_line`.
    """
    data = np.asarray(data, dtype=np.float64)
    if data.ndim == 1:
        return np.ascontiguousarray(data)
    write_data = data[0] if data.shape[0] == 1 else data
    return np.ascontiguousarray(write_data)


def iter_raster_lines(waveform, width, n_lines, stride, n_flyback):
    """Yield ``(line_index, line_waveform, n_flyback)`` for one raster.

    The last host line has no trailing flyback samples in *waveform*.  Those
    samples are padded with the final imaging position so every line uses the
    same QICK program and NI sample count.
    """
    waveform = np.asarray(waveform, dtype=float)
    if waveform.ndim == 1:
        waveform = waveform[np.newaxis, :]
    width = int(width)
    n_flyback = int(n_flyback)
    for line_index in range(int(n_lines)):
        source_start = line_index * int(stride)
        trailing = n_flyback if line_index < n_lines - 1 else 0
        source_stop = source_start + width + trailing
        line = waveform[:, source_start:source_stop]
        if n_flyback and line.shape[1] == width:
            line = np.concatenate(
                [line, np.repeat(line[:, -1:], n_flyback, axis=1)],
                axis=1,
            )
        yield line_index, line, n_flyback


def should_publish_scan_progress(line_index, n_lines, every=utils.SCAN_PREVIEW_EVERY_LINES):
    """Return True for the first line, every *every* lines, and the last line."""
    n_done = int(line_index) + 1
    n_lines = int(n_lines)
    every = max(1, int(every))
    return n_done == 1 or n_done == n_lines or n_done % every == 0


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

    def _program_config(
        self, width, dwell_seconds, n_flyback, flyback_seconds=None
    ):
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
        n_flyback = int(n_flyback)
        cfg.n_flyback = n_flyback
        if n_flyback > 0:
            total = (
                float(flyback_seconds)
                if flyback_seconds is not None
                else utils.RFSOC_GALVO_FLYBACK_S
            )
            period_s = max(
                total / n_flyback,
                utils.RFSOC_CONFOCAL_SETTLE_US * 1e-6,
            )
            cfg.flyback_period_treg = max(1, int(round(period_s * tproc_hz)))
        else:
            cfg.flyback_period_treg = 1
        return cfg, plan

    def _line_timeout(self, plan, n_imaging, cfg):
        imaging = int(n_imaging) * (
            plan.effective_seconds + utils.RFSOC_CONFOCAL_SETTLE_US * 1e-6
        )
        tproc_hz = float(self.session.soccfg["tprocs"][0]["f_time"]) * 1e6
        flyback = int(cfg.n_flyback) * (int(cfg.flyback_period_treg) / tproc_hz)
        return max(10.0, 2.0 * (imaging + flyback))

    def _open_ao_task(self, ao_channels, expected, plan):
        import nidaqmx
        from nidaqmx.constants import AcquisitionType, Edge

        task = nidaqmx.Task()
        for channel in ao_channels:
            task.ao_channels.add_ao_voltage_chan(channel)
        nominal_rate = 1.0 / (
            plan.effective_seconds + utils.RFSOC_CONFOCAL_SETTLE_US * 1e-6
        )
        task.timing.cfg_samp_clk_timing(
            rate=nominal_rate,
            source=utils.DAQ_RFSOC_CLOCK_INPUT,
            active_edge=Edge.RISING,
            sample_mode=AcquisitionType.FINITE,
            samps_per_chan=int(expected),
        )
        try:
            from nidaqmx.constants import RegenerationMode

            task.out_stream.regen_mode = RegenerationMode.DONT_ALLOW_REGENERATION
        except Exception:
            pass
        return task

    @staticmethod
    def _close_ao_task(task):
        if task is None:
            return
        try:
            task.stop()
        except Exception:
            pass
        task.close()

    def _clock_and_count(self, task, program, data, timeout):
        write_data = analog_write_buffer(data)
        task.write(write_data, auto_start=False)
        task.start()
        counts = np.asarray(program.acquire(progress=False), dtype=np.int64)
        task.wait_until_done(timeout=timeout)
        try:
            task.stop()
        except Exception:
            pass
        return counts

    def acquire_line(
        self,
        ao_channels,
        waveform,
        dwell_seconds,
        *,
        n_imaging_points,
        n_flyback=0,
        flyback_seconds=None,
        handle: AcquisitionHandle | None = None,
    ):
        """Arm one NI line, then let one QICK acquire clock and count it."""
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
                int(n_imaging_points),
                dwell_seconds,
                int(n_flyback),
                flyback_seconds=flyback_seconds,
            )
            program = ConfocalLine(cfg)
            task = self._open_ao_task(ao_channels, expected, plan)
            handle.task = task
            try:
                counts = self._clock_and_count(
                    task, program, data, self._line_timeout(plan, n_imaging_points, cfg)
                )
            finally:
                handle.task = None
                self._close_ao_task(task)

        return self._pack_line_result(counts, n_imaging_points, plan)

    def acquire_raster(
        self,
        ao_channels,
        waveform,
        dwell_seconds,
        *,
        width,
        n_lines,
        stride,
        n_flyback,
        flyback_seconds=None,
        handle: AcquisitionHandle | None = None,
        on_line: Callable | None = None,
        stop_check: Callable[[], bool] | None = None,
    ):
        """Acquire every raster line with one compiled program and one NI task."""
        handle = handle or AcquisitionHandle()
        width = int(width)
        n_flyback = int(n_flyback)
        expected = width + n_flyback
        counts = np.zeros(int(n_lines) * width, dtype=np.int64)
        widths = np.zeros(int(n_lines) * width, dtype=np.int64)

        with self.session.acquisition():
            cfg, plan = self._program_config(
                width, dwell_seconds, n_flyback, flyback_seconds=flyback_seconds
            )
            program = ConfocalLine(cfg)
            task = self._open_ao_task(ao_channels, expected, plan)
            handle.task = task
            timeout = self._line_timeout(plan, width, cfg)
            widths_ps = int(round(plan.effective_seconds * 1e12))
            try:
                for line_index, line_waveform, flyback in iter_raster_lines(
                    waveform, width, n_lines, stride, n_flyback
                ):
                    if handle.stop_event.is_set() or (stop_check and stop_check()):
                        raise InterruptedError("scan stopped")
                    if line_waveform.shape != (len(ao_channels), expected):
                        raise ValueError(
                            f"line waveform shape {line_waveform.shape}, expected "
                            f"({len(ao_channels)}, {expected})"
                        )
                    line_counts = self._clock_and_count(
                        task, program, line_waveform, timeout
                    )
                    if line_counts.shape != (width,):
                        raise RuntimeError(
                            f"RFSoC returned {line_counts.shape}, expected ({width},)"
                        )
                    dest = slice(line_index * width, (line_index + 1) * width)
                    counts[dest] = line_counts
                    widths[dest] = widths_ps
                    if on_line:
                        on_line(counts.copy(), widths.copy())
            finally:
                handle.task = None
                self._close_ao_task(task)
        return counts, widths

    @staticmethod
    def _pack_line_result(counts, n_imaging_points, plan):
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
    flyback_seconds=None,
    on_line: Callable | None = None,
    stop_check: Callable[[], bool] | None = None,
    handle: AcquisitionHandle | None = None,
):
    """Acquire a flattened raster waveform one line at a time."""
    handle = handle or AcquisitionHandle()
    acquire_raster = getattr(backend, "acquire_raster", None)
    if acquire_raster is not None:
        return acquire_raster(
            ao_channels,
            waveform,
            dwell_seconds,
            width=width,
            n_lines=n_lines,
            stride=stride,
            n_flyback=n_flyback,
            flyback_seconds=flyback_seconds,
            handle=handle,
            on_line=on_line,
            stop_check=stop_check,
        )

    counts = np.zeros(int(n_lines) * int(width), dtype=np.int64)
    widths = np.zeros(int(n_lines) * int(width), dtype=np.int64)
    for line_index, line_waveform, flyback in iter_raster_lines(
        waveform, width, n_lines, stride, n_flyback
    ):
        if handle.stop_event.is_set() or (stop_check and stop_check()):
            raise InterruptedError("scan stopped")
        line_counts, line_widths = backend.acquire_line(
            ao_channels,
            line_waveform,
            dwell_seconds,
            n_imaging_points=width,
            n_flyback=flyback,
            flyback_seconds=flyback_seconds,
            handle=handle,
        )
        dest = slice(line_index * width, (line_index + 1) * width)
        counts[dest] = line_counts
        widths[dest] = line_widths
        if on_line:
            on_line(counts.copy(), widths.copy())
    return counts, widths
