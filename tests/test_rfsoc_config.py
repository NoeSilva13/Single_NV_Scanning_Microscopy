from common.utils import RFSOC_MAX_COUNTING_WINDOW_S
from rfsoc.config import expected_nqz, readout_plan, validate_linear_sweep

READOUT_CLOCK_HZ = 307.2e6


def test_nyquist_zone_depends_on_firmware():
    assert expected_nqz("photon_counting", 2.87e9) == 2
    assert expected_nqz("photon_counting_9ghz", 2.87e9) == 1


def test_an_ordinary_dwell_is_integrated_in_one_window():
    plan = readout_plan(1e-3, READOUT_CLOCK_HZ)
    assert plan.windows_per_pixel == 1
    assert plan.samples_per_window == 307200
    assert plan.effective_seconds == 1e-3


def test_dwell_beyond_the_validated_window_is_split_and_summed():
    plan = readout_plan(5e-3, READOUT_CLOCK_HZ)
    assert plan.windows_per_pixel == 3
    assert plan.samples_per_window <= RFSOC_MAX_COUNTING_WINDOW_S * READOUT_CLOCK_HZ
    assert plan.effective_seconds >= 5e-3


def test_only_linear_hardware_sweeps_are_accepted():
    assert validate_linear_sweep([1, 2, 3], "x").tolist() == [1, 2, 3]
    try:
        validate_linear_sweep([1, 2, 4], "x")
    except ValueError:
        pass
    else:
        raise AssertionError("nonlinear sweep was accepted")
