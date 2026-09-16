from rfsoc.diagnostics import (
    PROBE_GAP_SECONDS,
    TPROC_MAX_IMMEDIATE_TREG,
    probe_window_ladder,
    window_probe_plan,
)

READOUT_CLOCK_HZ = 307.2e6
GAP_TREG = int(round(PROBE_GAP_SECONDS * READOUT_CLOCK_HZ))


def shot_seconds(probe):
    return probe.seconds + GAP_TREG / READOUT_CLOCK_HZ


def test_the_ladder_brackets_every_candidate_counter_width():
    lengths = probe_window_ladder(READOUT_CLOCK_HZ, 5.0)
    assert lengths[0] == 2 ** 12
    assert 2 ** 30 in lengths
    assert lengths[-1] == 1_536_000_000
    assert lengths == sorted(set(lengths))


def test_a_ceiling_below_the_first_window_is_refused():
    try:
        probe_window_ladder(READOUT_CLOCK_HZ, 1e-6)
    except ValueError:
        pass
    else:
        raise AssertionError("a ceiling below the first window was accepted")


def test_shots_are_spent_where_they_buy_precision():
    plan = window_probe_plan(
        [4096, 307200, 1_536_000_000],
        READOUT_CLOCK_HZ,
        GAP_TREG,
        budget_seconds=4.0,
        max_reps=8192,
    )
    reps = [probe.reps for probe in plan]
    assert reps[0] == 8192
    assert reps[-1] == 1
    assert reps == sorted(reps, reverse=True)


def test_no_window_spends_more_than_its_budget():
    lengths = probe_window_ladder(READOUT_CLOCK_HZ, 5.0)
    plan = window_probe_plan(lengths, READOUT_CLOCK_HZ, GAP_TREG, budget_seconds=4.0)
    for probe in plan:
        # A single shot longer than the budget is the one unavoidable overrun.
        assert probe.reps == 1 or probe.reps * shot_seconds(probe) <= 4.0
    total = sum(probe.reps * shot_seconds(probe) for probe in plan)
    assert total < 120.0


def test_a_window_the_tproc_cannot_schedule_is_refused():
    try:
        window_probe_plan(
            [int(7.0 * READOUT_CLOCK_HZ)], READOUT_CLOCK_HZ, GAP_TREG
        )
    except ValueError as exc:
        assert "31-bit immediate" in str(exc)
    else:
        raise AssertionError("an unschedulable window was accepted")


def test_the_longest_schedulable_window_is_still_accepted():
    length = TPROC_MAX_IMMEDIATE_TREG - GAP_TREG - 270
    plan = window_probe_plan([length], READOUT_CLOCK_HZ, GAP_TREG)
    assert plan[0].reps == 1
    assert plan[0].seconds < 7.0
