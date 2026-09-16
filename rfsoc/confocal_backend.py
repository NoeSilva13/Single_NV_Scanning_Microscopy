"""Host coordination for RFSoC-timed NI analog-output rasters."""

from __future__ import annotations

from dataclasses import dataclass, field
import threading
from typing import Callable

import numpy as np

from common import utils
from .config import base_nv_config, readout_clock_hz, readout_plan
from .confocal_frame import ConfocalFrame, stream_counts


def analog_write_buffer(data):
    """Copy *data* into the C-contiguous layout nidaqmx.Task.write requires.

    Raster lines are column slices of ``(n_channels, N)`` and are not
    C-contiguous. A 1-channel array is flattened to 1-D, matching the
    nidaqmx convention used by :meth:`RFSoCConfocalBackend.acquire_frame`.
    """
    data = np.asarray(data, dtype=np.float64)
    if data.ndim == 1:
        return np.ascontiguousarray(data)
    write_data = data[0] if data.shape[0] == 1 else data
    return np.ascontiguousarray(write_data)


def raster_line(waveform, width, n_lines, stride, n_flyback, line_index):
    """Return one ``width + n_flyback`` sample line of a flattened raster.

    The last host line has no trailing flyback samples in *waveform*.  Those
    samples are padded with the final imaging position so every line clocks the
    same number of AO updates.
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


def frame_waveform(waveform, width, n_lines, stride, n_flyback):
    """Concatenate every flyback-padded line into the AO block of one frame."""
    lines = [
        raster_line(waveform, width, n_lines, stride, n_flyback, line_index)
        for line_index in range(int(n_lines))
    ]
    return np.concatenate(lines, axis=1)


def lead_in_waveform(parked, target, n_lead):
    """Ramp the AO from its parked position to the first pixel of the frame.

    The NI task starts at the first pixel, which can be a full-field jump away
    from wherever the galvo was left.  These samples are clocked before the
    first ADC window, so the jump gets the same retrace budget as a line
    flyback rather than smearing the first pixels of the image.
    """
    n_lead = int(n_lead)
    parked = np.asarray(parked, dtype=float).reshape(-1, 1)
    target = np.asarray(target, dtype=float).reshape(-1, 1)
    if n_lead < 1:
        return np.zeros((parked.shape[0], 0), dtype=float)
    steps = np.linspace(0.0, 1.0, n_lead + 1)[1:]
    return parked + (target - parked) * steps


def stream_stride(width, pixel_seconds, update_seconds=None):
    """Pixels the board counts between handing data back to the host.

    Capped at one raster line so the image advances line by line, and down to
    single pixels once one pixel already outlasts an update interval.
    """
    if update_seconds is None:
        update_seconds = utils.RFSOC_STREAM_UPDATE_SECONDS
    width = max(1, int(width))
    pixel_seconds = float(pixel_seconds)
    if pixel_seconds <= 0:
        return width
    pixels = round(float(update_seconds) / pixel_seconds)
    return int(min(width, max(1, pixels)))


@dataclass
class AcquisitionHandle:
    stop_event: threading.Event = field(default_factory=threading.Event)
    task: object | None = None

    def stop(self):
        # Checked after every readout stride, so the tProc is stopped within a
        # line (a pixel at long dwells) instead of at the end of the frame.
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
        cfg.readout_integration_treg = plan.samples
        cfg.pixel_clock_pmod = utils.RFSOC_PIXEL_CLOCK_PMOD
        cfg.pixel_clock_width_tns = utils.RFSOC_PIXEL_CLOCK_WIDTH_NS
        cfg.pixel_settle_tus = utils.RFSOC_CONFOCAL_SETTLE_US
        cfg.relax_delay_treg = 1
        tproc_hz = float(self.session.soccfg["tprocs"][0]["f_time"]) * 1e6
        cfg.readout_window_tproc_treg = max(1, int(round(plan.seconds * tproc_hz)))
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

    def _pixel_seconds(self, plan):
        return plan.seconds + utils.RFSOC_CONFOCAL_SETTLE_US * 1e-6

    def _frame_timeout(self, plan, cfg):
        """Wall time the frame cannot legitimately exceed, for the NI wait."""
        imaging = (
            int(cfg.n_lines) * int(cfg.reps) * self._pixel_seconds(plan)
        )
        tproc_hz = float(self.session.soccfg["tprocs"][0]["f_time"]) * 1e6
        retrace = (int(cfg.n_flyback) * int(cfg.n_lines) + int(cfg.n_lead)) * (
            int(cfg.flyback_period_treg) / tproc_hz
        )
        return max(10.0, 2.0 * (imaging + retrace))

    def _open_ao_task(self, ao_channels, expected, plan):
        import nidaqmx
        from nidaqmx.constants import AcquisitionType, Edge

        task = nidaqmx.Task()
        for channel in ao_channels:
            task.ao_channels.add_ao_voltage_chan(channel)
        task.timing.cfg_samp_clk_timing(
            rate=1.0 / self._pixel_seconds(plan),
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
        """Acquire a whole raster with one QICK program and one NI task.

        Every pixel integrates its entire dwell in a single ADC window, and the
        counts come back in strides while the tProc keeps running, so *on_line*
        is called with the image as it fills rather than once at the end.  Its
        ``widths`` argument is zero wherever a pixel has not been counted yet.
        """
        handle = handle or AcquisitionHandle()
        width = int(width)
        n_lines = int(n_lines)
        n_flyback = int(n_flyback)
        n_lead = max(1, n_flyback)

        def stopped():
            return handle.stop_event.is_set() or bool(stop_check and stop_check())

        if stopped():
            raise InterruptedError("scan stopped before the frame was armed")

        counts = np.zeros(n_lines * width, dtype=np.int64)
        widths = np.zeros(n_lines * width, dtype=np.int64)

        with self.session.acquisition():
            cfg, plan = self._program_config(
                width,
                dwell_seconds,
                n_flyback,
                flyback_seconds=flyback_seconds,
                n_lines=n_lines,
                n_lead=n_lead,
            )
            program = ConfocalFrame(cfg)
            frame = frame_waveform(waveform, width, n_lines, stride, n_flyback)
            parked = np.asarray(waveform, dtype=float)
            if parked.ndim == 1:
                parked = parked[np.newaxis, :]
            data = np.concatenate(
                [lead_in_waveform(parked[:, :1], frame[:, :1], n_lead), frame],
                axis=1,
            )
            if data.shape[0] != len(ao_channels):
                raise ValueError(
                    f"raster waveform has {data.shape[0]} channels, expected "
                    f"{len(ao_channels)}"
                )
            write_data = analog_write_buffer(data)
            pixel_seconds = self._pixel_seconds(plan)
            readout_stride = stream_stride(width, pixel_seconds)
            dwell_ps = int(round(plan.seconds * 1e12))
            timeout = self._frame_timeout(plan, cfg)
            task = self._open_ao_task(ao_channels, data.shape[1], plan)
            handle.task = task

            def arm_analog_output():
                # The streamer starts the tProc, so the AO task has to be
                # running before the readout job is queued: the first pixel
                # clock arrives within microseconds of that.
                task.write(write_data, auto_start=False)
                task.start()

            try:
                for frame_counts, filled in stream_counts(
                    program,
                    self.session.soc,
                    stride=readout_stride,
                    poll_timeout=max(10.0, 3.0 * readout_stride * pixel_seconds),
                    on_armed=arm_analog_output,
                    stop_check=stopped,
                ):
                    counts[:filled] = frame_counts[:filled]
                    widths[:filled] = dwell_ps
                    if on_line:
                        on_line(counts.copy(), widths.copy())
                task.wait_until_done(timeout=timeout)
            finally:
                handle.task = None
                self._close_ao_task(task)

        return counts, widths

    def acquire_line(
        self,
        ao_channels,
        waveform,
        dwell_seconds,
        *,
        n_imaging_points,
        handle: AcquisitionHandle | None = None,
        on_progress: Callable | None = None,
        stop_check: Callable[[], bool] | None = None,
    ):
        """Acquire one hardware-timed sweep as a raster of a single line."""
        data = np.asarray(waveform, dtype=float)
        if data.ndim == 1:
            data = data[np.newaxis, :]
        n_points = int(n_imaging_points)
        if data.shape != (len(ao_channels), n_points):
            raise ValueError(
                f"line waveform shape {data.shape}, expected "
                f"({len(ao_channels)}, {n_points})"
            )
        return self.acquire_frame(
            ao_channels,
            data,
            dwell_seconds,
            width=n_points,
            n_lines=1,
            stride=n_points,
            n_flyback=0,
            handle=handle,
            on_line=on_progress,
            stop_check=stop_check,
        )

    def live_count_rate(self, integration_seconds=0.2):
        """Acquire a free-running PL point unless another RFSoC job is active."""
        if self.session.busy:
            return None, False
        with self.session.acquisition(blocking=False):
            qd = self.session.qd
            cfg = base_nv_config(self.session)
            clock = readout_clock_hz(self.session.soccfg, cfg.adc_channel)
            plan = readout_plan(integration_seconds, clock)
            cfg.readout_integration_treg = plan.samples
            cfg.relax_delay_treg = 1
            counts = int(qd.PLIntensity(cfg).acquire(progress=False))
            return counts / plan.seconds, False
