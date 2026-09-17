import numpy as np
import pandas as pd
import pytest

from rfsoc.experiments.base import (
    CountingResult,
    ExperimentResult,
    fine_sweep,
    normalized_result,
    spin_executed,
    spin_requested,
)
from rfsoc.experiments.cpmg import _fit_decay, _fit_ramsey, ramsey_spectrum
from rfsoc.experiments.io import fitted_curve, save_result
from rfsoc.experiments.odmr import _fit_resonance
from rfsoc.experiments.rabi import _fit_rabi
from rfsoc.experiments.readout_window import _fit_window
from rfsoc.experiments.t1 import _fit_t1


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


def test_spin_requested_records_the_timings_a_csv_needs_to_reproduce_the_sweep():
    requested = spin_requested(
        mw_frequency_hz=2.846e9,
        mw_gain=32_767,
        laser_on_ns=6_000,
        readout_ns=633,
        laser_readout_offset_ns=1_159,
        reference_start_ns=5_000,
        mw_to_laser_delay_ns=555,
        relax_delay_ns=2_000,
        reps=10_000,
        durations_ns=[4, 500],
    )
    assert requested["laser_on_ns"] == 6_000
    assert requested["laser_readout_offset_ns"] == 1_159
    assert requested["mw_to_laser_delay_ns"] == 555
    assert requested["relax_delay_ns"] == 2_000
    assert requested["durations_ns"] == [4, 500]


def test_spin_executed_reads_the_same_names_back_from_the_config():
    cfg = FakeConfig()
    cfg.mw_fGHz = 2.846
    cfg.mw_gain = 32_767
    cfg.laser_on_tns = 6_000
    cfg.readout_integration_tns = 633
    cfg.laser_readout_offset_tns = 1_159
    cfg.readout_reference_start_tns = 5_000
    cfg.mw_to_laser_delay_tns = 555
    cfg.relax_delay_tns = 2_000
    cfg.reps = 10_000
    cfg.get_reference = True
    cfg.mw_pi_ftns = 50.0
    executed = spin_executed(cfg, durations_ns=[4.0, 500.0])
    assert executed["mw_frequency_hz"] == pytest.approx(2.846e9)
    assert executed["laser_on_ns"] == 6_000
    assert executed["laser_readout_offset_ns"] == 1_159
    assert executed["mw_to_laser_delay_ns"] == 555
    assert executed["relax_delay_ns"] == 2_000
    assert executed["mw_pi_ns"] == 50.0
    assert executed["durations_ns"] == [4.0, 500.0]


def test_save_result_writes_configuration_in_the_csv_header(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "rfsoc.experiments.io._next_stem",
        lambda kind: str(tmp_path / f"001_{kind}"),
    )
    result = ExperimentResult(
        kind="Rabi",
        x_name="MW_duration",
        x_unit="ns",
        x=np.array([4.0, 6.0]),
        signal_counts=np.array([1.0, 2.0]),
        reference_counts=np.array([3.0, 4.0]),
        signal_rate_cps=np.array([10.0, 20.0]),
        reference_rate_cps=np.array([30.0, 40.0]),
        contrast=np.array([0.1, 0.2]),
        requested={"laser_on_ns": 6_000, "durations_ns": list(range(249))},
        executed={"laser_on_ns": 6_000, "reps": 10_000},
        fit={"mw_pi_ns": 50.0},
    )
    save_result(result)
    text = (tmp_path / "001_Rabi.csv").read_text(encoding="utf-8")
    assert text.startswith("# Measurement Time:")
    assert "# Kind: Rabi" in text
    assert "# Requested:" in text
    assert "#   laser_on_ns: 6000" in text
    assert "#   durations_ns: 0 to 248 (249 points)" in text
    assert "# Executed:" in text
    assert "# Fit:" in text
    assert "#   mw_pi_ns: 50.0" in text
    table = pd.read_csv(tmp_path / "001_Rabi.csv", comment="#")
    assert list(table.columns) == [
        "MW_duration_ns",
        "Signal_counts",
        "Reference_counts",
        "Signal_cps",
        "Reference_cps",
        "Contrast",
    ]
    np.testing.assert_allclose(table["Contrast"], [0.1, 0.2])
