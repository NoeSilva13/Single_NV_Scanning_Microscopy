import numpy as np

from common import utils
from rfsoc.confocal_backend import (
    AcquisitionHandle,
    RFSoCConfocalBackend,
    block_waveform,
    iter_frame_blocks,
    lead_in_waveform,
    lines_per_block,
    raster_line,
    run_lines,
)
from rfsoc.config import readout_plan

READOUT_CLOCK_HZ = 307.2e6


def test_frame_blocks_cover_every_line_once():
    assert list(iter_frame_blocks(10, 4)) == [(0, 4), (4, 4), (8, 2)]
    assert list(iter_frame_blocks(4, 10)) == [(0, 4)]
    assert sum(n for _first, n in iter_frame_blocks(100, 7)) == 100


def test_block_size_follows_the_wall_time_budget():
    # 100 px x (1 ms + 5 us settle) + 2 ms retrace = 102.5 ms per line.
    assert lines_per_block(100, 2, 1e-3, 2e-3, budget_seconds=2.0) == 19
    # A line that is already over budget still has to be acquired.
    assert lines_per_block(100, 2, 1e-3, 2e-3, budget_seconds=1e-3) == 1


def test_block_waveform_pads_flyback_and_starts_at_the_block():
    raster = np.arange(2 * 15, dtype=float).reshape(2, 15)
    # width 3, 3 lines, stride 5 (3 imaging + 2 flyback), last line unpadded.
    block = block_waveform(raster, 3, 3, 5, 2, first_line=1, block_lines=2)
    assert block.shape == (2, 10)
    np.testing.assert_array_equal(block[0], [5, 6, 7, 8, 9, 10, 11, 12, 12, 12])
    np.testing.assert_array_equal(
        raster_line(raster, 3, 3, 5, 2, 0)[0], [0, 1, 2, 3, 4]
    )


def test_lead_in_ramps_and_arrives_on_the_first_pixel():
    lead = lead_in_waveform([0.0, 1.0], [4.0, 1.0], 4)
    assert lead.shape == (2, 4)
    np.testing.assert_allclose(lead[0], [1.0, 2.0, 3.0, 4.0])
    np.testing.assert_allclose(lead[1], [1.0, 1.0, 1.0, 1.0])
    assert lead_in_waveform([0.0], [4.0], 0).shape == (1, 0)


class FakeAcquisition:
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class FakeSession:
    def acquisition(self, blocking=True):
        return FakeAcquisition()


class FakeProgram:
    def __init__(self, cfg):
        self.cfg = cfg


class FakeFrameBackend(RFSoCConfocalBackend):
    """Frame acquisition with the QICK program and the NI task replaced."""

    def __init__(self):
        super().__init__(FakeSession())
        self.pass_pixels = []
        self.waveforms = []
        self.task_lengths = []

    def _program_config(self, width, dwell_seconds, n_flyback,
                        flyback_seconds=None, n_lines=1, n_lead=0):
        plan = readout_plan(dwell_seconds, READOUT_CLOCK_HZ)
        cfg = type("FakeConfig", (), {})()
        cfg.reps = int(width)
        cfg.n_flyback = int(n_flyback)
        cfg.n_lines = int(n_lines)
        cfg.n_lead = int(n_lead)
        cfg.flyback_period_treg = 1
        return cfg, plan

    def _line_timeout(self, plan, n_imaging, cfg):
        return 1.0

    def _open_ao_task(self, ao_channels, expected, plan):
        self.task_lengths.append(int(expected))
        return object()

    @staticmethod
    def _close_ao_task(task):
        return None

    def _clock_and_count(self, task, program, data, timeout):
        cfg = program.cfg
        n_pixels = int(cfg.n_lines) * int(cfg.reps)
        self.waveforms.append(np.asarray(data).copy())
        self.pass_pixels.append(n_pixels)
        return np.ones(n_pixels, dtype=np.int64)


def test_frame_passes_accumulate_counts_and_integrated_widths(monkeypatch):
    monkeypatch.setattr("rfsoc.confocal_frame.ConfocalFrame", FakeProgram)
    monkeypatch.setattr(utils, "RFSOC_FRAME_BLOCK_SECONDS", 1e-3)

    width, n_lines, n_flyback = 4, 3, 2
    stride = width + n_flyback
    raster = np.arange(n_lines * stride, dtype=float)[np.newaxis, :]
    backend = FakeFrameBackend()
    updates = []

    counts, widths = run_lines(
        backend,
        ["Dev1/ao0"],
        raster,
        width=width,
        n_lines=n_lines,
        stride=stride,
        dwell_seconds=5e-3,
        n_flyback=n_flyback,
        flyback_seconds=2e-3,
        on_line=lambda c, w: updates.append((c, w)),
        handle=AcquisitionHandle(),
    )

    # 5 ms exceeds one validated window, so it needs 3 windows of 1.667 ms.
    plan = readout_plan(5e-3, READOUT_CLOCK_HZ)
    n_passes = plan.windows_per_pixel
    assert n_passes == 3
    # The 1 ms budget forces one line per block, so 3 blocks x 3 passes.
    assert backend.pass_pixels == [width] * (n_lines * n_passes)
    assert counts.tolist() == [n_passes] * (n_lines * width)
    assert np.all(widths == n_passes * int(round(plan.window_seconds * 1e12)))
    assert len(updates) == n_lines * n_passes
    # One task per block, clocking the lead-in plus one flyback-padded line.
    assert backend.task_lengths == [n_flyback + stride] * n_lines
    # Each pass re-arms with a ramp from where the last task parked the galvo
    # to the first pixel of its own line.
    np.testing.assert_array_equal(backend.waveforms[0][0], [0, 0, 0, 1, 2, 3, 4, 5])
    np.testing.assert_array_equal(
        backend.waveforms[3][0], [5.5, 6, 6, 7, 8, 9, 10, 11]
    )


def test_an_ordinary_dwell_takes_one_acquire_for_the_whole_raster(monkeypatch):
    monkeypatch.setattr("rfsoc.confocal_frame.ConfocalFrame", FakeProgram)
    monkeypatch.setattr(utils, "RFSOC_FRAME_BLOCK_SECONDS", 10.0)

    width, n_lines, n_flyback = 4, 3, 2
    stride = width + n_flyback
    raster = np.arange(n_lines * stride, dtype=float)[np.newaxis, :]
    backend = FakeFrameBackend()

    counts, _widths = run_lines(
        backend,
        ["Dev1/ao0"],
        raster,
        width=width,
        n_lines=n_lines,
        stride=stride,
        dwell_seconds=1e-3,
        n_flyback=n_flyback,
        flyback_seconds=2e-3,
        handle=AcquisitionHandle(),
    )

    # A 1 ms dwell is a single window, so the frame is one block and one pass:
    # every pixel integrates its whole dwell in one uninterrupted stop.
    assert backend.task_lengths == [n_flyback + n_lines * stride]
    assert backend.pass_pixels == [n_lines * width]
    assert counts.tolist() == [1] * (n_lines * width)


def test_frame_acquire_stops_before_the_first_pass(monkeypatch):
    monkeypatch.setattr("rfsoc.confocal_frame.ConfocalFrame", FakeProgram)

    width, n_lines, n_flyback = 4, 2, 2
    stride = width + n_flyback
    raster = np.arange(n_lines * stride, dtype=float)[np.newaxis, :]
    backend = FakeFrameBackend()
    handle = AcquisitionHandle()
    handle.stop()

    try:
        backend.acquire_frame(
            ["Dev1/ao0"],
            raster,
            1e-3,
            width=width,
            n_lines=n_lines,
            stride=stride,
            n_flyback=n_flyback,
            handle=handle,
        )
    except InterruptedError:
        pass
    else:
        raise AssertionError("stop request was ignored")
    assert backend.pass_pixels == []
