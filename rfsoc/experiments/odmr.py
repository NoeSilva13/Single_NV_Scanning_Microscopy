"""FPGA-swept CW and pulsed ODMR."""

from __future__ import annotations

import numpy as np

from rfsoc.config import base_nv_config, validate_hardware_settings, validate_linear_sweep
from rfsoc.process_lock import RFSoCBusyError
from .base import (
    ExperimentResult,
    _array,
    fit_curve,
    normalized_result,
    spin_config,
)


def _lorentzian(f_hz, amplitude, center_hz, hwhm_hz, offset):
    return amplitude / (1 + ((f_hz - center_hz) / hwhm_hz) ** 2) + offset


def _fit_resonance(result):
    """Fit the ODMR line as one Lorentzian and report where the NV resonates.

    One line, so a spectrum split by strain or by a magnetic field is fitted as
    the deeper of its two dips; sweep each half separately to get both.
    """
    f_hz = np.asarray(result.x, dtype=float)
    y = np.asarray(result.contrast, dtype=float)
    baseline = float(np.median(y))
    deepest = int(np.argmax(np.abs(y - baseline)))
    span_hz = abs(float(f_hz[-1] - f_hz[0])) if f_hz.size > 1 else 1e6
    popt, errors = fit_curve(
        _lorentzian,
        f_hz,
        y,
        p0=[
            float(y[deepest] - baseline),
            float(f_hz[deepest]),
            max(span_hz / 20, 1e3),
            baseline,
        ],
        bounds=(
            [-np.inf, float(np.min(f_hz)), 1e3, -np.inf],
            [np.inf, float(np.max(f_hz)), np.inf, np.inf],
        ),
    )
    if popt is None:
        result.fit = None
        return result
    result.fit = {
        "amplitude": float(popt[0]),
        "resonance_hz": float(popt[1]),
        "resonance_error_hz": float(errors[1]),
        "linewidth_hz": 2 * abs(float(popt[2])),
        "linewidth_error_hz": 2 * float(errors[2]),
        "offset": float(popt[3]),
    }
    return result


def fitted_curve(result):
    """Sample the fitted line densely, and label where the NV resonates."""
    fit = result.fit
    if not fit or "resonance_hz" not in fit:
        return None
    x = np.linspace(float(result.x[0]), float(result.x[-1]), 512)
    y = _lorentzian(
        x,
        fit["amplitude"],
        fit["resonance_hz"],
        fit["linewidth_hz"] / 2,
        fit["offset"],
    )
    label = (
        f"resonance {fit['resonance_hz'] / 1e9:.6f} GHz\n"
        f"linewidth {fit['linewidth_hz'] / 1e6:.3f} MHz"
    )
    return x, y, label


def _cw_contrast(reference, signal):
    return np.divide(
        reference - signal,
        reference,
        out=np.zeros_like(reference),
        where=reference != 0,
    )


def _cw_odmr_config(session, requested_x, *, readout_ns, relax_delay_ns, reps, mw_gain):
    validate_hardware_settings(float(requested_x.mean()))
    cfg = base_nv_config(session, reps=reps)
    cfg.readout_integration_tns = int(readout_ns)
    cfg.relax_delay_tns = int(relax_delay_ns)
    cfg.mw_gain = int(mw_gain)
    cfg.mw_start_fMHz = requested_x[0] / 1e6
    cfg.mw_end_fMHz = requested_x[-1] / 1e6
    cfg.nsweep_points = int(requested_x.size)
    return cfg


def cw_odmr(
    session,
    frequencies_hz,
    *,
    readout_ns=100_000,
    relax_delay_ns=2_000,
    reps=5_000,
    mw_gain=5_000,
    progress=True,
):
    requested_x = validate_linear_sweep(frequencies_hz, "frequencies_hz")
    cfg = _cw_odmr_config(
        session,
        requested_x,
        readout_ns=readout_ns,
        relax_delay_ns=relax_delay_ns,
        reps=reps,
        mw_gain=mw_gain,
    )
    with session.acquisition():
        data = session.qd.LockinODMR(cfg).acquire(progress=progress)

    signal = _array(data, "signal")
    reference = _array(data, "reference")
    x_mhz = _array(data, "frequencies")
    contrast = _cw_contrast(reference, signal)
    integration_s = cfg.readout_integration_tns * 1e-9
    norm = integration_s * cfg.reps
    result = ExperimentResult(
        kind="CW_ODMR",
        x_name="Frequency",
        x_unit="Hz",
        x=x_mhz * 1e6,
        signal_counts=signal,
        reference_counts=reference,
        signal_rate_cps=signal / norm,
        reference_rate_cps=reference / norm,
        contrast=contrast,
        requested={"frequencies_hz": requested_x.tolist(), "readout_ns": readout_ns},
        executed={
            "frequencies_hz": (x_mhz * 1e6).tolist(),
            "readout_ns": cfg.readout_integration_tns,
            "reps": cfg.reps,
            "mw_gain": cfg.mw_gain,
        },
    )
    return _fit_resonance(result)


def cw_odmr_source(
    session,
    frequencies_hz,
    *,
    readout_ns=100_000,
    relax_delay_ns=2_000,
    reps=5_000,
    mw_gain=5_000,
):
    """Compile one CW ODMR sweep and average its passes as they arrive.

    Returns the frequency axis and a callable that runs one more pass, reporting
    the contrast averaged over every pass so far, so a live window converges on
    the line while it is watched.  Like the live count, it stands down rather
    than wait: a busy board yields ``None``.
    """
    requested_x = validate_linear_sweep(frequencies_hz, "frequencies_hz")
    cfg = _cw_odmr_config(
        session,
        requested_x,
        readout_ns=readout_ns,
        relax_delay_ns=relax_delay_ns,
        reps=reps,
        mw_gain=mw_gain,
    )
    program = session.qd.LockinODMR(cfg)
    totals = {"signal": 0.0, "reference": 0.0}

    def one_pass():
        try:
            with session.acquisition(blocking=False):
                data = program.acquire(progress=False)
        except RFSoCBusyError:
            return None
        totals["signal"] = totals["signal"] + _array(data, "signal")
        totals["reference"] = totals["reference"] + _array(data, "reference")
        return _cw_contrast(totals["reference"], totals["signal"])

    return requested_x, one_pass


def pulsed_odmr(
    session,
    frequencies_hz,
    *,
    mw_duration_ns=1_000,
    laser_on_ns=3_000,
    readout_ns=300,
    laser_readout_offset_ns=100,
    reference_start_ns=2_000,
    mw_to_laser_delay_ns=500,
    relax_delay_ns=2_000,
    reps=100_000,
    mw_gain=5_000,
    get_reference=True,
    progress=True,
):
    requested_x = validate_linear_sweep(frequencies_hz, "frequencies_hz")
    cfg = spin_config(
        session,
        reps=reps,
        mw_frequency_hz=float(requested_x.mean()),
        mw_gain=mw_gain,
        laser_on_ns=laser_on_ns,
        readout_ns=readout_ns,
        laser_readout_offset_ns=laser_readout_offset_ns,
        reference_start_ns=reference_start_ns,
        mw_to_laser_delay_ns=mw_to_laser_delay_ns,
        relax_delay_ns=relax_delay_ns,
        mw_pi_ns=mw_duration_ns,
        get_reference=get_reference,
    )
    cfg.mw_start_fMHz = requested_x[0] / 1e6
    cfg.mw_end_fMHz = requested_x[-1] / 1e6
    cfg.nsweep_points = int(requested_x.size)
    with session.acquisition():
        from qickdawg.finetimingsuite import PODMRFineRes

        data = PODMRFineRes(cfg).acquire(progress=progress)
    x_hz = _array(data, "mw_fMHz") * 1e6
    result = normalized_result(
        kind="Pulsed_ODMR",
        x_name="Frequency",
        x_unit="Hz",
        x=x_hz,
        data=data,
        integration_seconds=cfg.readout_integration_tns * 1e-9,
        reps=cfg.reps,
        requested={
            "frequencies_hz": requested_x.tolist(),
            "mw_duration_ns": mw_duration_ns,
        },
        executed={
            "frequencies_hz": x_hz.tolist(),
            "mw_duration_ns": cfg.mw_pi_ftns,
            "readout_ns": cfg.readout_integration_tns,
            "reps": cfg.reps,
            "mw_gain": cfg.mw_gain,
            "get_reference": cfg.get_reference,
        },
    )
    return _fit_resonance(result)
