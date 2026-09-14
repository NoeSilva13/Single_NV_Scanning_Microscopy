"""Shared configuration and result types for native RFSoC experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from rfsoc.config import base_nv_config, validate_hardware_settings


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
    cfg.get_reference = True
    return cfg


def _array(data, name):
    try:
        return np.asarray(data[name], dtype=float)
    except (KeyError, TypeError):
        return np.asarray(getattr(data, name), dtype=float)


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
    signal_off = _array(data, "signal2")
    laser_ref_off = _array(data, "reference2")
    on_norm = np.divide(
        signal_on, laser_ref_on,
        out=np.zeros_like(signal_on), where=laser_ref_on != 0,
    )
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
