"""FPGA-swept CW and pulsed ODMR."""

from __future__ import annotations

import numpy as np

from rfsoc.config import base_nv_config, validate_hardware_settings, validate_linear_sweep
from .base import ExperimentResult, _array, normalized_result, spin_config


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
    validate_hardware_settings(float(requested_x.mean()))
    cfg = base_nv_config(session, reps=reps)
    cfg.readout_integration_tns = int(readout_ns)
    cfg.relax_delay_tns = int(relax_delay_ns)
    cfg.mw_gain = int(mw_gain)
    cfg.mw_start_fMHz = requested_x[0] / 1e6
    cfg.mw_end_fMHz = requested_x[-1] / 1e6
    cfg.nsweep_points = int(requested_x.size)
    with session.acquisition():
        data = session.qd.LockinODMR(cfg).acquire(progress=progress)

    signal = _array(data, "signal")
    reference = _array(data, "reference")
    x_mhz = _array(data, "frequencies")
    contrast = np.divide(
        reference - signal,
        reference,
        out=np.zeros_like(reference),
        where=reference != 0,
    )
    integration_s = cfg.readout_integration_tns * 1e-9
    norm = integration_s * cfg.reps
    return ExperimentResult(
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
    )
    cfg.mw_pi_ftns = int(mw_duration_ns)
    cfg.mw_start_fMHz = requested_x[0] / 1e6
    cfg.mw_end_fMHz = requested_x[-1] / 1e6
    cfg.nsweep_points = int(requested_x.size)
    with session.acquisition():
        from qickdawg.finetimingsuite import PODMRFineRes

        data = PODMRFineRes(cfg).acquire(progress=progress)
    x_hz = _array(data, "mw_fMHz") * 1e6
    return normalized_result(
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
        },
    )
