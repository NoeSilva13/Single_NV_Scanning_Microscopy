import numpy as np

from confocal.raster_engine import build_raster_waveforms, reconstruct


def test_raster_keeps_flyback_in_waveform_only():
    waveforms, shape, stride, width, n_lines = build_raster_waveforms(
        [np.arange(3), np.arange(2)], n_flyback=2
    )
    assert shape == (2, 3)
    assert (stride, width, n_lines) == (5, 3, 2)
    assert len(waveforms[0]) == 8  # final line has no trailing flyback

    counts = np.arange(6) + 1
    widths = np.full(6, 1_000_000_000)
    image = reconstruct(counts, widths, shape, stride, width)
    np.testing.assert_allclose(image, counts.reshape(shape) * 1000)


def test_partial_compact_data_uses_zero_widths():
    counts = np.array([4, 5, 0, 0])
    widths = np.array([1_000_000_000, 1_000_000_000, 0, 0])
    image = reconstruct(counts, widths, (2, 2), 3, 2)
    np.testing.assert_allclose(image, [[4000, 5000], [0, 0]])
