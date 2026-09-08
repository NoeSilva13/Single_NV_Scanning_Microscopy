"""
Shared hardware-timed scanning core.
-------------------------------------------------
Provides the reusable AO + CountBetweenMarkers (CBM) primitive used by every
DAQ-driven acquisition in the confocal application:

- 2D raster scan (galvo XY on ao0/ao1)
- Auto-focus Z sweep (piezo on ao2)
- Single-axis line scan (galvo X or Y)

The pattern is identical in all cases: a finite, hardware-timed analog-output
task clocks out a pre-computed voltage waveform; that same sample clock is
exported to a PFI terminal wired to the Time Tagger, where CountBetweenMarkers
counts APD photons between successive clock edges (one value per point). The
integration time of each point is therefore defined by the DAQ clock, not by a
free-running Counter binwidth.
"""

import time

import numpy as np
import nidaqmx
from nidaqmx.constants import AcquisitionType
import TimeTagger


def _register_ref(ref, value, lock):
    """Store *value* in the mutable single-element list *ref* under *lock*."""
    if ref is None:
        return
    if lock is not None:
        with lock:
            ref[0] = value
    else:
        ref[0] = value


def _cleanup(task, cbm, task_ref, cbm_ref, lock):
    """Stop/close the AO task and stop the CBM, clearing shared references."""
    def _do():
        if task is not None:
            try:
                task.stop()
                task.close()
            except Exception:
                pass
        if task_ref is not None:
            task_ref[0] = None
        if cbm is not None:
            try:
                cbm.stop()
            except Exception:
                pass
        if cbm_ref is not None:
            cbm_ref[0] = None

    if lock is not None:
        with lock:
            _do()
    else:
        _do()


def run_hardware_timed_sweep(
    tagger,
    ao_channels,
    waveform,
    rate,
    *,
    click_channel=1,
    begin_channel=3,
    end_channel=-3,
    clock_export_term="/Dev1/PFI8",
    extra_clock_samples=1,
    cbm_settle_s=1.0,
    poll_interval_s=0.2,
    stop_check=None,
    on_progress=None,
    task_ref=None,
    cbm_ref=None,
    lock=None,
):
    """Run a finite hardware-timed AO sweep and count photons per point via CBM.

    Parameters
    ----------
    tagger : TimeTagger.TimeTagger
        The Time Tagger instance.
    ao_channels : list[str]
        Analog-output channel names, e.g. ``["Dev1/ao0", "Dev1/ao1"]``.
    waveform : np.ndarray
        Voltage samples. Shape ``(len(ao_channels), n_points)`` (a 1D array is
        accepted for a single channel).
    rate : float
        Sample-clock rate in Hz (``1 / dwell_time``). Defines each point's
        integration time.
    click_channel, begin_channel, end_channel : int
        Time Tagger channels for photon clicks and the DAQ clock markers.
    clock_export_term : str
        PFI terminal the AO sample clock is exported to (wired to the tagger).
    extra_clock_samples : int
        Extra clock samples beyond ``n_points`` (preserves the ``+1`` used by
        the original raster scan so ``n_points`` intervals are produced).
    cbm_settle_s : float
        Seconds to wait after starting the CBM before starting the AO task.
    poll_interval_s : float
        Polling period while waiting for the sweep to finish.
    stop_check : Optional[Callable[[], bool]]
        Returns True to abort the sweep early.
    on_progress : Optional[Callable[[np.ndarray, np.ndarray], None]]
        Called during polling with ``(partial_counts, partial_bin_widths_ps)``.
    task_ref, cbm_ref : Optional[list]
        Single-element mutable lists that receive the live task/CBM so an
        external Stop control can terminate them.
    lock : Optional[threading.Lock]
        Guards writes to ``task_ref``/``cbm_ref``.

    Returns
    -------
    Tuple[np.ndarray, np.ndarray]
        ``(counts, bin_widths_ps)`` with ``n_points`` entries each.
    """
    waveform = np.asarray(waveform, dtype=float)
    if waveform.ndim == 1:
        waveform = waveform[np.newaxis, :]
    n_channels, n_points = waveform.shape

    task = None
    cbm = None
    try:
        task = nidaqmx.Task()
        _register_ref(task_ref, task, lock)

        for chan in ao_channels:
            task.ao_channels.add_ao_voltage_chan(chan)

        task.timing.cfg_samp_clk_timing(
            rate=rate,
            sample_mode=AcquisitionType.FINITE,
            samps_per_chan=n_points + extra_clock_samples,
        )
        task.export_signals.samp_clk_output_term = clock_export_term

        # nidaqmx expects a 1D array for a single channel, 2D otherwise.
        write_data = waveform[0] if n_channels == 1 else waveform
        task.write(write_data, auto_start=False)

        cbm = TimeTagger.CountBetweenMarkers(
            tagger=tagger,
            click_channel=click_channel,
            begin_channel=begin_channel,
            end_channel=end_channel,
            n_values=n_points,
        )
        _register_ref(cbm_ref, cbm, lock)

        cbm.start()
        time.sleep(cbm_settle_s)
        task.start()

        while not cbm.ready():
            if stop_check is not None and stop_check():
                break
            time.sleep(poll_interval_s)
            if on_progress is not None:
                on_progress(cbm.getData(), cbm.getBinWidths())

        counts = np.asarray(cbm.getData())
        bin_widths_ps = np.asarray(cbm.getBinWidths())
        return counts, bin_widths_ps

    finally:
        _cleanup(task, cbm, task_ref, cbm_ref, lock)


def counts_to_rate(counts, bin_widths_ps):
    """Convert raw counts and bin widths (picoseconds) to a count rate (cps).

    Points whose bin width is zero (not yet acquired) map to ``0.0``.
    """
    bins_s = np.asarray(bin_widths_ps, dtype=float) / 1e12
    rate = np.zeros_like(bins_s, dtype=float)
    valid = bins_s > 0
    rate[valid] = np.asarray(counts, dtype=float)[valid] / bins_s[valid]
    return rate
