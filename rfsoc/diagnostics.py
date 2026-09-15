"""Manual RFSoC4x2 bring-up checks.

Run individual checks at the bench; they intentionally never guess wiring or
silently continue after a firmware mismatch.
"""

from __future__ import annotations

import json

from common import utils
from .client import RFSoCSession
from .config import (
    expected_nqz,
    readout_clock_hz,
    validate_hardware_settings,
)


def connection_report(session=None):
    session = session or RFSoCSession()
    session.connect()
    cfg = session.soc.get_cfg()
    report = {
        "host": session.host,
        "server_name": session.server_name,
        "expected_firmware": utils.RFSOC_FIRMWARE,
        "adc_channel": utils.RFSOC_ADC_CHANNEL,
        "readout_clock_hz": readout_clock_hz(
            session.soccfg, utils.RFSOC_ADC_CHANNEL
        ),
        "mw_channel": utils.RFSOC_MW_CHANNEL,
        "mw_nqz": utils.RFSOC_MW_NQZ,
        "aom_pmod": utils.RFSOC_AOM_PMOD,
        "pixel_clock_pmod": utils.RFSOC_PIXEL_CLOCK_PMOD,
        "soc_cfg": cfg,
    }
    return report


def validate_mw_frequency(frequency_hz=2.87e9):
    validate_hardware_settings(frequency_hz)
    return {
        "frequency_hz": frequency_hz,
        "firmware": utils.RFSOC_FIRMWARE,
        "expected_nqz": expected_nqz(utils.RFSOC_FIRMWARE, frequency_hz),
    }


def edge_count_rate(integration_seconds=None, reps=10, session=None):
    """Collect repeated PL edge counts for threshold/linearity bench tests.

    The edge counter uses a 16-bit window, so a single diagnostic acquire must
    stay below ``RFSOC_MAX_READOUT_SAMPLES / readout_clock`` (~213 µs at
    307.2 MHz). Defaults to 100 µs when *integration_seconds* is omitted.
    """
    from .config import base_nv_config, readout_plan

    session = session or RFSoCSession()
    session.connect()
    with session.acquisition():
        cfg = base_nv_config(session, reps=reps)
        clock = readout_clock_hz(session.soccfg, cfg.adc_channel)
        max_seconds = utils.RFSOC_MAX_READOUT_SAMPLES / clock
        if integration_seconds is None:
            integration_seconds = min(100e-6, max_seconds)
        plan = readout_plan(integration_seconds, clock)
        if plan.windows_per_pixel != 1:
            raise ValueError(
                "Diagnostic window exceeds one hardware window "
                f"(max {max_seconds * 1e6:.1f} µs at {clock / 1e6:.1f} MHz); "
                "reduce integration"
            )
        cfg.readout_integration_treg = plan.samples_per_window
        cfg.relax_delay_treg = 1
        total = int(session.qd.PLIntensity(cfg).acquire(progress=False))
    return {
        "total_counts": total,
        "reps": reps,
        "integration_seconds": plan.effective_seconds,
        "count_rate_cps": total / (reps * plan.effective_seconds),
        "high_threshold": cfg.high_threshold,
        "low_threshold": cfg.low_threshold,
    }


def main():
    validate_hardware_settings()
    print(json.dumps(connection_report(), indent=2, default=str))
    print(json.dumps(validate_mw_frequency(), indent=2))
    print(
        "Next bench checks: inspect AOM/pixel-clock PMOD with an oscilloscope; "
        "then run edge_count_rate() while sweeping safe conditioned TTL levels."
    )


if __name__ == "__main__":
    main()
