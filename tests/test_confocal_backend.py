import numpy as np

from rfsoc.confocal_backend import (
    AcquisitionHandle,
    RFSoCConfocalBackend,
    analog_write_buffer,
    iter_line_chunks,
    iter_raster_lines,
    max_pixels_per_acquire,
    run_lines,
    should_publish_scan_progress,
)
from rfsoc.config import readout_plan
from common.utils import RFSOC_MAX_ADC_READOUTS


class FakeLineBackend:
    def __init__(self):
        self.calls = []

    def acquire_line(
        self, channels, waveform, dwell_seconds, *,
        n_imaging_points, n_flyback, handle, **_kwargs,
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
    assert backend.calls[1][0].shape == (1, 5)
    assert [call[2] for call in backend.calls] == [2, 2]
    np.testing.assert_array_equal(backend.calls[1][0], [[5, 6, 7, 7, 7]])
    assert counts.tolist() == [1, 1, 1, 2, 2, 2]
    assert np.all(widths == 1000)
    assert len(updates) == 2


def test_iter_raster_lines_pads_the_last_line():
    waveform = np.arange(8, dtype=float)[None, :]
    lines = list(iter_raster_lines(waveform, 3, 2, 5, 2))
    assert [idx for idx, _, _ in lines] == [0, 1]
    np.testing.assert_array_equal(lines[0][1], [[0, 1, 2, 3, 4]])
    np.testing.assert_array_equal(lines[1][1], [[5, 6, 7, 7, 7]])
    assert [fb for _, _, fb in lines] == [2, 2]


def test_preview_publishes_first_every_n_and_last():
    published = [
        i for i in range(10) if should_publish_scan_progress(i, 10, every=5)
    ]
    assert published == [0, 4, 9]


def test_line_chunks_keep_adc_readouts_under_the_cap():
    plan_1ms = readout_plan(1e-3, 307.2e6)
    assert plan_1ms.windows_per_pixel == 5
    assert max_pixels_per_acquire(plan_1ms.windows_per_pixel) == 25
    chunks_100 = list(iter_line_chunks(100, 2, plan_1ms.windows_per_pixel))
    assert chunks_100 == [
        (0, 25, 0),
        (25, 25, 0),
        (50, 25, 0),
        (75, 25, 2),
    ]
    assert all(
        n_pix * plan_1ms.windows_per_pixel <= RFSOC_MAX_ADC_READOUTS
        for _start, n_pix, _fb in chunks_100
    )
    assert list(iter_line_chunks(50, 2, 5)) == [(0, 25, 0), (25, 25, 2)]

    plan_200us = readout_plan(200e-6, 307.2e6)
    assert plan_200us.windows_per_pixel == 1
    assert max_pixels_per_acquire(plan_200us.windows_per_pixel) == 128
    assert list(iter_line_chunks(100, 0, 1)) == [(0, 100, 0)]
    assert list(iter_line_chunks(200, 2, 1)) == [(0, 128, 0), (128, 72, 2)]


def test_one_pixel_dwell_cannot_exceed_the_transfer_cap():
    try:
        max_pixels_per_acquire(RFSOC_MAX_ADC_READOUTS + 1)
    except ValueError:
        pass
    else:
        raise AssertionError("over-long dwell was accepted")


def test_clock_and_count_concatenates_chunks_on_one_ni_task():
    class FakeProgram:
        def __init__(self, n, value):
            self.n = n
            self.value = value
            self.calls = 0

        def acquire(self, progress=False):
            self.calls += 1
            return np.full(self.n, self.value, dtype=np.int64)

    class FakeTask:
        def __init__(self):
            self.events = []

        def write(self, data, auto_start=False):
            self.events.append(("write", np.asarray(data).shape))

        def start(self):
            self.events.append("start")

        def wait_until_done(self, timeout=None):
            self.events.append("wait")

        def stop(self):
            self.events.append("stop")

    backend = RFSoCConfocalBackend(session=None)
    first = FakeProgram(25, 8)
    second = FakeProgram(25, 10)
    task = FakeTask()
    counts = backend._clock_and_count(
        task, [first, second], np.zeros(50), timeout=1
    )
    assert first.calls == 1 and second.calls == 1
    assert counts.tolist() == [8] * 25 + [10] * 25
    assert task.events == [("write", (50,)), "start", "wait", "stop"]


def test_sum_window_passes_retraces_the_line():
    class FakeProgram:
        def __init__(self):
            self.calls = 0

        def acquire(self, progress=False):
            self.calls += 1
            return np.full(4, self.calls, dtype=np.int64)

    class FakeTask:
        def __init__(self):
            self.starts = 0

        def write(self, data, auto_start=False):
            return None

        def start(self):
            self.starts += 1

        def wait_until_done(self, timeout=None):
            return None

        def stop(self):
            return None

    backend = RFSoCConfocalBackend(session=None)
    program = FakeProgram()
    task = FakeTask()
    counts = backend._sum_window_passes(
        task, [program], np.zeros(4), timeout=1, n_windows=5, n_pixels=4
    )
    assert program.calls == 5
    assert task.starts == 5
    assert counts.tolist() == [15, 15, 15, 15]


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

