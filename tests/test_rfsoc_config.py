import pytest

from common.utils import RFSOC_MAX_COUNTING_WINDOW_S
from rfsoc.config import expected_nqz, readout_plan, validate_linear_sweep

READOUT_CLOCK_HZ = 307.2e6


def test_nyquist_zone_depends_on_firmware():
    assert expected_nqz("photon_counting", 2.87e9) == 2
    assert expected_nqz("photon_counting_9ghz", 2.87e9) == 1


def test_any_dwell_up_to_the_measured_window_is_counted_in_one_go():
    plan = readout_plan(1e-3, READOUT_CLOCK_HZ)
    assert plan.samples == 307200
    assert plan.seconds == 1e-3

    ceiling = readout_plan(RFSOC_MAX_COUNTING_WINDOW_S, READOUT_CLOCK_HZ)
    assert ceiling.samples == round(RFSOC_MAX_COUNTING_WINDOW_S * READOUT_CLOCK_HZ)


def test_a_dwell_past_the_measured_window_is_refused_not_split():
    with pytest.raises(ValueError, match="window_linearity"):
        readout_plan(RFSOC_MAX_COUNTING_WINDOW_S * 1.01, READOUT_CLOCK_HZ)


def test_only_linear_hardware_sweeps_are_accepted():
    assert validate_linear_sweep([1, 2, 3], "x").tolist() == [1, 2, 3]
    try:
        validate_linear_sweep([1, 2, 4], "x")
    except ValueError:
        pass
    else:
        raise AssertionError("nonlinear sweep was accepted")
