"""Counted photoluminescence: one PL point, dark counts, and live traces.

Both programs count for a single window: ``PLIntensity`` gates the laser while
it counts, ``DarkCounts`` triggers only the ADC and leaves the laser gate low,
so the difference between them is the detector and room background.
"""

from __future__ import annotations

from rfsoc.config import (
    base_nv_config,
    edge_counting_warnings_muted,
    readout_clock_hz,
    readout_plan,
)
from rfsoc.process_lock import RFSoCBusyError
from .base import CountingResult

_PROGRAMS = {"PL_Intensity": "PLIntensity", "Dark_Counts": "DarkCounts"}


def _counting_program(session, kind, *, integration_seconds, reps, relax_delay_ns):
    """Compile one counting program and report the window it will count for.

    The window is expressed through ``readout_plan()`` rather than through
    QICK-DAWG's ``max_int_time_treg``, which is fixed at 2**16-1 samples: that
    ceiling comes from the analog sum buffer, and ``window_linearity()`` measured
    this board counting edges linearly far past it.
    """
    if kind not in _PROGRAMS:
        raise ValueError(f"unknown counting program: {kind}")
    qd = session.qd
    cfg = base_nv_config(session, reps=reps)
    plan = readout_plan(
        integration_seconds, readout_clock_hz(session.soccfg, cfg.adc_channel)
    )
    cfg.readout_integration_treg = plan.samples
    cfg.relax_delay_tns = int(relax_delay_ns)
    with edge_counting_warnings_muted():
        program = getattr(qd, _PROGRAMS[kind])(cfg)
    return program, plan


def counted_point(
    session,
    kind="PL_Intensity",
    *,
    integration_seconds=0.2,
    reps=1,
    relax_delay_ns=50,
):
    """Count one point with *kind* and return it as counts and as a rate."""
    program, plan = _counting_program(
        session,
        kind,
        integration_seconds=integration_seconds,
        reps=reps,
        relax_delay_ns=relax_delay_ns,
    )
    with session.acquisition():
        counts = int(program.acquire(progress=False))
    return CountingResult(
        kind=kind,
        counts=counts,
        window_seconds=plan.seconds,
        reps=int(reps),
        requested={
            "integration_seconds": integration_seconds,
            "reps": reps,
            "relax_delay_ns": relax_delay_ns,
        },
        executed={
            "integration_seconds": plan.seconds,
            "integration_samples": plan.samples,
            "reps": int(reps),
            "relax_delay_ns": relax_delay_ns,
        },
    )


def pl_intensity(session, **kwargs):
    """Count photoluminescence for one window with the laser gated on."""
    return counted_point(session, "PL_Intensity", **kwargs)


def dark_counts(session, **kwargs):
    """Count for one window with the laser gate left low: detector background."""
    return counted_point(session, "Dark_Counts", **kwargs)


def counting_source(
    session,
    kind="PL_Intensity",
    *,
    integration_seconds=0.2,
    reps=1,
    relax_delay_ns=50,
):
    """Return a callable that counts one point every time it is called.

    The program is compiled once, so a live trace re-arms the same assembly
    several times a second instead of rebuilding it.  The claim is taken per
    point and never waited for: a live trace is worth less than the scan or the
    experiment it would abort, so a busy board yields ``None`` and a gap in the
    trace instead of a turn.
    """
    program, plan = _counting_program(
        session,
        kind,
        integration_seconds=integration_seconds,
        reps=reps,
        relax_delay_ns=relax_delay_ns,
    )
    norm = plan.seconds * int(reps)

    def point():
        try:
            with session.acquisition(blocking=False):
                return int(program.acquire(progress=False)) / norm
        except RFSoCBusyError:
            return None

    return point, plan
