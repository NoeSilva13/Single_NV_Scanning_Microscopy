"""RFSoC-mastered photon counting with externally clocked NI analog output."""

import numpy as np

from rfsoc.confocal_backend import AcquisitionHandle, RFSoCConfocalBackend


def _register_ref(ref, value, lock):
    """Store *value* in the mutable single-element list *ref* under *lock*."""
    if ref is None:
        return
    if lock is not None:
        with lock:
            ref[0] = value
    else:
        ref[0] = value


def _clear_refs(task_ref, acquisition_ref, lock):
    def _do():
        if task_ref is not None:
            task_ref[0] = None
        if acquisition_ref is not None:
            acquisition_ref[0] = None
    if lock is not None:
        with lock:
            _do()
    else:
        _do()


def run_hardware_timed_sweep(
    session,
    ao_channels,
    waveform,
    rate,
    *,
    stop_check=None,
    on_progress=None,
    task_ref=None,
    acquisition_ref=None,
    lock=None,
):
    """Acquire one one-dimensional sweep with RFSoC as timing master.

    *on_progress* is called as the sweep advances, with a zero bin width on
    every point that has not been counted yet.
    """
    waveform = np.asarray(waveform, dtype=float)
    if waveform.ndim == 1:
        waveform = waveform[np.newaxis, :]
    n_points = waveform.shape[1]
    handle = AcquisitionHandle()
    _register_ref(acquisition_ref, handle, lock)
    try:
        return RFSoCConfocalBackend(session).acquire_line(
            ao_channels,
            waveform,
            1.0 / float(rate),
            n_imaging_points=n_points,
            handle=handle,
            on_progress=on_progress,
            stop_check=stop_check,
        )
    finally:
        _clear_refs(task_ref, acquisition_ref, lock)


def run_hardware_timed_raster(
    session,
    ao_channels,
    waveform,
    dwell_time,
    *,
    width,
    n_lines,
    stride,
    n_flyback,
    flyback_seconds=None,
    stop_check=None,
    on_progress=None,
    task_ref=None,
    acquisition_ref=None,
    lock=None,
):
    """Acquire a complete raster using one compiled QICK program and one NI task.

    *on_progress* is called while the frame is still being counted, with a zero
    bin width on every pixel the tProc has not reached yet.
    """
    handle = AcquisitionHandle()
    _register_ref(acquisition_ref, handle, lock)
    try:
        return RFSoCConfocalBackend(session).acquire_frame(
            ao_channels,
            waveform,
            dwell_time,
            width=width,
            n_lines=n_lines,
            stride=stride,
            n_flyback=n_flyback,
            flyback_seconds=flyback_seconds,
            on_line=on_progress,
            stop_check=stop_check,
            handle=handle,
        )
    finally:
        _clear_refs(task_ref, acquisition_ref, lock)


def counts_to_rate(counts, bin_widths_ps):
    """Convert raw counts and bin widths (picoseconds) to a count rate (cps).

    Points whose bin width is zero (not yet acquired) map to ``0.0``.
    """
    bins_s = np.asarray(bin_widths_ps, dtype=float) / 1e12
    rate = np.zeros_like(bins_s, dtype=float)
    valid = bins_s > 0
    rate[valid] = np.asarray(counts, dtype=float)[valid] / bins_s[valid]
    return rate
