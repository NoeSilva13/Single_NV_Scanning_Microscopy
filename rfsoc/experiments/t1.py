"""FPGA delay-swept T1 acquisition and host-side fit."""

from __future__ import annotations

import numpy as np

from rfsoc.config import validate_linear_sweep
from .base import (
    EXP_SCALING_FACTORS,
    _array,
    fit_curve,
    normalized_result,
    spin_config,
)


def _t1_model(t_s, amplitude, t1_s, stretch, offset):
    return amplitude * np.exp(-np.power(t_s / t1_s, stretch)) + offset


def _fit_t1(result):
    popt, errors = fit_curve(
        _t1_model,
        result.x * 1e-9,
        result.contrast,
        p0=[
            float(result.contrast[0] - result.contrast[-1]),
            max(float(np.median(result.x * 1e-9)), 1e-9),
            1.0,
            float(result.contrast[-1]),
        ],
        bounds=([-np.inf, 1e-12, 0.1, -np.inf], [np.inf, np.inf, 1.0, np.inf]),
    )
    if popt is None:
        result.fit = None
        return result
    result.fit = {
        "amplitude": float(popt[0]),
        "t1_seconds": float(popt[1]),
        "stretch": float(popt[2]),
        "offset": float(popt[3]),
        "t1_error_seconds": float(errors[1]),
    }
    return result


def fitted_curve(result):
    """Sample the fitted stretched exponential, and label T1."""
    fit = result.fit
    if not fit:
        return None
    x_ns = np.linspace(float(result.x[0]), float(result.x[-1]), 512)
    y = _t1_model(
        x_ns * 1e-9,
        fit["amplitude"],
        fit["t1_seconds"],
        fit["stretch"],
        fit["offset"],
    )
    label = f"T1 {fit['t1_seconds'] * 1e3:.3f} ms\nstretch {fit['stretch']:.2f}"
    return x_ns, y, label


def t1(
    session,
    delays_ns,
    *,
    scaling="linear",
    scaling_factor="9/8",
    mw_frequency_hz=2.87e9,
    mw_pi_ns=1_000,
    laser_on_ns=50_000,
    readout_ns=3_000,
    laser_readout_offset_ns=1_500,
    reference_start_ns=40_000,
    mw_to_laser_delay_ns=500,
    relax_delay_ns=2_000,
    reps=3_000,
    mw_gain=5_000,
    get_reference=True,
    progress=True,
):
    requested_x = np.asarray(list(delays_ns), dtype=float)
    if requested_x.size < 2 or np.any(requested_x < 0):
        raise ValueError("delays_ns must contain at least two non-negative values")
    if scaling == "linear":
        validate_linear_sweep(requested_x, "delays_ns")
    elif scaling == "exponential":
        if requested_x[0] <= 0:
            raise ValueError("exponential T1 sweep must start above zero")
        if scaling_factor not in EXP_SCALING_FACTORS:
            raise ValueError(f"unsupported T1 exponential factor: {scaling_factor}")
    else:
        raise ValueError("scaling must be 'linear' or 'exponential'")

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
        # T1FineRes 4bc384f checks mw_pi2_ftsamp but reads mw_pi_ftsamp, so the
        # pi length goes into both names until upstream settles on one.
        mw_pi2_ns=mw_pi_ns,
        mw_pi_ns=mw_pi_ns,
        get_reference=get_reference,
    )
    if scaling == "linear":
        # Avoid NVConfiguration.add_linear_sweep(nsweep_points=...), whose
        # pinned implementation computes a reversed delta and one extra step.
        cfg.delay_start_tns = float(requested_x[0])
        cfg.delay_end_tns = float(requested_x[-1])
        cfg.nsweep_points = int(requested_x.size)
    else:
        cfg.add_exponential_sweep(
            "delay",
            "tns",
            float(requested_x[0]),
            float(requested_x[-1]),
            scaling_factor=scaling_factor,
        )
    with session.acquisition():
        from qickdawg.finetimingsuite import T1FineRes

        data = T1FineRes(cfg).acquire(progress=progress)
    x_ns = _array(data, "delay_tns")
    result = normalized_result(
        kind="T1",
        x_name="Delay",
        x_unit="ns",
        x=x_ns,
        data=data,
        integration_seconds=cfg.readout_integration_tns * 1e-9,
        reps=cfg.reps,
        requested={
            "delays_ns": requested_x.tolist(),
            "scaling": scaling,
            "scaling_factor": scaling_factor,
            "mw_pi_ns": mw_pi_ns,
        },
        executed={
            "delays_ns": x_ns.tolist(),
            "mw_pi_ns": cfg.mw_pi_ftns,
            "mw_frequency_hz": cfg.mw_fGHz * 1e9,
            "readout_ns": cfg.readout_integration_tns,
            "reps": cfg.reps,
            "mw_gain": cfg.mw_gain,
            "get_reference": cfg.get_reference,
        },
        t1_ratio=True,
    )
    return _fit_t1(result)
