import numpy as np

from rfsoc.confocal_backend import AcquisitionHandle, analog_write_buffer, run_lines


class FakeLineBackend:
    def __init__(self):
        self.calls = []

    def acquire_line(
        self, channels, waveform, dwell_seconds, *,
        n_imaging_points, n_flyback, handle,
    ):
        self.calls.append((waveform.copy(), n_imaging_points, n_flyback))
        value = len(self.calls)
        return (
            np.full(n_imaging_points, value, dtype=np.int64),
            np.full(n_imaging_points, 1000, dtype=np.int64),
        )


def test_run_lines_sends_flyback_but_returns_only_pixels():
    backend = FakeLineBackend()
    waveform = np.arange(8, dtype=float)[None, :]
    updates = []
    counts, widths = run_lines(
        backend,
        ["Dev1/ao0"],
        waveform,
        width=3,
        n_lines=2,
        stride=5,
        dwell_seconds=1e-3,
        n_flyback=2,
        on_line=lambda c, w: updates.append((c, w)),
        handle=AcquisitionHandle(),
    )
    assert backend.calls[0][0].shape == (1, 5)
    assert backend.calls[1][0].shape == (1, 3)
    assert [call[2] for call in backend.calls] == [2, 0]
    assert counts.tolist() == [1, 1, 1, 2, 2, 2]
    assert np.all(widths == 1000)
    assert len(updates) == 2


def test_analog_write_buffer_copies_xy_line_slices():
    raster = np.arange(2 * 22, dtype=np.float64).reshape(2, 22)
    full = np.concatenate([raster, raster], axis=1)
    line = full[:, 0:22]
    assert not line.flags["C_CONTIGUOUS"]
    out = analog_write_buffer(line)
    assert out.flags["C_CONTIGUOUS"]
    assert out.shape == (2, 22)
    assert np.array_equal(out, raster)

    single = full[0:1, 0:22]
    flat = analog_write_buffer(single)
    assert flat.ndim == 1
    assert flat.flags["C_CONTIGUOUS"]
    assert np.array_equal(flat, raster[0])

