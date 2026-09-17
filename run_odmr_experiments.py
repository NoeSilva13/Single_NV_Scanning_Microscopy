"""RFSoC4x2 experiment runner.

One subcommand per experiment::

    python run_odmr_experiments.py list
    python run_odmr_experiments.py pl --live
    python run_odmr_experiments.py cwodmr
    python run_odmr_experiments.py rabi
    python run_odmr_experiments.py cpmg -n 32 --set reps=20000

The configuration of every experiment lives in ``SETTINGS`` below and is meant
to be edited as the sample and the setup change; ``--set key=value`` overrides
one entry for a single run.  Each sweep is one QICK acquire, and the pulsed
experiments are built on the FineRes programs, whose pulses land on DAC samples
(about 0.2 ns) instead of on tProc cycles (about 3.3 ns).

This can run next to the confocal app: each experiment claims the board for the
duration of its sweep, so the app's live count plot goes quiet and resumes
afterwards.  A scan already in flight keeps the board, and the runner waits
``RFSOC_CLAIM_WAIT_S`` for it before giving up.  The live windows here are the
polite side of the same deal: they take the claim per update and skip an update
rather than interrupt a scan.
"""

import argparse
import ast
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

# --- Configuration ----------------------------------------------------------
# Sweep axes are written as (start, stop, points) for a linear sweep and as
# (start, stop) for an exponential one, where the scaling factor picks the
# points in between.

# The NV resonance, as found by ODMR.  The two ODMR experiments sweep across it
# instead of being told about it, so it is not part of the shared block.
MW_FREQUENCY_HZ = 2.846e9
# The pulse timing shared by every pulsed experiment.
PULSE_TIMING = {
    "mw_gain": 32_767,
    "laser_on_ns": 6_000,
    "reference_start_ns": 5_000,
    "mw_to_laser_delay_ns": 555,
    "relax_delay_ns": 2_000,
}
# Where to count and for how long, as recommended by the readout-window fit.
READOUT = {
    "readout_ns": 633,
    "laser_readout_offset_ns": 1_159,
}
# Pulse lengths, as measured by the Rabi fit, which reports mw_pi2_ns/mw_pi_ns.
MW_PI2_NS = 25.0
MW_PI_NS = 2 * MW_PI2_NS

SETTINGS = {
    "pl": {"integration_seconds": 0.2, "reps": 1, "relax_delay_ns": 50},
    "dark": {"integration_seconds": 0.2, "reps": 10, "relax_delay_ns": 50},
    "cwodmr": {
        "frequencies_hz": (2.80e9, 2.95e9, 80),
        "readout_ns": 100_000,
        "relax_delay_ns": 2_000,
        "reps": 5_000,
        "mw_gain": 5_000,
    },
    "podmr": {
        **PULSE_TIMING,
        **READOUT,
        "frequencies_hz": (2.80e9, 2.95e9, 80),
        "mw_duration_ns": MW_PI_NS,
        "reps": 50_000,
    },
    "readout-window": {
        **PULSE_TIMING,
        "mw_frequency_hz": MW_FREQUENCY_HZ,
        "window_ns": 100,
        "n_offsets": 40,
        "offset_start_ns": 0.0,
        "mw_pi_ns": MW_PI_NS,
        "reps": 10_000,
    },
    "rabi": {
        **PULSE_TIMING,
        **READOUT,
        "mw_frequency_hz": MW_FREQUENCY_HZ,
        # Two nanoseconds per step: ten DAC samples, and short enough to catch
        # the first half period of a strongly driven NV.
        "durations_ns": (4, 500, 249),
        "reps": 10_000,
    },
    "ramsey": {
        **PULSE_TIMING,
        **READOUT,
        "mw_frequency_hz": MW_FREQUENCY_HZ,
        "taus_ns": (100, 15_000, 150),
        "mw_pi2_ns": MW_PI2_NS,
        "scaling": "linear",
        "reps": 50_000,
    },
    "hahn": {
        **PULSE_TIMING,
        **READOUT,
        "mw_frequency_hz": MW_FREQUENCY_HZ,
        "taus_ns": (500, 2_000_000),
        "mw_pi2_ns": MW_PI2_NS,
        "scaling": "exponential",
        "scaling_factor": "3/2",
        "reps": 50_000,
    },
    "cpmg": {
        **PULSE_TIMING,
        **READOUT,
        "mw_frequency_hz": MW_FREQUENCY_HZ,
        "taus_ns": (500, 500_000),
        "mw_pi2_ns": MW_PI2_NS,
        "scaling": "exponential",
        "scaling_factor": "3/2",
        "n_pulses": 32,
        "reps": 50_000,
    },
    "t1": {
        **PULSE_TIMING,
        **READOUT,
        "mw_frequency_hz": MW_FREQUENCY_HZ,
        "delays_ns": (1_000, 30_000_000),
        "mw_pi_ns": MW_PI_NS,
        "scaling": "exponential",
        "scaling_factor": "9/8",
        "laser_on_ns": 50_000,
        "reference_start_ns": 40_000,
        "reps": 3_000,
    },
}

HELP = {
    "pl": "count photoluminescence for one window; --live traces it",
    "dark": "count with the laser gate low: detector and room background",
    "cwodmr": "continuous-wave ODMR spectrum; --live averages passes as they come",
    "podmr": "pulsed ODMR spectrum on PODMRFineRes",
    "readout-window": "walk a narrow counting window across the laser pulse",
    "rabi": "Rabi oscillation; fits the pi/2 and pi pulse lengths",
    "ramsey": "free precession between two pi/2 pulses: detuning and T2*",
    "hahn": "Hahn echo: one refocusing pulse, fits T2",
    "cpmg": "CPMG-N with XY8 phase cycling, fits the extended T2",
    "t1": "spin-lattice relaxation, fits T1",
}


def _sweep_axis(spec):
    """Build a sweep axis from its configuration entry.

    ``(start, stop, points)`` is a linear grid, ``(start, stop)`` is the two
    ends of an exponential one, and anything longer is taken as the explicit
    list of points.
    """
    values = list(spec)
    if len(values) == 3:
        return np.linspace(float(values[0]), float(values[1]), int(values[2]))
    return np.asarray(values, dtype=float)


def _overrides(assignments):
    """Parse ``--set key=value`` pairs into keyword arguments."""
    settings = {}
    for assignment in assignments or ():
        if "=" not in assignment:
            raise SystemExit(f"--set expects key=value, got {assignment!r}")
        key, _, raw = assignment.partition("=")
        try:
            settings[key.strip()] = ast.literal_eval(raw.strip())
        except (SyntaxError, ValueError):
            settings[key.strip()] = raw.strip()
    return settings


def _run_pl(session, settings, args):
    if args.live:
        point, plan = counting_source(session, "PL_Intensity", **settings)
        live_scalar(
            point,
            ylabel="Count rate (cps)",
            title=f"PL intensity, {plan.seconds * 1e3:.1f} ms window",
        )
        return None
    return pl_intensity(session, **settings)


def _run_dark(session, settings, args):
    return dark_counts(session, **settings)


def _run_cwodmr(session, settings, args):
    frequencies_hz = _sweep_axis(settings.pop("frequencies_hz"))
    if args.live:
        x_hz, one_pass = cw_odmr_source(session, frequencies_hz, **settings)
        live_curve(
            one_pass,
            x_hz / 1e9,
            xlabel="Frequency (GHz)",
            ylabel="Contrast",
            title="CW ODMR",
        )
        return None
    return cw_odmr(session, frequencies_hz, progress=args.progress, **settings)


def _run_podmr(session, settings, args):
    frequencies_hz = _sweep_axis(settings.pop("frequencies_hz"))
    return pulsed_odmr(session, frequencies_hz, progress=args.progress, **settings)


def _run_readout_window(session, settings, args):
    return readout_window(session, progress=args.progress, **settings)


def _run_rabi(session, settings, args):
    durations_ns = _sweep_axis(settings.pop("durations_ns"))
    return rabi(session, durations_ns, progress=args.progress, **settings)


def _run_ramsey(session, settings, args):
    taus_ns = _sweep_axis(settings.pop("taus_ns"))
    return ramsey(session, taus_ns, progress=args.progress, **settings)


def _run_hahn(session, settings, args):
    taus_ns = _sweep_axis(settings.pop("taus_ns"))
    return hahn_echo(session, taus_ns, progress=args.progress, **settings)


def _run_cpmg(session, settings, args):
    taus_ns = _sweep_axis(settings.pop("taus_ns"))
    if args.n_pulses is not None:
        settings["n_pulses"] = args.n_pulses
    return cpmg(session, taus_ns, progress=args.progress, **settings)


def _run_t1(session, settings, args):
    delays_ns = _sweep_axis(settings.pop("delays_ns"))
    return t1(session, delays_ns, progress=args.progress, **settings)


RUNNERS = {
    "pl": _run_pl,
    "dark": _run_dark,
    "cwodmr": _run_cwodmr,
    "podmr": _run_podmr,
    "readout-window": _run_readout_window,
    "rabi": _run_rabi,
    "ramsey": _run_ramsey,
    "hahn": _run_hahn,
    "cpmg": _run_cpmg,
    "t1": _run_t1,
}


def _common_flags():
    """Flags every subcommand takes, written after the subcommand name."""
    flags = argparse.ArgumentParser(add_help=False)
    flags.add_argument(
        "--no-save", dest="save", action="store_false",
        help="do not write the NPZ/CSV/PDF files",
    )
    flags.add_argument(
        "--no-plot", dest="plot", action="store_false",
        help="do not open a figure",
    )
    flags.add_argument(
        "--no-progress", dest="progress", action="store_false",
        help="do not print the sweep progress bar",
    )
    flags.add_argument(
        "--set", dest="overrides", action="append", metavar="KEY=VALUE",
        help="override one configuration entry for this run (repeatable)",
    )
    return flags


def build_parser():
    parser = argparse.ArgumentParser(
        description="Run one RFSoC4x2 experiment.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    flags = _common_flags()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "list",
        parents=[flags],
        help="print every experiment and its configuration",
    )
    for name, runner_help in HELP.items():
        command = commands.add_parser(name, parents=[flags], help=runner_help)
        if name in ("pl", "cwodmr"):
            command.add_argument(
                "--live", action="store_true",
                help="open a window that keeps measuring until it is closed",
            )
        if name == "cpmg":
            command.add_argument(
                "-n", "--n-pulses", type=int, default=None,
                help="number of refocusing pulses (default from SETTINGS)",
            )
    return parser


def print_catalog():
    for name, settings in SETTINGS.items():
        print(f"{name}: {HELP[name]}")
        for key, value in settings.items():
            print(f"    {key} = {value!r}")
        print()


def report(result, *, save, plot):
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
    if plot:
        plot_result(result, save=save)
    elif save:
        save_result(result)
    if result.fit:
        print("Fit:")
        for key, value in result.fit.items():
            print(f"  {key}: {value}")
    if result.saved_files:
        print("Saved:", result.saved_files)
    return result


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "list":
        print_catalog()
        return None
    settings = dict(SETTINGS[args.command])
    settings.update(_overrides(args.overrides))
    session = RFSoCSession().connect()
    result = RUNNERS[args.command](session, settings, args)
    return report(result, save=args.save, plot=args.plot)


if __name__ == "__main__":
    try:
        main()
    except RFSoCBusyError as exc:
        sys.exit(f"RFSoC unavailable: {exc}")
    except KeyboardInterrupt:
        sys.exit("Stopped")
