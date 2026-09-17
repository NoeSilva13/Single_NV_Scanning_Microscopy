"""Shared configuration and result types for native RFSoC experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.optimize import curve_fit
from scipy.signal import find_peaks

from rfsoc.config import (
    base_nv_config,
    validate_hardware_settings,
    validate_linear_sweep,
)

# The only step ratios NVConfiguration.add_exponential_sweep() knows how to
# build, so an exponential axis has to pick one of them.
EXP_SCALING_FACTORS = frozenset({"17/16", "9/8", "5/4", "3/2"})


@dataclass
class ExperimentResult:
    kind: str
    x_name: str
    x_unit: str
    x: np.ndarray
    signal_counts: np.ndarray
    reference_counts: np.ndarray
    signal_rate_cps: np.ndarray
    reference_rate_cps: np.ndarray
    contrast: np.ndarray
    requested: dict[str, Any] = field(default_factory=dict)
    executed: dict[str, Any] = field(default_factory=dict)
    fit: dict[str, float] | None = None
    saved_files: dict[str, str] = field(default_factory=dict)


@dataclass
class CountingResult:
    """One counted point rather than a sweep: PL intensity or dark counts."""

    kind: str
    counts: int
    window_seconds: float
    reps: int
    requested: dict[str, Any] = field(default_factory=dict)
    executed: dict[str, Any] = field(default_factory=dict)

    @property
    def rate_cps(self):
        return self.counts / (self.window_seconds * self.reps)


def spin_config(
    session,
    *,
    reps,
    mw_frequency_hz,
    mw_gain,
    laser_on_ns,
    readout_ns,
    laser_readout_offset_ns,
    reference_start_ns,
    mw_to_laser_delay_ns,
    relax_delay_ns,
    mw_pi2_ns=None,
    mw_pi_ns=None,
    n_cpmg=None,
    get_reference=True,
):
    validate_hardware_settings(mw_frequency_hz)
    cfg = base_nv_config(session, reps=reps)
    cfg.mw_fGHz = float(mw_frequency_hz) / 1e9
    cfg.mw_gain = int(mw_gain)
    cfg.laser_on_tns = int(laser_on_ns)
    cfg.readout_integration_tns = int(readout_ns)
    cfg.laser_readout_offset_tns = int(laser_readout_offset_ns)
    cfg.readout_reference_start_tns = int(reference_start_ns)
    cfg.mw_to_laser_delay_tns = int(mw_to_laser_delay_ns)
    cfg.relax_delay_tns = int(relax_delay_ns)
    # Pulse lengths go in as fine time.  NVConfiguration derives the _ftsamp
    # names the FineRes programs read, so a pulse lands on a DAC sample rather
    # than on a tProc cycle: 0.2 ns of granularity instead of 3.3 ns.
    if mw_pi2_ns is not None:
        cfg.mw_pi2_ftns = float(mw_pi2_ns)
    if mw_pi_ns is not None:
        cfg.mw_pi_ftns = float(mw_pi_ns)
    if n_cpmg is not None:
        cfg.n_cpmg = int(n_cpmg)
    # CPMGXYFineRes and T1FineRes read scaling_mode in initialize() without
    # listing it in required_cfg, so a linear sweep has to say so out loud.
    # add_exponential_sweep() overwrites both when the sweep is exponential.
    cfg.scaling_mode = "linear"
    cfg.scaling_factor = ""
    # Four readouts per point with the reference, two without: dropping it
    # halves the sweep and costs the MW-off normalisation.
    cfg.get_reference = bool(get_reference)
    return cfg


def spin_requested(
    *,
    mw_frequency_hz,
    mw_gain,
    laser_on_ns,
    readout_ns,
    laser_readout_offset_ns,
    reference_start_ns,
    mw_to_laser_delay_ns,
    relax_delay_ns,
    reps,
    get_reference=True,
    mw_pi2_ns=None,
    mw_pi_ns=None,
    n_cpmg=None,
    **extra,
):
    """User-facing kwargs that went into a pulsed sweep, plus any extras."""
    settings = {
        "mw_frequency_hz": mw_frequency_hz,
        "mw_gain": mw_gain,
        "laser_on_ns": laser_on_ns,
        "readout_ns": readout_ns,
        "laser_readout_offset_ns": laser_readout_offset_ns,
        "reference_start_ns": reference_start_ns,
        "mw_to_laser_delay_ns": mw_to_laser_delay_ns,
        "relax_delay_ns": relax_delay_ns,
        "reps": reps,
        "get_reference": bool(get_reference),
    }
    if mw_pi2_ns is not None:
        settings["mw_pi2_ns"] = mw_pi2_ns
    if mw_pi_ns is not None:
        settings["mw_pi_ns"] = mw_pi_ns
    if n_cpmg is not None:
        settings["n_cpmg"] = n_cpmg
    settings.update(extra)
    return settings


_MISSING = object()


def _cfg_get(cfg, name, default=None):
    value = getattr(cfg, name, _MISSING)
    if value is not _MISSING:
        return value
    try:
        return cfg[name]
    except (KeyError, TypeError):
        return default


def spin_executed(cfg, **extra):
    """What the board actually ran, in the same names as ``spin_requested``."""
    settings = {
        "mw_frequency_hz": float(_cfg_get(cfg, "mw_fGHz")) * 1e9,
        "mw_gain": int(_cfg_get(cfg, "mw_gain")),
        "laser_on_ns": _cfg_get(cfg, "laser_on_tns"),
        "readout_ns": _cfg_get(cfg, "readout_integration_tns"),
        "laser_readout_offset_ns": _cfg_get(cfg, "laser_readout_offset_tns"),
        "reference_start_ns": _cfg_get(cfg, "readout_reference_start_tns"),
        "mw_to_laser_delay_ns": _cfg_get(cfg, "mw_to_laser_delay_tns"),
        "relax_delay_ns": _cfg_get(cfg, "relax_delay_tns"),
        "reps": _cfg_get(cfg, "reps"),
        "get_reference": bool(_cfg_get(cfg, "get_reference", True)),
    }
    mw_pi2_ns = _cfg_get(cfg, "mw_pi2_ftns")
    if mw_pi2_ns is not None:
        settings["mw_pi2_ns"] = mw_pi2_ns
    mw_pi_ns = _cfg_get(cfg, "mw_pi_ftns")
    if mw_pi_ns is not None:
        settings["mw_pi_ns"] = mw_pi_ns
    n_cpmg = _cfg_get(cfg, "n_cpmg")
    if n_cpmg is not None:
        settings["n_cpmg"] = n_cpmg
    settings.update(extra)
    return settings


def fine_sweep(cfg, name, values_ns):
    """Point the fine-time sweep *name* at *values_ns*, in nanoseconds.

    Writes start, end and ``nsweep_points`` directly instead of calling
    ``NVConfiguration.add_linear_sweep``, whose ``nsweep_points`` branch
    computes the step backwards and lands one step past the requested end.  The
    programs read exactly these three attributes, and the ``_ftns`` names carry
    the conversion to the DAC samples they sweep over.
    """
    values = validate_linear_sweep(values_ns, name)
    cfg[f"{name}_start_ftns"] = float(values[0])
    cfg[f"{name}_end_ftns"] = float(values[-1])
    cfg.nsweep_points = int(values.size)
    cfg.scaling_mode = "linear"
    cfg.scaling_factor = ""
    return values


def fit_curve(model, x, y, p0, bounds=None, maxfev=20_000):
    """Fit *model*, reporting ``(None, None)`` instead of raising.

    A fit is a convenience laid over the measurement: a sweep that is short,
    flat or full of noise still has to be saved and plotted, so a fit that does
    not converge is an absent number rather than a failed acquisition.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.size <= len(p0) or not np.all(np.isfinite(y)) or np.ptp(y) == 0:
        return None, None
    kwargs = {"maxfev": maxfev}
    if bounds is not None:
        kwargs["bounds"] = bounds
    try:
        popt, pcov = curve_fit(model, x, y, p0=p0, **kwargs)
    except (RuntimeError, ValueError, TypeError):
        return None, None
    return popt, np.sqrt(np.diag(pcov))


def oscillation_spectrum(x_ns, y):
    """Amplitude spectrum of a trace sampled in nanoseconds, and its peaks.

    Returns the frequency axis in hertz, the spectrum, and the peak frequencies
    ordered by height.  A decaying-cosine fit only converges when it starts near
    the right frequency, and this is where that first guess comes from.  The
    window is Hanning, as in the QICK-DAWG demo, so a trace that does not end on
    a whole period does not smear across the spectrum.
    """
    x_ns = np.asarray(x_ns, dtype=float)
    y = np.asarray(y, dtype=float)
    steps = np.diff(x_ns)
    if y.size < 4 or steps.size == 0 or not np.all(np.isfinite(y)):
        return np.zeros(0), np.zeros(0), np.zeros(0)
    spectrum = np.abs(np.fft.rfft((y - np.mean(y)) * np.hanning(y.size)))
    frequencies_hz = np.fft.rfftfreq(y.size, d=float(np.mean(steps)) * 1e-9)
    if not spectrum.size or spectrum.max() <= 0:
        return frequencies_hz, spectrum, np.zeros(0)
    peaks, _ = find_peaks(spectrum, height=0.2 * spectrum.max())
    ordered = peaks[np.argsort(spectrum[peaks])[::-1]]
    return frequencies_hz, spectrum, frequencies_hz[ordered]


def _array(data, name):
    try:
        return np.asarray(data[name], dtype=float)
    except (KeyError, TypeError):
        return np.asarray(getattr(data, name), dtype=float)


def _optional_array(data, name):
    try:
        return _array(data, name)
    except AttributeError:
        return None


def normalized_result(
    *,
    kind,
    x_name,
    x_unit,
    x,
    data,
    integration_seconds,
    reps,
    requested,
    executed,
    t1_ratio=False,
):
    """Normalize QICK-DAWG's four-readout result into a stable native schema."""
    signal_on = _array(data, "signal1")
    laser_ref_on = _array(data, "reference1")
    signal_off = _optional_array(data, "signal2")
    on_norm = np.divide(
        signal_on, laser_ref_on,
        out=np.zeros_like(signal_on), where=laser_ref_on != 0,
    )
    if signal_off is None:
        # get_reference=False: the MW-off sequence was never run, so the only
        # normalisation left is the steady state at the end of the same laser
        # pulse, which is what reference1 already is.
        return ExperimentResult(
            kind=kind,
            x_name=x_name,
            x_unit=x_unit,
            x=np.asarray(x, dtype=float),
            signal_counts=signal_on,
            reference_counts=laser_ref_on,
            signal_rate_cps=signal_on / (float(integration_seconds) * int(reps)),
            reference_rate_cps=laser_ref_on / (float(integration_seconds) * int(reps)),
            contrast=on_norm,
            requested=requested,
            executed=executed,
        )
    laser_ref_off = _array(data, "reference2")
    off_norm = np.divide(
        signal_off, laser_ref_off,
        out=np.zeros_like(signal_off), where=laser_ref_off != 0,
    )
    if t1_ratio:
        contrast = np.divide(
            on_norm, off_norm, out=np.zeros_like(on_norm), where=off_norm != 0
        )
    else:
        contrast = np.divide(
            off_norm - on_norm,
            off_norm,
            out=np.zeros_like(off_norm),
            where=off_norm != 0,
        )
    norm = float(integration_seconds) * int(reps)
    return ExperimentResult(
        kind=kind,
        x_name=x_name,
        x_unit=x_unit,
        x=np.asarray(x, dtype=float),
        signal_counts=signal_on,
        reference_counts=signal_off,
        signal_rate_cps=signal_on / norm,
        reference_rate_cps=signal_off / norm,
        contrast=contrast,
        requested=requested,
        executed=executed,
    )
