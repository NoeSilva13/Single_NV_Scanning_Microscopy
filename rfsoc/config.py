"""Validation and unit conversion for RFSoC4x2 programs."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np

from common import utils


@dataclass(frozen=True)
class ReadoutPlan:
    windows_per_pixel: int
    window_seconds: float
    effective_seconds: float
    samples_per_window: int


def expected_nqz(firmware: str, frequency_hz: float) -> int:
    """Return the RF-DAC Nyquist zone expected for a positive frequency."""
    sample_rate_hz = 9.8304e9 if firmware == "photon_counting_9ghz" else 4.9152e9
    if not 0 < frequency_hz < sample_rate_hz:
        raise ValueError(
            f"{frequency_hz / 1e9:.6g} GHz is outside the configured DAC range"
        )
    return int(frequency_hz // (sample_rate_hz / 2.0)) + 1


def validate_hardware_settings(frequency_hz: float | None = None) -> None:
    if utils.RFSOC_FIRMWARE not in {"photon_counting", "photon_counting_9ghz"}:
        raise ValueError(f"Unsupported RFSoC firmware: {utils.RFSOC_FIRMWARE}")
    if utils.RFSOC_EDGE_LOW_THRESHOLD >= utils.RFSOC_EDGE_HIGH_THRESHOLD:
        raise ValueError("RFSoC edge low threshold must be below high threshold")
    if utils.RFSOC_AOM_PMOD == utils.RFSOC_PIXEL_CLOCK_PMOD:
        raise ValueError("AOM and pixel clock must use different PMOD pins")
    if frequency_hz is not None:
        zone = expected_nqz(utils.RFSOC_FIRMWARE, frequency_hz)
        if zone != utils.RFSOC_MW_NQZ:
            raise ValueError(
                f"{frequency_hz / 1e9:.6g} GHz requires NQZ {zone} with "
                f"{utils.RFSOC_FIRMWARE}, configured {utils.RFSOC_MW_NQZ}"
            )


def readout_plan(
    dwell_seconds: float,
    readout_clock_hz: float,
    max_samples: int = utils.RFSOC_MAX_READOUT_SAMPLES,
) -> ReadoutPlan:
    """Split a requested dwell into legal, equally sized ADC windows."""
    if dwell_seconds <= 0 or readout_clock_hz <= 0:
        raise ValueError("dwell and readout clock must be positive")
    requested_samples = max(1, int(round(dwell_seconds * readout_clock_hz)))
    windows = int(math.ceil(requested_samples / max_samples))
    samples = int(math.ceil(requested_samples / windows))
    if samples > max_samples:
        raise AssertionError("readout window split exceeded hardware limit")
    window_seconds = samples / readout_clock_hz
    return ReadoutPlan(
        windows_per_pixel=windows,
        window_seconds=window_seconds,
        effective_seconds=windows * window_seconds,
        samples_per_window=samples,
    )


def validate_linear_sweep(values: Iterable[float], name: str) -> np.ndarray:
    values = np.asarray(list(values), dtype=float)
    if values.ndim != 1 or values.size < 2 or not np.all(np.isfinite(values)):
        raise ValueError(f"{name} must contain at least two finite values")
    delta = np.diff(values)
    if not np.allclose(delta, delta[0], rtol=1e-7, atol=1e-12):
        raise ValueError(f"{name} must be linear for a single FPGA acquire")
    return values


def readout_clock_hz(soccfg, adc_channel: int = utils.RFSOC_ADC_CHANNEL) -> float:
    """Extract the edge-counter sample clock from QickConfig."""
    cfg = soccfg["readouts"][adc_channel]
    for key in ("f_output", "fs"):
        if key in cfg:
            return float(cfg[key]) * 1e6
    raise KeyError("QickConfig does not expose the readout clock")


def base_nv_config(session, *, reps: int = 1):
    """Build a validated NVConfiguration after the client is connected."""
    validate_hardware_settings()
    cfg = session.new_config()
    cfg.adc_channel = utils.RFSOC_ADC_CHANNEL
    cfg.edge_counting = True
    cfg.high_threshold = utils.RFSOC_EDGE_HIGH_THRESHOLD
    cfg.low_threshold = utils.RFSOC_EDGE_LOW_THRESHOLD
    cfg.laser_gate_pmod = utils.RFSOC_AOM_PMOD
    cfg.mw_channel = utils.RFSOC_MW_CHANNEL
    cfg.mw_nqz = utils.RFSOC_MW_NQZ
    # NVAveragerProgram.check_cfg accesses mw_gain for every subclass.
    cfg.mw_gain = 0
    cfg.reps = int(reps)
    cfg.soft_avgs = 1
    cfg.pre_init = True
    return cfg
