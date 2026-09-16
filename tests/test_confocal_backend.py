import numpy as np
import pytest

from common import utils
from rfsoc.confocal_backend import (
    AcquisitionHandle,
    RFSoCConfocalBackend,
    analog_write_buffer,
    frame_waveform,
    lead_in_waveform,
    raster_line,
    stream_stride,
)
from rfsoc.config import readout_plan
from tests.test_confocal_frame import FakeProgram, FakeSoc

READOUT_CLOCK_HZ = 307.2e6


def test_frame_waveform_pads_flyback_on_every_line_but_the_last():
    raster = np.arange(2 * 15, dtype=float).reshape(2, 15)
    # width 3, 3 lines, stride 5 (3 imaging + 2 flyback), last line unpadded.
    frame = frame_waveform(raster, 3, 3, 5, 2)
    assert frame.shape == (2, 15)
    np.testing.assert_array_equal(
        frame[0], [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 12, 12]
    )
    np.testing.assert_array_equal(
        raster_line(raster, 3, 3, 5, 2, 0)[0], [0, 1, 2, 3, 4]
    )


def test_lead_in_ramps_and_arrives_on_the_first_pixel():
    lead = lead_in_waveform([0.0, 1.0], [4.0, 1.0], 4)
    assert lead.shape == (2, 4)
    np.testing.assert_allclose(lead[0], [1.0, 2.0, 3.0, 4.0])
    np.testing.assert_allclose(lead[1], [1.0, 1.0, 1.0, 1.0])
    assert lead_in_waveform([0.0], [4.0], 0).shape == (1, 0)


def test_the_stride_follows_the_dwell_from_a_line_down_to_a_pixel():
    # An ordinary dwell would need more than a line per update, so it is capped.
    assert stream_stride(100, 1.005e-3, 0.2) == 100
    # Long dwells advance the image pixel by pixel instead.
    assert stream_stride(100, 0.1, 0.2) == 2
    assert stream_stride(100, 5.0, 0.2) == 1
    assert stream_stride(100, 1e-3) == min(
        100, round(utils.RFSOC_STREAM_UPDATE_SECONDS / 1e-3)
    )


class FakeAcquisition:
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class FakeSession:
    def __init__(self, soc):
        self.soc = soc
        self.soccfg = {"tprocs": [{"f_time": 307.2}]}

    def acquisition(self, blocking=True):
        return FakeAcquisition()


class FakeTask:
    def __init__(self, events):
        self.events = events
        self.written = None

    def write(self, data, auto_start=False):
        self.written = np.asarray(data).copy()
        self.events.append("ni_write")

    def start(self):
        self.events.append("ni_start")

    def wait_until_done(self, timeout=None):
        self.events.append("ni_wait")

    def stop(self):
        self.events.append("ni_stop")

    def close(self):
        self.events.append("ni_close")


class FakeFrameBackend(RFSoCConfocalBackend):
    """Frame acquisition with the QICK program and the NI task replaced."""

    def __init__(self, soc, events):
        super().__init__(FakeSession(soc))
        self.events = events
        self.tasks = []

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

    def _open_ao_task(self, ao_channels, expected, plan):
        self.events.append(("ni_task", int(expected)))
        task = FakeTask(self.events)
        self.tasks.append(task)
        return task


def fake_frame_program(cfg, events):
    program = FakeProgram(int(cfg.n_lines) * int(cfg.reps), events)
    program.cfg = cfg
    return program


def test_the_whole_raster_is_one_acquire_updated_line_by_line(monkeypatch):
    events = []
    width, n_lines, n_flyback = 4, 3, 2
    stride = width + n_flyback
    raster = np.arange(n_lines * stride, dtype=float)[np.newaxis, :]
    lines = [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]]
    soc = FakeSoc([[line] for line in lines], events)
    backend = FakeFrameBackend(soc, events)
    monkeypatch.setattr(
        "rfsoc.confocal_backend.ConfocalFrame",
        lambda cfg: fake_frame_program(cfg, events),
    )
    updates = []

    counts, widths = backend.acquire_frame(
        ["Dev1/ao0"],
        raster,
        1e-3,
        width=width,
        n_lines=n_lines,
        stride=stride,
        n_flyback=n_flyback,
        flyback_seconds=2e-3,
        on_line=lambda c, w: updates.append((c, w)),
    )

    # One QICK program and one NI task for the whole image; the lead-in holds
    # the first pixel, and the last line carries no flyback samples.
    assert [event for event in events if event[0] == "ni_task"] == [
        ("ni_task", n_flyback + n_lines * stride)
    ]
    assert events.count("config_all") == 1
    # Two lead-in clocks on the first pixel, the two full lines with their
    # flyback ramps, then the last line padded to the same length.
    np.testing.assert_array_equal(
        backend.tasks[0].written,
        [0.0, 0.0] + list(range(16)) + [15.0, 15.0],
    )
    # A 1 ms dwell asks for more than a line per update, so the stride is a line.
    assert ("start_readout", n_lines * width, width) in events
    # The image is handed over as it fills, with a zero bin width ahead of it.
    assert [int(np.count_nonzero(w)) for _c, w in updates] == [4, 8, 12]
    assert updates[0][0].tolist() == [1, 2, 3, 4, 0, 0, 0, 0, 0, 0, 0, 0]
    dwell_ps = int(round(readout_plan(1e-3, READOUT_CLOCK_HZ).seconds * 1e12))
    assert counts.tolist() == [c for line in lines for c in line]
    assert np.all(widths == dwell_ps)


def test_a_stop_before_the_frame_is_armed_never_opens_a_task():
    events = []
    backend = FakeFrameBackend(FakeSoc([], events), events)
    handle = AcquisitionHandle()
    handle.stop()

    with pytest.raises(InterruptedError):
        backend.acquire_frame(
            ["Dev1/ao0"],
            np.arange(12, dtype=float)[np.newaxis, :],
            1e-3,
            width=4,
            n_lines=2,
            stride=6,
            n_flyback=2,
            handle=handle,
        )

    assert events == []


def test_a_stop_mid_frame_closes_the_ni_task(monkeypatch):
    events = []
    width, n_lines = 4, 3
    raster = np.arange(n_lines * width, dtype=float)[np.newaxis, :]
    soc = FakeSoc([[[1, 2, 3, 4]], [[5, 6, 7, 8]]], events)
    backend = FakeFrameBackend(soc, events)
    monkeypatch.setattr(
        "rfsoc.confocal_backend.ConfocalFrame",
        lambda cfg: fake_frame_program(cfg, events),
    )
    handle = AcquisitionHandle()

    with pytest.raises(InterruptedError):
        backend.acquire_frame(
            ["Dev1/ao0"],
            raster,
            1e-3,
            width=width,
            n_lines=n_lines,
            stride=width,
            n_flyback=0,
            handle=handle,
            on_line=lambda _c, _w: handle.stop(),
        )

    assert soc.stopped == 1
    assert events[-1] == "ni_close"
    assert handle.task is None


def test_a_dwell_past_the_measured_window_is_refused_before_any_hardware():
    events = []
    backend = FakeFrameBackend(FakeSoc([], events), events)

    with pytest.raises(ValueError, match="window_linearity"):
        backend.acquire_frame(
            ["Dev1/ao0"],
            np.arange(8, dtype=float)[np.newaxis, :],
            utils.RFSOC_MAX_COUNTING_WINDOW_S * 2,
            width=4,
            n_lines=2,
            stride=4,
            n_flyback=0,
        )

    assert events == []


def test_a_sweep_is_acquired_as_a_raster_of_one_line(monkeypatch):
    events = []
    soc = FakeSoc([[[7, 8, 9]]], events)
    backend = FakeFrameBackend(soc, events)
    monkeypatch.setattr(
        "rfsoc.confocal_backend.ConfocalFrame",
        lambda cfg: fake_frame_program(cfg, events),
    )

    counts, widths = backend.acquire_line(
        ["Dev1/ao0"],
        np.array([[1.0, 2.0, 3.0]]),
        1e-3,
        n_imaging_points=3,
    )

    assert counts.tolist() == [7, 8, 9]
    assert np.all(widths > 0)
    # One lead-in clock, then the three sweep points.
    np.testing.assert_array_equal(backend.tasks[0].written, [1.0, 1.0, 2.0, 3.0])


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
