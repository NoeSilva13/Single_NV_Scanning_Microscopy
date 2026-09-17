import numpy as np
import pytest

import run_odmr_experiments as cli

# Imported from their modules rather than from the package, whose re-exported
# experiment functions shadow the modules of the same name.
from rfsoc.experiments.base import (
    CountingResult,
    ExperimentResult,
    fine_sweep,
    normalized_result,
)
from rfsoc.experiments.counting import counted_point
from rfsoc.experiments.cpmg import (
    _coherence_sweep,
    _fit_decay,
    _fit_ramsey,
    ramsey_spectrum,
)
from rfsoc.experiments.io import fitted_curve
from rfsoc.experiments.odmr import _fit_resonance, cw_odmr, pulsed_odmr
from rfsoc.experiments.rabi import _fit_rabi, rabi
from rfsoc.experiments.readout_window import _fit_window, readout_window
from rfsoc.experiments.t1 import _fit_t1, t1


class FakeConfig(dict):
    """Stands in for NVConfiguration where only the written keys matter."""

    def __setitem__(self, key, value):
        super().__setitem__(key, value)

    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc


def sweep_result(kind, x, y, x_unit="ns"):
    """An ExperimentResult carrying a synthetic curve to fit."""
    zeros = np.zeros_like(np.asarray(x, dtype=float))
    return ExperimentResult(
        kind=kind,
        x_name="x",
        x_unit=x_unit,
        x=np.asarray(x, dtype=float),
        signal_counts=zeros,
        reference_counts=zeros,
        signal_rate_cps=zeros,
        reference_rate_cps=zeros,
        contrast=np.asarray(y, dtype=float),
    )


def test_native_contrast_uses_laser_normalized_signal_and_reference():
    data = {
        "signal1": np.array([80, 45]),
        "reference1": np.array([100, 50]),
        "signal2": np.array([100, 50]),
        "reference2": np.array([100, 50]),
    }
    result = normalized_result(
        kind="Rabi",
        x_name="duration",
        x_unit="ns",
        x=[0, 1],
        data=data,
        integration_seconds=1e-3,
        reps=10,
        requested={},
        executed={},
    )
    np.testing.assert_allclose(result.contrast, [0.2, 0.1])
    np.testing.assert_allclose(result.signal_rate_cps, [8000, 4500])


def test_t1_result_is_signal_over_reference():
    data = {
        "signal1": np.array([50]),
        "reference1": np.array([100]),
        "signal2": np.array([100]),
        "reference2": np.array([100]),
    }
    result = normalized_result(
        kind="T1",
        x_name="delay",
        x_unit="ns",
        x=[1],
        data=data,
        integration_seconds=1,
        reps=1,
        requested={},
        executed={},
        t1_ratio=True,
    )
    np.testing.assert_allclose(result.contrast, [0.5])


def test_a_sweep_without_the_mw_off_reference_falls_back_to_the_laser_reference():
    # get_reference=False halves the sweep by dropping the MW-off readouts, so
    # signal2/reference2 are simply absent from what the program returns.
    data = {"signal1": np.array([80.0, 45.0]), "reference1": np.array([100.0, 50.0])}
    result = normalized_result(
        kind="Rabi",
        x_name="duration",
        x_unit="ns",
        x=[0, 1],
        data=data,
        integration_seconds=1e-3,
        reps=10,
        requested={},
        executed={},
    )
    np.testing.assert_allclose(result.contrast, [0.8, 0.9])
    np.testing.assert_allclose(result.reference_counts, [100.0, 50.0])


def test_a_counted_point_reports_a_rate_per_window_and_rep():
    result = CountingResult(
        kind="PL_Intensity", counts=6_000, window_seconds=0.2, reps=3
    )
    assert result.rate_cps == pytest.approx(10_000)


def test_fine_sweep_writes_the_three_attributes_the_programs_read():
    cfg = FakeConfig()
    values = fine_sweep(cfg, "tau", np.linspace(100, 1_000, 10))
    assert cfg["tau_start_ftns"] == pytest.approx(100)
    assert cfg["tau_end_ftns"] == pytest.approx(1_000)
    assert cfg["nsweep_points"] == 10
    assert cfg["scaling_mode"] == "linear"
    np.testing.assert_allclose(values, np.linspace(100, 1_000, 10))


def test_fine_sweep_refuses_an_uneven_axis():
    cfg = FakeConfig()
    with pytest.raises(ValueError):
        fine_sweep(cfg, "tau", [100, 200, 400])


def test_the_rabi_fit_recovers_the_pi_pulse_from_a_damped_oscillation():
    durations_ns = np.linspace(0, 500, 251)
    contrast = (
        -0.15
        * np.cos(2 * np.pi * durations_ns / 100)
        * np.exp(-durations_ns / 800)
        + 0.15
    )
    fit = _fit_rabi(sweep_result("Rabi", durations_ns, contrast)).fit
    assert fit["rabi_period_ns"] == pytest.approx(100, rel=0.01)
    assert fit["mw_pi_ns"] == pytest.approx(50, rel=0.01)
    assert fit["mw_pi2_ns"] == pytest.approx(25, rel=0.01)
    assert fit["rabi_frequency_hz"] == pytest.approx(10e6, rel=0.01)


def test_the_ramsey_fit_recovers_the_detuning_and_t2_star():
    taus_ns = np.linspace(100, 15_000, 150)
    contrast = (
        0.1 * np.cos(2 * np.pi * 2e-3 * taus_ns) * np.exp(-taus_ns / 3_000) + 0.2
    )
    result = _fit_ramsey(sweep_result("Ramsey", taus_ns, contrast))
    assert result.fit["detuning_hz"] == pytest.approx(2e6, rel=0.02)
    assert result.fit["t2_star_seconds"] == pytest.approx(3e-6, rel=0.1)
    frequencies_hz, spectrum, peaks_hz = ramsey_spectrum(result)
    assert spectrum.size == frequencies_hz.size
    assert peaks_hz[0] == pytest.approx(2e6, rel=0.2)


def test_the_hahn_echo_fit_recovers_t2():
    taus_ns = np.geomspace(500, 2e6, 40)
    contrast = 0.2 * np.exp(-taus_ns / 2e5) + 0.05
    fit = _fit_decay(sweep_result("Hahn_Echo", taus_ns, contrast)).fit
    assert fit["t2_seconds"] == pytest.approx(2e-4, rel=0.01)


def test_the_odmr_fit_recovers_the_resonance_and_the_linewidth():
    frequencies_hz = np.linspace(2.80e9, 2.95e9, 80)
    contrast = 0.2 / (1 + ((frequencies_hz - 2.87e9) / 5e6) ** 2) + 0.01
    fit = _fit_resonance(
        sweep_result("CW_ODMR", frequencies_hz, contrast, x_unit="Hz")
    ).fit
    assert fit["resonance_hz"] == pytest.approx(2.87e9, abs=1e6)
    assert fit["linewidth_hz"] == pytest.approx(10e6, rel=0.05)


def test_the_t1_fit_recovers_t1():
    delays_ns = np.geomspace(1e3, 3e7, 50)
    contrast = 0.5 * np.exp(-delays_ns * 1e-9 / 5e-3) + 0.5
    fit = _fit_t1(sweep_result("T1", delays_ns, contrast)).fit
    assert fit["t1_seconds"] == pytest.approx(5e-3, rel=0.02)
    assert fit["stretch"] == pytest.approx(1.0, rel=0.05)


def test_the_readout_window_fit_recommends_the_window_it_measured():
    offsets_ns = np.arange(0, 4_000, 100.0)
    photoluminescence_cps = 1e5 * (1 - np.exp(-offsets_ns / 120))
    contrast = 0.3 * np.exp(-offsets_ns / 400)
    # Before the laser has turned on there is no photoluminescence to compare,
    # which is exactly the region the fit has to stay out of.
    contrast[photoluminescence_cps < 0.05 * photoluminescence_cps.max()] = 0.0
    fit = _fit_window(offsets_ns, contrast, photoluminescence_cps)
    assert fit["tau_ns"] == pytest.approx(400, rel=0.02)
    assert fit["recommended_readout_integration_ns"] == pytest.approx(400, rel=0.02)
    assert fit["recommended_laser_on_ns"] == pytest.approx(2_000, rel=0.02)
    assert fit["recommended_laser_readout_offset_ns"] == pytest.approx(200)


def test_a_fit_that_cannot_converge_is_reported_as_no_fit():
    flat = sweep_result("Hahn_Echo", np.arange(10.0), np.zeros(10))
    assert _fit_decay(flat).fit is None


def test_the_fitted_curve_of_a_kind_is_drawable_through_the_registry():
    durations_ns = np.linspace(0, 500, 251)
    result = _fit_rabi(
        sweep_result(
            "Rabi",
            durations_ns,
            -0.15 * np.cos(2 * np.pi * durations_ns / 100) + 0.15,
        )
    )
    x, y, label = fitted_curve(result)
    assert x.size == y.size
    assert "mw_pi_ns" in label


def test_the_cli_exposes_every_experiment_with_its_configuration():
    parser = cli.build_parser()
    assert sorted(cli.SETTINGS) == sorted(cli.HELP) == sorted(cli.RUNNERS)
    assert len(cli.SETTINGS) == 10
    for name in cli.SETTINGS:
        assert parser.parse_args([name]).command == name
    assert parser.parse_args(["list"]).command == "list"


def test_every_configured_key_is_a_parameter_of_its_experiment():
    import inspect

    targets = {
        "pl": counted_point,
        "dark": counted_point,
        "cwodmr": cw_odmr,
        "podmr": pulsed_odmr,
        "readout-window": readout_window,
        "rabi": rabi,
        "ramsey": _coherence_sweep,
        "hahn": _coherence_sweep,
        "cpmg": _coherence_sweep,
        "t1": t1,
    }
    for name, settings in cli.SETTINGS.items():
        accepted = set(inspect.signature(targets[name]).parameters)
        # cpmg() consumes n_pulses itself and passes the rest through.
        unknown = set(settings) - accepted - {"n_pulses"}
        assert not unknown, f"{name} configures {sorted(unknown)}"


def test_the_sweep_axis_is_linear_when_given_a_point_count():
    np.testing.assert_allclose(cli._sweep_axis((0, 10, 3)), [0, 5, 10])
    np.testing.assert_allclose(cli._sweep_axis((500, 2e6)), [500, 2e6])


def test_overrides_are_parsed_as_python_literals():
    assert cli._overrides(["reps=2000", "scaling_factor='3/2'"]) == {
        "reps": 2000,
        "scaling_factor": "3/2",
    }
    assert cli._overrides(["taus_ns=(100, 200, 3)"])["taus_ns"] == (100, 200, 3)
