"""
Generic N-axis raster scan engine (canonical unit: micrometers).
-------------------------------------------------
Builds the multi-channel voltage waveform for a hardware-timed raster over an
arbitrary set of DAQ axes (1..3 in practice: X, Y, Z), drives it through
``scanning_core.run_hardware_timed_sweep``, and reconstructs the acquired count
rate into a 2D image or 3D volume.

Axis ordering is *fast to slow*: ``axes[0]`` sweeps fastest (one full line per
imaging row), the remaining axes step between lines. A flyback ramp is inserted
between consecutive fast-axis lines so every axis (including the slow ones that
step at line boundaries) has time to retrace and settle before the next line;
the photon counts collected during flyback samples are discarded.

All positions handled here are in micrometers. Each :class:`daq_axis.DAQAxis`
converts its own waveform to volts at the DAQ boundary via ``to_voltage``.
"""

import itertools

import numpy as np

from scanning_core import run_hardware_timed_sweep, counts_to_rate


def build_raster_waveforms(axes_points, n_flyback=0):
    """Compose per-axis µm waveforms for an N-axis raster.

    Args:
        axes_points: List of 1D µm arrays ordered fast..slow. ``axes_points[0]``
            is the fast axis (columns); the rest step between lines.
        n_flyback: Retrace samples inserted between consecutive fast lines
            (0 disables flyback).

    Returns:
        waveforms: List of 1D µm arrays (one per axis, same order as input).
        shape: Reconstruction shape in acquisition order (slow..fast), e.g.
            ``(height, width)`` for 2D or ``(depth, height, width)`` for 3D.
        stride: Samples per line including flyback (``width + n_flyback``).
        width: Number of imaging samples per fast line.
        n_lines: Total number of fast-axis lines.
    """
    axes_points = [np.asarray(p, dtype=float) for p in axes_points]
    fast = axes_points[0]
    width = len(fast)
    slow = axes_points[1:]                    # [s1 (fastest slow) .. s_last (slowest)]
    slow_rev = list(reversed(slow))           # [slowest .. s1] -> slowest is outer loop

    if slow:
        combos = list(itertools.product(*[range(len(a)) for a in slow_rev]))
    else:
        combos = [()]
    n_lines = len(combos)

    def coords_for(combo):
        """Map a slowest-first index tuple back to per-slow-axis µm positions."""
        coord = [0.0] * len(slow)
        for k, idx in enumerate(combo):
            coord[len(slow) - 1 - k] = slow_rev[k][idx]
        return coord

    n_axes = len(axes_points)
    segs = [[] for _ in range(n_axes)]

    use_flyback = n_flyback and n_flyback > 0
    for li, combo in enumerate(combos):
        coord = coords_for(combo)
        segs[0].append(fast)
        for j in range(len(slow)):
            segs[j + 1].append(np.full(width, coord[j]))

        if use_flyback and li < n_lines - 1:
            ncoord = coords_for(combos[li + 1])
            segs[0].append(np.linspace(fast[-1], fast[0], n_flyback))
            for j in range(len(slow)):
                segs[j + 1].append(np.linspace(coord[j], ncoord[j], n_flyback))

    waveforms = [np.concatenate(s) for s in segs]
    shape = tuple(len(a) for a in slow_rev) + (width,)
    stride = width + (n_flyback if use_flyback else 0)
    return waveforms, shape, stride, width, n_lines


def raster_geometry(axes_points, n_flyback=0):
    """Lightweight geometry (no waveform allocation) for a raster.

    Returns ``(shape, stride, width, n_lines)`` matching
    :func:`build_raster_waveforms`.
    """
    lengths = [len(np.asarray(p)) for p in axes_points]
    width = lengths[0]
    slow_lengths = lengths[1:]
    shape = tuple(reversed(slow_lengths)) + (width,)
    n_lines = int(np.prod(slow_lengths)) if slow_lengths else 1
    use_flyback = n_flyback and n_flyback > 0
    stride = width + (n_flyback if use_flyback else 0)
    return shape, stride, width, n_lines


def reconstruct(counts, bin_widths_ps, shape, stride, width):
    """Rebuild the 2D image / 3D volume (count rate, cps) from raw CBM output.

    Points not yet acquired (zero bin width) map to 0, so this is safe to call
    with partial data during live updates.
    """
    counts = np.asarray(counts)
    bin_widths_ps = np.asarray(bin_widths_ps)
    n_lines = int(np.prod(shape[:-1])) if len(shape) > 1 else 1

    lines = np.zeros((n_lines, width), dtype=np.float32)
    for li in range(n_lines):
        start = li * stride
        end = start + width
        if end <= len(bin_widths_ps):
            lines[li] = counts_to_rate(counts[start:end], bin_widths_ps[start:end])
    return lines.reshape(shape)


def run_raster(tagger, axes, axes_points, dwell_time, n_flyback=0, *,
               on_progress=None, stop_check=None,
               task_ref=None, cbm_ref=None, lock=None):
    """Run a hardware-timed N-axis raster and return raw counts + geometry.

    Args:
        tagger: Time Tagger instance.
        axes: List of :class:`daq_axis.DAQAxis`, fast..slow (parallel to
            ``axes_points``).
        axes_points: List of 1D µm arrays, fast..slow.
        dwell_time: Per-point integration time in seconds (1/rate).
        n_flyback: Retrace samples between fast lines.
        on_progress: Optional callback ``(partial_counts, partial_bins_ps)``.
        stop_check, task_ref, cbm_ref, lock: Forwarded to
            ``run_hardware_timed_sweep``.

    Returns:
        counts, bin_widths_ps, shape, stride, width
    """
    waveforms_um, shape, stride, width, _n_lines = build_raster_waveforms(
        axes_points, n_flyback
    )
    volt_waveform = np.array(
        [axis.to_voltage(wf) for axis, wf in zip(axes, waveforms_um)]
    )
    channels = [axis.ao_channel for axis in axes]
    rate = 1.0 / dwell_time

    counts, bin_widths_ps = run_hardware_timed_sweep(
        tagger,
        channels,
        volt_waveform,
        rate,
        stop_check=stop_check,
        on_progress=on_progress,
        task_ref=task_ref,
        cbm_ref=cbm_ref,
        lock=lock,
    )
    return counts, bin_widths_ps, shape, stride, width
