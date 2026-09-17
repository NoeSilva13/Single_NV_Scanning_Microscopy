"""Fine-resolution FPGA Rabi sweep and the pulse lengths it calibrates."""

from __future__ import annotations

import numpy as np

from rfsoc.config import validate_linear_sweep
from .base import (
    _array,
    fine_sweep,
    fit_curve,
    normalized_result,
    oscillation_spectrum,
    spin_config,
    spin_executed,
    spin_requested,
)


def _rabi_model(t_ns, amplitude, period_ns, decay_ns, offset):
    return (
        amplitude
        * np.cos(2 * np.pi * t_ns / period_ns)
        * np.exp(-t_ns / decay_ns)
        + offset
    )


def _fit_rabi(result):
    """Fit the oscillation and report the pulse lengths it implies.

    Everything pulsed downstream is measured in these two numbers: a pi/2 pulse
    is a quarter of the Rabi period and a pi pulse is half of it.
    """
    t_ns = np.asarray(result.x, dtype=float)
    y = np.asarray(result.contrast, dtype=float)
    _, _, peaks_hz = oscillation_spectrum(t_ns, y)
    span_ns = float(t_ns[-1] - t_ns[0]) if t_ns.size > 1 else 1.0
    period_guess_ns = 1e9 / float(peaks_hz[0]) if peaks_hz.size else span_ns / 2
    popt, errors = fit_curve(
        _rabi_model,
        t_ns,
        y,
        p0=[
            float(np.ptp(y) / 2),
            period_guess_ns,
            max(span_ns, 1.0),
            float(np.mean(y)),
        ],
        bounds=(
            [-np.inf, 1e-3, 1e-3, -np.inf],
            [np.inf, np.inf, np.inf, np.inf],
        ),
    )
    if popt is None:
        result.fit = None
        return result
    period_ns = float(popt[1])
    period_error_ns = float(errors[1])
    result.fit = {
        "amplitude": float(popt[0]),
        "rabi_period_ns": period_ns,
        "rabi_period_error_ns": period_error_ns,
        "rabi_frequency_hz": 1e9 / period_ns,
        "mw_pi2_ns": period_ns / 4,
        "mw_pi2_error_ns": period_error_ns / 4,
        "mw_pi_ns": period_ns / 2,
        "mw_pi_error_ns": period_error_ns / 2,
        "decay_ns": float(popt[2]),
        "offset": float(popt[3]),
    }
    return result


def fitted_curve(result):
    """Sample the fitted oscillation, and label the calibrated pulse lengths."""
    fit = result.fit
    if not fit:
        return None
    x = np.linspace(float(result.x[0]), float(result.x[-1]), 512)
    y = _rabi_model(
        x, fit["amplitude"], fit["rabi_period_ns"], fit["decay_ns"], fit["offset"]
    )
    label = (
        f"mw_pi2_ns {fit['mw_pi2_ns']:.2f}\n"
        f"mw_pi_ns {fit['mw_pi_ns']:.2f}\n"
        f"Rabi {fit['rabi_frequency_hz'] / 1e6:.3f} MHz"
    )
    return x, y, label


def rabi(
    session,
    durations_ns,
    *,
    mw_frequency_hz=2.87e9,
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
    requested_x = validate_linear_sweep(durations_ns, "durations_ns")
    cfg = spin_config(
        session,
        reps=reps,
        mw_frequency_hz=mw_frequency_hz,
        mw_gain=mw_gain,
        laser_on_ns=laser_on_ns,
        readout_ns=readout_ns,
        laser_readout_offset_ns=laser_readout_offset_ns,
        reference_start_ns=reference_start_ns,
        mw_to_laser_delay_ns=mw_to_laser_delay_ns,
        relax_delay_ns=relax_delay_ns,
        get_reference=get_reference,
    )
    fine_sweep(cfg, "mw_duration", requested_x)
    with session.acquisition():
        from qickdawg.finetimingsuite import RabiFineRes

        data = RabiFineRes(cfg).acquire(progress=progress)
    x_ns = _array(data, "mw_duration_ftns")
    result = normalized_result(
        kind="Rabi",
        x_name="MW_duration",
        x_unit="ns",
        x=x_ns,
        data=data,
        integration_seconds=cfg.readout_integration_tns * 1e-9,
        reps=cfg.reps,
        requested=spin_requested(
            mw_frequency_hz=mw_frequency_hz,
            mw_gain=mw_gain,
            laser_on_ns=laser_on_ns,
            readout_ns=readout_ns,
            laser_readout_offset_ns=laser_readout_offset_ns,
            reference_start_ns=reference_start_ns,
            mw_to_laser_delay_ns=mw_to_laser_delay_ns,
            relax_delay_ns=relax_delay_ns,
            reps=reps,
            get_reference=get_reference,
            durations_ns=requested_x.tolist(),
        ),
        executed=spin_executed(cfg, durations_ns=x_ns.tolist()),
    )
    return _fit_rabi(result)
