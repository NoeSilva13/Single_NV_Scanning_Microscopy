import numpy as np

from rfsoc.experiments.base import normalized_result


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
