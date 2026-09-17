"""RFSoC4x2 experiment runner.

Edit/uncomment one block, then run ``python run_odmr_experiments.py``.
Each block lists every parameter of that experiment.  Each pulsed sweep is one
FineRes acquire: pulses land on DAC samples (about 0.2 ns) instead of on tProc
cycles (about 3.3 ns).

This can run next to the confocal app: each experiment claims the board for the
duration of its sweep, so the app's live count plot goes quiet and resumes
afterwards.  A scan already in flight keeps the board, and the runner waits
``RFSOC_CLAIM_WAIT_S`` for it before giving up.  The live windows here are the
polite side of the same deal: they take the claim per update and skip an update
rather than interrupt a scan.
"""

import sys

import numpy as np

from rfsoc.client import RFSoCSession
from rfsoc.experiments import (
    counting_source,
    cpmg,
    cw_odmr,
    cw_odmr_source,
    dark_counts,
    hahn_echo,
    pl_intensity,
    pulsed_odmr,
    rabi,
    ramsey,
    readout_window,
    t1,
)
from rfsoc.experiments.base import CountingResult
from rfsoc.experiments.io import live_curve, live_scalar, plot_result, save_result
from rfsoc.process_lock import RFSoCBusyError


def live_pl(session, **kwargs):
    """Trace photoluminescence until the window is closed or Ctrl+C is hit."""
    point, plan = counting_source(session, "PL_Intensity", **kwargs)
    live_scalar(
        point,
        ylabel="Count rate (cps)",
        title=f"PL intensity, {plan.seconds * 1e3:.1f} ms window",
    )


def live_cwodmr(session, frequencies_hz, **kwargs):
    """Average CW ODMR passes into a live spectrum until the window is closed."""
    x_hz, one_pass = cw_odmr_source(session, frequencies_hz, **kwargs)
    live_curve(
        one_pass,
        x_hz / 1e9,
        xlabel="Frequency (GHz)",
        ylabel="Contrast",
        title="CW ODMR",
    )


def report(result):
    """Save, plot and print whatever the experiment returned."""
    if result is None:
        return None
    if isinstance(result, CountingResult):
        print(
            f"{result.kind}: {result.counts} counts in "
            f"{result.window_seconds * 1e3:.3f} ms x {result.reps} reps "
            f"= {result.rate_cps:.0f} cps ({result.rate_cps / 1e6:.4f} Mcps)"
        )
        return result
    plot_result(result)
    if result.fit:
        print("Fit:")
        for key, value in result.fit.items():
            print(f"  {key}: {value}")
    if result.saved_files:
        print("Saved:", result.saved_files)
    return result


def main():
    session = RFSoCSession().connect()
    result = None

    # 1. PL Intensity.  Uncomment live_pl to keep a trace open until Ctrl+C.
    result = pl_intensity(session, integration_seconds=0.2, reps=1, relax_delay_ns=50)
    # live_pl(session, integration_seconds=0.2, reps=1, relax_delay_ns=50)

    # 2. Dark Counts
    # result = dark_counts(session, integration_seconds=0.2, reps=10, relax_delay_ns=50)

    # 3. CW ODMR.  Uncomment live_cwodmr to average passes as they arrive.
    # result = cw_odmr(
    #     session,
    #     np.linspace(2.80e9, 2.95e9, 80),
    #     readout_ns=100_000,
    #     relax_delay_ns=2_000,
    #     reps=5_000,
    #     mw_gain=5_000,
    # )
    # live_cwodmr(
    #     session,
    #     np.linspace(2.80e9, 2.95e9, 80),
    #     readout_ns=100_000,
    #     relax_delay_ns=2_000,
    #     reps=900,
    #     mw_gain=5_000,
    # )

    # 4. Pulsed ODMR
    # result = pulsed_odmr(
    #     session,
    #     np.linspace(2.80e9, 2.95e9, 80),
    #     mw_duration_ns=50.0,
    #     laser_on_ns=6_000,
    #     readout_ns=633,
    #     laser_readout_offset_ns=1_159,
    #     reference_start_ns=5_000,
    #     mw_to_laser_delay_ns=555,
    #     relax_delay_ns=2_000,
    #     reps=50_000,
    #     mw_gain=32_767,
    # )

    # 5. Calibrate the readout window
    # result = readout_window(
    #     session,
    #     window_ns=100,
    #     n_offsets=40,
    #     offset_start_ns=0.0,
    #     mw_frequency_hz=2.846e9,
    #     mw_pi_ns=50.0,
    #     mw_gain=32_767,
    #     laser_on_ns=6_000,
    #     reference_start_ns=5_000,
    #     mw_to_laser_delay_ns=555,
    #     relax_delay_ns=2_000,
    #     reps=10_000,
    # )

    # 6. Rabi.  Two nanoseconds per step: ten DAC samples.
    # result = rabi(
    #     session,
    #     np.linspace(4, 500, 249),
    #     mw_frequency_hz=2.846e9,
    #     laser_on_ns=6_000,
    #     readout_ns=633,
    #     laser_readout_offset_ns=1_159,
    #     reference_start_ns=5_000,
    #     mw_to_laser_delay_ns=555,
    #     relax_delay_ns=2_000,
    #     reps=10_000,
    #     mw_gain=32_767,
    # )

    # 7. Ramsey
    # result = ramsey(
    #     session,
    #     np.linspace(100, 15_000, 150),
    #     mw_frequency_hz=2.846e9,
    #     mw_pi2_ns=25.0,
    #     laser_on_ns=6_000,
    #     readout_ns=633,
    #     laser_readout_offset_ns=1_159,
    #     reference_start_ns=5_000,
    #     mw_to_laser_delay_ns=555,
    #     relax_delay_ns=2_000,
    #     reps=50_000,
    #     mw_gain=32_767,
    # )

    # 8. Hahn Echo
    # result = hahn_echo(
    #     session,
    #     [500, 2_000_000],
    #     scaling="exponential",
    #     scaling_factor="3/2",
    #     mw_frequency_hz=2.846e9,
    #     mw_pi2_ns=25.0,
    #     laser_on_ns=6_000,
    #     readout_ns=633,
    #     laser_readout_offset_ns=1_159,
    #     reference_start_ns=5_000,
    #     mw_to_laser_delay_ns=555,
    #     relax_delay_ns=2_000,
    #     reps=50_000,
    #     mw_gain=32_767,
    # )

    # 9. CPMG-N
    # result = cpmg(
    #     session,
    #     [500, 500_000],
    #     n_pulses=32,
    #     scaling="exponential",
    #     scaling_factor="3/2",
    #     mw_frequency_hz=2.846e9,
    #     mw_pi2_ns=25.0,
    #     laser_on_ns=6_000,
    #     readout_ns=633,
    #     laser_readout_offset_ns=1_159,
    #     reference_start_ns=5_000,
    #     mw_to_laser_delay_ns=555,
    #     relax_delay_ns=2_000,
    #     reps=50_000,
    #     mw_gain=32_767,
    # )

    # 10. T1
    # result = t1(
    #     session,
    #     [1_000, 30_000_000],
    #     scaling="exponential",
    #     scaling_factor="9/8",
    #     mw_frequency_hz=2.846e9,
    #     mw_pi_ns=50.0,
    #     laser_on_ns=50_000,
    #     readout_ns=633,
    #     laser_readout_offset_ns=1_159,
    #     reference_start_ns=40_000,
    #     mw_to_laser_delay_ns=555,
    #     relax_delay_ns=2_000,
    #     reps=3_000,
    #     mw_gain=32_767,
    # )

    return report(result)


if __name__ == "__main__":
    try:
        main()
    except RFSoCBusyError as exc:
        sys.exit(f"RFSoC unavailable: {exc}")
    except KeyboardInterrupt:
        sys.exit("Stopped")
