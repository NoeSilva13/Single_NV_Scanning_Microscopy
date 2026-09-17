"""Readout window calibration: where to count, for how long, and how long to pump.

``CountingDurationFineRes`` counts a single narrow window per acquire, so the
window is walked across the laser pulse from the host, one program per offset.
With the microwave pulse on and off, the difference between the two traces is the
spin contrast, and it decays as the laser repumps the NV into ms=0.  That time
constant sets the three numbers every pulsed experiment depends on: the counting
window, the offset that puts it where the photoluminescence has risen, and the
pumping time.
"""

from __future__ import annotations

import numpy as np

from .base import ExperimentResult, _array, fit_curve, spin_config

# Fraction of the peak photoluminescence that counts as "the laser is on".
PL_RISE_FRACTION = 0.8
# Pumping time recommended as a multiple of the measured repump constant.
LASER_ON_TAU_MULTIPLE = 5.0


def _exponential(t, amplitude, tau, offset):
    return amplitude * np.exp(-t / tau) + offset


def _fit_window(offsets_ns, contrast, pl_cps):
    """Turn a window walk into the numbers the other experiments need.

    The fractional contrast is what decays cleanly: both traces carry the same
    photoluminescence rise, so dividing it out leaves the repump exponential on
    its own.  The fit starts at the peak of that contrast, because everything
    before it is the laser still turning on.
    """
    peak = int(np.argmax(contrast))
    t = offsets_ns[peak:] - offsets_ns[peak]
    y = contrast[peak:]
    fit = {"peak_contrast_offset_ns": float(offsets_ns[peak])}

    rise = np.flatnonzero(pl_cps >= PL_RISE_FRACTION * np.max(pl_cps))
    if rise.size:
        fit["recommended_laser_readout_offset_ns"] = float(offsets_ns[rise[0]])

    popt, errors = fit_curve(
        _exponential,
        t,
        y,
        p0=[float(y[0] - y[-1]), max(float(np.median(t)), 1.0), float(y[-1])],
        bounds=([-np.inf, 1e-3, -np.inf], [np.inf, np.inf, np.inf]),
    )
    if popt is None:
        return fit
    tau = float(popt[1])
    fit.update(
        amplitude=float(popt[0]),
        tau_ns=tau,
        tau_error_ns=float(errors[1]),
        offset=float(popt[2]),
        recommended_readout_integration_ns=tau,
        recommended_laser_on_ns=LASER_ON_TAU_MULTIPLE * tau,
    )
    return fit


def fitted_curve(result):
    """Sample the fitted repump decay, and label the numbers it recommends."""
    fit = result.fit
    if not fit or "tau_ns" not in fit:
        return None
    peak_ns = fit["peak_contrast_offset_ns"]
    x = np.linspace(peak_ns, float(result.x[-1]), 512)
    y = _exponential(x - peak_ns, fit["amplitude"], fit["tau_ns"], fit["offset"])
    label = (
        f"repump tau {fit['tau_ns']:.0f} ns\n"
        f"readout_ns {fit['recommended_readout_integration_ns']:.0f}\n"
        f"laser_on_ns {fit['recommended_laser_on_ns']:.0f}"
    )
    offset = fit.get("recommended_laser_readout_offset_ns")
    if offset is not None:
        label += f"\nlaser_readout_offset_ns {offset:.0f}"
    return x, y, label


def readout_window(
    session,
    *,
    window_ns=100,
    n_offsets=40,
    offset_start_ns=0.0,
    offset_step_ns=None,
    offsets_ns=None,
    mw_frequency_hz=2.87e9,
    mw_pi_ns=180.0,
    mw_gain=5_000,
    laser_on_ns=15_000,
    reference_start_ns=12_000,
    mw_to_laser_delay_ns=555,
    relax_delay_ns=1_500,
    reps=10_000,
    progress=True,
):
    """Walk a narrow counting window across the laser pulse and fit the repump.

    By default the offsets tile the pulse with contiguous bins of *window_ns*,
    which is how the QICK-DAWG demo builds its pseudo time trace.  Pass
    *offsets_ns* to walk an explicit list instead.
    """
    if offsets_ns is None:
        step = float(window_ns if offset_step_ns is None else offset_step_ns)
        offsets = offset_start_ns + step * np.arange(int(n_offsets), dtype=float)
    else:
        offsets = np.asarray(list(offsets_ns), dtype=float)
    if offsets.size < 2:
        raise ValueError("a readout window walk needs at least two offsets")

    cfg = spin_config(
        session,
        reps=reps,
        mw_frequency_hz=mw_frequency_hz,
        mw_gain=mw_gain,
        laser_on_ns=laser_on_ns,
        readout_ns=window_ns,
        laser_readout_offset_ns=offsets[0],
        reference_start_ns=reference_start_ns,
        mw_to_laser_delay_ns=mw_to_laser_delay_ns,
        relax_delay_ns=relax_delay_ns,
        mw_pi_ns=mw_pi_ns,
        # CountingDurationFineRes reshapes four readouts unconditionally, so the
        # MW-off half of the sequence is not optional here.
        get_reference=True,
    )

    signal_on = np.zeros(offsets.size)
    signal_off = np.zeros(offsets.size)
    executed_offsets = np.zeros(offsets.size)
    with session.acquisition():
        from qickdawg.finetimingsuite import CountingDurationFineRes

        for index, offset_ns in enumerate(offsets):
            cfg.laser_readout_offset_tns = float(offset_ns)
            executed_offsets[index] = cfg.laser_readout_offset_tns
            data = CountingDurationFineRes(cfg).acquire(progress=False)
            signal_on[index] = float(_array(data, "signal1"))
            signal_off[index] = float(_array(data, "signal2"))
            if progress:
                print(
                    f"readout window {index + 1}/{offsets.size} "
                    f"offset {executed_offsets[index]:.0f} ns",
                    end="\r",
                    flush=True,
                )
    if progress:
        print()

    norm = cfg.readout_integration_tns * 1e-9 * cfg.reps
    rate_on = signal_on / norm
    rate_off = signal_off / norm
    contrast = np.divide(
        rate_off - rate_on, rate_off, out=np.zeros_like(rate_off), where=rate_off != 0
    )
    result = ExperimentResult(
        kind="Readout_Window",
        x_name="Laser_readout_offset",
        x_unit="ns",
        x=executed_offsets,
        signal_counts=signal_on,
        reference_counts=signal_off,
        signal_rate_cps=rate_on,
        reference_rate_cps=rate_off,
        contrast=contrast,
        requested={
            "offsets_ns": offsets.tolist(),
            "window_ns": window_ns,
            "mw_pi_ns": mw_pi_ns,
            "reps": reps,
        },
        executed={
            "offsets_ns": executed_offsets.tolist(),
            "window_ns": cfg.readout_integration_tns,
            "mw_pi_ns": cfg.mw_pi_ftns,
            "mw_frequency_hz": cfg.mw_fGHz * 1e9,
            "laser_on_ns": cfg.laser_on_tns,
            "reference_start_ns": cfg.readout_reference_start_tns,
            "reps": cfg.reps,
            "mw_gain": cfg.mw_gain,
        },
    )
    result.fit = _fit_window(executed_offsets, contrast, rate_off)
    return result
