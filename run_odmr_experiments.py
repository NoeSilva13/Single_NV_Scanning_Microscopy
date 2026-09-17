"""RFSoC4x2 experiment runner.

Edit/uncomment one block, then run ``python run_odmr_experiments.py``.
Every experiment performs one QICK acquire for its complete FPGA sweep.

This can run next to the confocal app: each experiment claims the board for the
duration of its sweep, so the app's live count plot goes quiet and resumes
afterwards.  A scan already in flight keeps the board, and the runner waits
``RFSOC_CLAIM_WAIT_S`` for it before giving up.
"""

import sys

import numpy as np

from rfsoc.client import RFSoCSession
from rfsoc.experiments import cw_odmr, pulsed_odmr, rabi, t1
from rfsoc.experiments.io import plot_result, save_result
from rfsoc.process_lock import RFSoCBusyError


def main():
    session = RFSoCSession().connect()

    # 1. CW ODMR
    result = cw_odmr(
        session,
        np.linspace(2.80e9, 2.95e9, 80),
        readout_ns=100_000,
        reps=5_000,
        mw_gain=5_000,
    )

    # 2. Pulsed ODMR
    # result = pulsed_odmr(
    #     session,
    #     np.linspace(2.80e9, 2.95e9, 80),
    #     mw_duration_ns=1_000,
    #     reps=100_000,
    #     mw_gain=5_000,
    # )

    # 3. Rabi (active)
    # result = rabi(
    #     session,
    #     np.linspace(0, 1_008, 128),
    #     mw_frequency_hz=2.846e9,
    #     reps=100_000,
    #     mw_gain=5_000,
    # )

    # 4. T1
    # result = t1(
    #     session,
    #     np.linspace(0, 30e6, 50),
    #     scaling="linear",
    #     mw_frequency_hz=2.846e9,
    #     mw_pi_ns=1_000,
    #     reps=3_000,
    # )

    save_result(result)
    plot_result(result)
    print("Saved:", result.saved_files)


if __name__ == "__main__":
    try:
        main()
    except RFSoCBusyError as exc:
        sys.exit(f"RFSoC unavailable: {exc}")
