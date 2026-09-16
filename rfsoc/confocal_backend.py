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


def raster_line(waveform, width, n_lines, stride, n_flyback, line_index):
    """Return one ``width + n_flyback`` sample line of a flattened raster.

    The last host line has no trailing flyback samples in *waveform*.  Those
    samples are padded with the final imaging position so every line uses the
    same QICK program and NI sample count.
    """
    waveform = np.asarray(waveform, dtype=float)
    if waveform.ndim == 1:
        waveform = waveform[np.newaxis, :]
    width = int(width)
    n_flyback = int(n_flyback)
    source_start = int(line_index) * int(stride)
    trailing = n_flyback if int(line_index) < int(n_lines) - 1 else 0
    line = waveform[:, source_start:source_start + width + trailing]
    if n_flyback and line.shape[1] == width:
        line = np.concatenate(
            [line, np.repeat(line[:, -1:], n_flyback, axis=1)], axis=1
        )
    return line


def iter_raster_lines(waveform, width, n_lines, stride, n_flyback):
    """Yield ``(line_index, line_waveform, n_flyback)`` for one raster."""
    for line_index in range(int(n_lines)):
        line = raster_line(
            waveform, width, n_lines, stride, n_flyback, line_index
        )
        yield line_index, line, int(n_flyback)


def lines_per_block(
    width, n_flyback, window_seconds, flyback_seconds=None, budget_seconds=None
):
    """How many lines to put in one acquire to spend about *budget_seconds*.

    Larger blocks amortise the fixed cost of an acquire over more pixels;
    smaller blocks keep the napari preview and the stop request responsive.
    """
    if budget_seconds is None:
        budget_seconds = utils.RFSOC_FRAME_BLOCK_SECONDS
    pixel = float(window_seconds) + utils.RFSOC_CONFOCAL_SETTLE_US * 1e-6
    retrace = (
        float(flyback_seconds)
        if flyback_seconds is not None
        else utils.RFSOC_GALVO_FLYBACK_S
    )
    line = int(width) * pixel + (retrace if int(n_flyback) > 0 else 0.0)
    if line <= 0:
        return 1
    return max(1, int(float(budget_seconds) // line))


def iter_frame_blocks(n_lines, block_lines):
    """Yield ``(first_line, n_block_lines)`` acquires covering the raster."""
    n_lines = int(n_lines)
    block_lines = max(1, int(block_lines))
    if n_lines < 1:
        raise ValueError("n_lines must be positive")
    for first in range(0, n_lines, block_lines):
        yield first, min(block_lines, n_lines - first)


def block_waveform(
    waveform, width, n_lines, stride, n_flyback, first_line, block_lines
):
    """Concatenate the flyback-padded lines of one acquisition block."""
    lines = [
        raster_line(waveform, width, n_lines, stride, n_flyback, line_index)
        for line_index in range(int(first_line), int(first_line) + int(block_lines))
    ]
    return np.concatenate(lines, axis=1)


def lead_in_waveform(parked, target, n_lead):
    """Ramp the AO from its parked position to the first pixel of a block.

    Every pass and every block starts the NI task at the first pixel of its
    first line, which can be a full-field jump away from where the previous
    task left the galvo.  These samples are clocked before the first ADC
    window, so the jump gets the same retrace budget as a line flyback.
    """
    n_lead = int(n_lead)
    parked = np.asarray(parked, dtype=float).reshape(-1, 1)
    target = np.asarray(target, dtype=float).reshape(-1, 1)
    if n_lead < 1:
        return np.zeros((parked.shape[0], 0), dtype=float)
    steps = np.linspace(0.0, 1.0, n_lead + 1)[1:]
    return parked + (target - parked) * steps


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
        self,
        width,
        dwell_seconds,
        n_flyback,
        flyback_seconds=None,
        n_lines=1,
        n_lead=0,
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
        cfg.n_lines = int(n_lines)
        cfg.n_lead = int(n_lead)
        n_retrace = max(n_flyback, cfg.n_lead)
        if n_retrace > 0:
            total = (
                float(flyback_seconds)
                if flyback_seconds is not None
                else utils.RFSOC_GALVO_FLYBACK_S
            )
            period_s = max(
                total / n_retrace,
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
        retrace = (int(cfg.n_flyback) * int(cfg.n_lines) + int(cfg.n_lead)) * (
            int(cfg.flyback_period_treg) / tproc_hz
        )
        return max(10.0, 2.0 * (int(cfg.n_lines) * imaging + retrace))

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

    def _compile_line_program(
        self, n_imaging, n_flyback, window_seconds, flyback_seconds=None
    ):
        """Compile the single ConfocalLine that clocks one whole host line."""
        cfg, plan = self._program_config(
            int(n_imaging),
            window_seconds,
            int(n_flyback),
            flyback_seconds=flyback_seconds,
        )
        return ConfocalLine(cfg), plan, cfg

    def _clock_and_count(self, task, program, data, timeout):
        """Arm NI, run the tProc, and return the counts it accumulated.

        The NI task must be written and started before the program runs: the
        first pixel clock arrives within microseconds of the tProc starting.
        """
        write_data = analog_write_buffer(data)
        task.write(write_data, auto_start=False)
        task.start()
        counts = np.array(
            program.acquire(progress=False), dtype=np.int64, copy=True
        )
        task.wait_until_done(timeout=timeout)
        try:
            task.stop()
        except Exception:
            pass
        return counts

    def _sum_window_passes(self, task, program, data, timeout, n_windows, n_pixels):
        """Retrace the line once per ADC window and sum the counts."""
        n_windows = int(n_windows)
        total = np.zeros(int(n_pixels), dtype=np.int64)
        for _ in range(n_windows):
            total += self._clock_and_count(task, program, data, timeout)
        return total

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
        """Arm NI, then retrace the line once per ADC window and sum counts."""
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
            _, dwell_plan = self._program_config(
                int(n_imaging_points),
                dwell_seconds,
                int(n_flyback),
                flyback_seconds=flyback_seconds,
            )
            program, window_plan, cfg = self._compile_line_program(
                int(n_imaging_points),
                int(n_flyback),
                dwell_plan.window_seconds,
                flyback_seconds=flyback_seconds,
            )
            task = self._open_ao_task(ao_channels, expected, window_plan)
            handle.task = task
            try:
                counts = self._sum_window_passes(
                    task,
                    program,
                    data,
                    self._line_timeout(window_plan, n_imaging_points, cfg),
                    dwell_plan.windows_per_pixel,
                    n_imaging_points,
                )
            finally:
                handle.task = None
                self._close_ao_task(task)

        return self._pack_line_result(counts, n_imaging_points, dwell_plan)

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
        """Acquire every raster line by summing one-window retraces."""
        handle = handle or AcquisitionHandle()
        width = int(width)
        n_flyback = int(n_flyback)
        expected = width + n_flyback
        counts = np.zeros(int(n_lines) * width, dtype=np.int64)
        widths = np.zeros(int(n_lines) * width, dtype=np.int64)

        with self.session.acquisition():
            _, dwell_plan = self._program_config(
                width, dwell_seconds, n_flyback, flyback_seconds=flyback_seconds
            )
            program, window_plan, cfg = self._compile_line_program(
                width,
                n_flyback,
                dwell_plan.window_seconds,
                flyback_seconds=flyback_seconds,
            )
            task = self._open_ao_task(ao_channels, expected, window_plan)
            handle.task = task
            timeout = self._line_timeout(window_plan, width, cfg)
            widths_ps = int(round(dwell_plan.effective_seconds * 1e12))
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
                    line_counts = self._sum_window_passes(
                        task,
                        program,
                        line_waveform,
                        timeout,
                        dwell_plan.windows_per_pixel,
                        width,
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

    def acquire_frame(
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
        """Acquire the raster as line blocks, one acquire per ADC-window pass.

        A dwell within ``RFSOC_MAX_COUNTING_WINDOW_S`` is one window, so each
        block is a single acquire and every pixel integrates its whole dwell in
        one go.  A longer dwell falls back to several passes over the block;
        counts and integrated widths then accumulate across passes, which keeps
        the reconstructed rate correct while the image is still filling in.
        """
        from .confocal_frame import ConfocalFrame

        handle = handle or AcquisitionHandle()
        width = int(width)
        n_lines = int(n_lines)
        n_flyback = int(n_flyback)
        n_lead = max(1, n_flyback)
        counts = np.zeros(n_lines * width, dtype=np.int64)
        widths = np.zeros(n_lines * width, dtype=np.int64)

        def stopped():
            return handle.stop_event.is_set() or bool(stop_check and stop_check())

        with self.session.acquisition():
            _, dwell_plan = self._program_config(
                width, dwell_seconds, n_flyback, flyback_seconds=flyback_seconds
            )
            n_passes = int(dwell_plan.windows_per_pixel)
            window_ps = int(round(dwell_plan.window_seconds * 1e12))
            block_lines = lines_per_block(
                width, n_flyback, dwell_plan.window_seconds, flyback_seconds
            )
            parked = np.asarray(waveform, dtype=float)
            if parked.ndim == 1:
                parked = parked[np.newaxis, :]
            parked = parked[:, :1]
            programs = {}

            for first, n_block in iter_frame_blocks(n_lines, block_lines):
                block = block_waveform(
                    waveform, width, n_lines, stride, n_flyback, first, n_block
                )
                key = (n_block, n_lead)
                if key not in programs:
                    cfg, window_plan = self._program_config(
                        width,
                        dwell_plan.window_seconds,
                        n_flyback,
                        flyback_seconds=flyback_seconds,
                        n_lines=n_block,
                        n_lead=n_lead,
                    )
                    programs[key] = (ConfocalFrame(cfg), cfg, window_plan)
                program, cfg, window_plan = programs[key]
                data = np.concatenate(
                    [lead_in_waveform(parked, block[:, :1], n_lead), block], axis=1
                )
                if data.shape[0] != len(ao_channels):
                    raise ValueError(
                        f"block waveform has {data.shape[0]} channels, expected "
                        f"{len(ao_channels)}"
                    )
                task = self._open_ao_task(ao_channels, data.shape[1], window_plan)
                handle.task = task
                timeout = self._line_timeout(window_plan, width, cfg)
                dest = slice(first * width, (first + n_block) * width)
                try:
                    for _ in range(n_passes):
                        if stopped():
                            raise InterruptedError("scan stopped")
                        block_counts = self._clock_and_count(
                            task, program, data, timeout
                        )
                        if block_counts.shape != (n_block * width,):
                            raise RuntimeError(
                                f"RFSoC returned {block_counts.shape}, expected "
                                f"({n_block * width},)"
                            )
                        counts[dest] += block_counts
                        widths[dest] += window_ps
                        if on_line:
                            on_line(counts.copy(), widths.copy())
                finally:
                    handle.task = None
                    self._close_ao_task(task)
                parked = data[:, -1:]

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
    """Acquire a flattened raster waveform, preferring the fewest acquires."""
    handle = handle or AcquisitionHandle()
    acquire_frame = getattr(backend, "acquire_frame", None)
    if utils.RFSOC_FRAME_ACQUIRE and acquire_frame is not None:
        return acquire_frame(
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
