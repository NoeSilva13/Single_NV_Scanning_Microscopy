import numpy as np

from rfsoc.confocal_backend import (
    AcquisitionHandle,
    RFSoCConfocalBackend,
    analog_write_buffer,
    iter_raster_lines,
    run_lines,
)


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


def test_clock_and_count_arms_ni_before_the_tproc_runs():
    events = []

    class FakeProgram:
        def acquire(self, progress=False):
            events.append("acquire")
            return np.full(50, 8, dtype=np.int64)

    class FakeTask:
        def write(self, data, auto_start=False):
            events.append(("write", np.asarray(data).shape))

        def start(self):
            events.append("start")

        def wait_until_done(self, timeout=None):
            events.append("wait")

        def stop(self):
            events.append("stop")

    backend = RFSoCConfocalBackend(session=None)
    counts = backend._clock_and_count(
        FakeTask(), FakeProgram(), np.zeros(50), timeout=1
    )
    assert counts.tolist() == [8] * 50
    # The first pixel clock follows the tProc start by microseconds, so the NI
    # task has to be written and started before the program is acquired.
    assert events == [("write", (50,)), "start", "acquire", "wait", "stop"]


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
        task, program, np.zeros(4), timeout=1, n_windows=5, n_pixels=4
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

