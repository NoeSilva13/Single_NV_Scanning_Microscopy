from rfsoc.config import expected_nqz, readout_plan, validate_linear_sweep


def test_nyquist_zone_depends_on_firmware():
    assert expected_nqz("photon_counting", 2.87e9) == 2
    assert expected_nqz("photon_counting_9ghz", 2.87e9) == 1


def test_dwell_is_split_below_register_limit():
    plan = readout_plan(500e-6, 307.2e6)
    assert plan.windows_per_pixel == 3
    assert plan.samples_per_window <= 65535
    assert plan.effective_seconds >= 500e-6


def test_only_linear_hardware_sweeps_are_accepted():
    assert validate_linear_sweep([1, 2, 3], "x").tolist() == [1, 2, 3]
    try:
        validate_linear_sweep([1, 2, 4], "x")
    except ValueError:
        pass
    else:
        raise AssertionError("nonlinear sweep was accepted")
