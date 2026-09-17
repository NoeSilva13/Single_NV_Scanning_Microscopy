"""Coherence sweeps on CPMGXYFineRes: Ramsey, Hahn echo and CPMG-N.

One program covers all three, because they are the same sequence with a
different number of refocusing pulses between the two pi/2 pulses: none for
Ramsey, which decays in T2*, one for the Hahn echo, which decays in T2, and N
for CPMG, which pushes T2 out by refocusing faster noise.  The refocusing
pulses alternate X and Y in blocks of eight, so a pulse-length error that would
otherwise accumulate over N pulses partly cancels.
"""

from __future__ import annotations

import numpy as np

from rfsoc.config import validate_linear_sweep
from .base import (
    EXP_SCALING_FACTORS,
    _array,
    fine_sweep,
    fit_curve,
    normalized_result,
    oscillation_spectrum,
    spin_config,
)


def _decay_model(t_ns, amplitude, t2_ns, offset):
    return amplitude * np.exp(-t_ns / t2_ns) + offset


def _ramsey_model(t_ns, amplitude, detuning_mhz, t2_star_ns, offset):
    phase = 2 * np.pi * detuning_mhz * 1e-3 * t_ns
    return amplitude * np.cos(phase) * np.exp(-t_ns / t2_star_ns) + offset


def ramsey_spectrum(result):
    """Spectrum of a Ramsey trace: the detuning, and any resolved hyperfine.

    The precession is read out as a beat between the drive and the transition,
    so the spectrum peaks at the detuning, and at the detuning plus the nitrogen
    hyperfine splitting when the sweep is long enough to resolve it.
    """
    return oscillation_spectrum(result.x, result.contrast)


def _fit_ramsey(result):
    t_ns = np.asarray(result.x, dtype=float)
    y = np.asarray(result.contrast, dtype=float)
    frequencies_hz, _, peaks_hz = ramsey_spectrum(result)
    # The spectrum is a far better first guess for the frequency than anything
    # a decaying cosine fit would find on its own.
    guess_mhz = float(peaks_hz[0]) / 1e6 if peaks_hz.size else 1.0
    popt, errors = fit_curve(
        _ramsey_model,
        t_ns,
        y,
        p0=[
            float(np.ptp(y) / 2),
            guess_mhz,
            max(float(t_ns[-1]), 1.0),
            float(np.mean(y)),
        ],
        bounds=(
            [-np.inf, 0.0, 1e-3, -np.inf],
            [np.inf, np.inf, np.inf, np.inf],
        ),
    )
    fit = {"fft_peaks_hz": [float(peak) for peak in peaks_hz[:4]]}
    if frequencies_hz.size:
        fit["fft_resolution_hz"] = float(frequencies_hz[1])
    if popt is not None:
        fit.update(
            amplitude=float(popt[0]),
            detuning_hz=float(popt[1]) * 1e6,
            detuning_error_hz=float(errors[1]) * 1e6,
            t2_star_seconds=float(popt[2]) * 1e-9,
            t2_star_error_seconds=float(errors[2]) * 1e-9,
            offset=float(popt[3]),
        )
    result.fit = fit
    return result


def _fit_decay(result):
    t_ns = np.asarray(result.x, dtype=float)
    y = np.asarray(result.contrast, dtype=float)
    popt, errors = fit_curve(
        _decay_model,
        t_ns,
        y,
        p0=[float(y[0] - y[-1]), max(float(np.median(t_ns)), 1.0), float(y[-1])],
        bounds=([-np.inf, 1e-3, -np.inf], [np.inf, np.inf, np.inf]),
    )
    if popt is None:
        result.fit = None
        return result
    result.fit = {
        "amplitude": float(popt[0]),
        "t2_seconds": float(popt[1]) * 1e-9,
        "t2_error_seconds": float(errors[1]) * 1e-9,
        "offset": float(popt[2]),
    }
    return result


def fitted_curve(result):
    """Sample the fitted coherence decay, and label T2 or T2* and the detuning."""
    fit = result.fit
    if not fit:
        return None
    x = np.linspace(float(result.x[0]), float(result.x[-1]), 512)
    if "t2_star_seconds" in fit:
        y = _ramsey_model(
            x,
            fit["amplitude"],
            fit["detuning_hz"] / 1e6,
            fit["t2_star_seconds"] * 1e9,
            fit["offset"],
        )
        label = (
            f"T2* {fit['t2_star_seconds'] * 1e6:.3f} us\n"
            f"detuning {fit['detuning_hz'] / 1e6:.3f} MHz"
        )
        return x, y, label
    if "t2_seconds" in fit:
        y = _decay_model(x, fit["amplitude"], fit["t2_seconds"] * 1e9, fit["offset"])
        return x, y, f"T2 {fit['t2_seconds'] * 1e6:.3f} us"
    return None


def _coherence_sweep(
    session,
    taus_ns,
    *,
    kind,
    n_cpmg,
    scaling="linear",
    scaling_factor="3/2",
    mw_frequency_hz=2.87e9,
    mw_pi2_ns=25.0,
    laser_on_ns=6_000,
    readout_ns=633,
    laser_readout_offset_ns=1_159,
    reference_start_ns=5_000,
    mw_to_laser_delay_ns=555,
    relax_delay_ns=2_000,
    reps=10_000,
    mw_gain=32_767,
    get_reference=True,
    progress=True,
):
    """Sweep the free precession time tau with *n_cpmg* refocusing pulses.

    ``tau`` is the delay between pulses, so the total precession time grows with
    ``n_cpmg``; the reported axis is tau, as the program sweeps it.
    """
    requested_x = np.asarray(list(taus_ns), dtype=float)
    if requested_x.size < 2 or np.any(requested_x <= 0):
        raise ValueError("taus_ns must contain at least two positive values")
    if scaling == "linear":
        validate_linear_sweep(requested_x, "taus_ns")
    elif scaling == "exponential":
        if scaling_factor not in EXP_SCALING_FACTORS:
            raise ValueError(f"unsupported exponential factor: {scaling_factor}")
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
        # CPMGXYFineRes builds its pi pulses as two pi/2 pulses back to back.
        mw_pi2_ns=mw_pi2_ns,
        n_cpmg=n_cpmg,
        get_reference=get_reference,
    )
    if scaling == "linear":
        fine_sweep(cfg, "tau", requested_x)
    else:
        cfg.add_exponential_sweep(
            "tau",
            "ftus",
            float(requested_x[0]) / 1e3,
            float(requested_x[-1]) / 1e3,
            scaling_factor=scaling_factor,
        )
    with session.acquisition():
        from qickdawg.finetimingsuite import CPMGXYFineRes

        data = CPMGXYFineRes(cfg).acquire(progress=progress)
    x_ns = _array(data, "tau_ftns")
    result = normalized_result(
        kind=kind,
        x_name="Tau",
        x_unit="ns",
        x=x_ns,
        data=data,
        integration_seconds=cfg.readout_integration_tns * 1e-9,
        reps=cfg.reps,
        requested={
            "taus_ns": requested_x.tolist(),
            "scaling": scaling,
            "scaling_factor": scaling_factor,
            "n_cpmg": n_cpmg,
            "mw_pi2_ns": mw_pi2_ns,
        },
        executed={
            "taus_ns": x_ns.tolist(),
            "n_cpmg": cfg.n_cpmg,
            "mw_pi2_ns": cfg.mw_pi2_ftns,
            "mw_frequency_hz": cfg.mw_fGHz * 1e9,
            "readout_ns": cfg.readout_integration_tns,
            "reps": cfg.reps,
            "mw_gain": cfg.mw_gain,
            "get_reference": cfg.get_reference,
        },
    )
    return _fit_ramsey(result) if n_cpmg == 0 else _fit_decay(result)


def ramsey(session, taus_ns, **kwargs):
    """Free precession between two pi/2 pulses: detuning and T2*."""
    return _coherence_sweep(session, taus_ns, kind="Ramsey", n_cpmg=0, **kwargs)


def hahn_echo(session, taus_ns, *, scaling="exponential", **kwargs):
    """One refocusing pulse between the two pi/2 pulses: T2.

    The delay is swept exponentially by default, because an echo decay spanning
    three decades is wasted on a linear grid.
    """
    return _coherence_sweep(
        session, taus_ns, kind="Hahn_Echo", n_cpmg=1, scaling=scaling, **kwargs
    )


def cpmg(session, taus_ns, *, n_pulses=32, scaling="exponential", **kwargs):
    """*n_pulses* refocusing pulses, alternating X and Y in blocks of eight."""
    if int(n_pulses) < 1:
        raise ValueError("CPMG needs at least one refocusing pulse")
    return _coherence_sweep(
        session,
        taus_ns,
        kind=f"CPMG_{int(n_pulses)}",
        n_cpmg=int(n_pulses),
        scaling=scaling,
        **kwargs,
    )
