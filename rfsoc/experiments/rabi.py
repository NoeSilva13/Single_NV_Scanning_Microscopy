"""Fine-resolution FPGA Rabi sweep."""

from __future__ import annotations

from rfsoc.config import validate_linear_sweep
from .base import _array, normalized_result, spin_config


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
    )
    cfg.mw_duration_start_ftns = float(requested_x[0])
    cfg.mw_duration_end_ftns = float(requested_x[-1])
    cfg.nsweep_points = int(requested_x.size)
    with session.acquisition():
        from qickdawg.finetimingsuite import RabiFineRes

        data = RabiFineRes(cfg).acquire(progress=progress)
    x_ns = _array(data, "mw_duration_ftns")
    return normalized_result(
        kind="Rabi",
        x_name="MW_duration",
        x_unit="ns",
        x=x_ns,
        data=data,
        integration_seconds=cfg.readout_integration_tns * 1e-9,
        reps=cfg.reps,
        requested={
            "durations_ns": requested_x.tolist(),
            "mw_frequency_hz": mw_frequency_hz,
        },
        executed={
            "durations_ns": x_ns.tolist(),
            "mw_frequency_hz": cfg.mw_fGHz * 1e9,
            "readout_ns": cfg.readout_integration_tns,
            "reps": cfg.reps,
            "mw_gain": cfg.mw_gain,
        },
    )
