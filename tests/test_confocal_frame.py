import numpy as np
import pytest

from rfsoc.confocal_frame import stream_counts


def accumulated(counts):
    """Shape a chunk of counts like QICK's accumulated (I, Q) buffer."""
    counts = np.asarray(counts, dtype=np.int64)
    return [np.column_stack([counts, np.zeros_like(counts)])]


class FakeProgram:
    def __init__(self, total, events):
        self.expected_readouts = int(total)
        self.counter_addr = 1
        self.ro_chs = {0: object()}
        self.reads_per_shot = None
        self.events = events

    def set_reads_per_shot(self, reads):
        self.reads_per_shot = [int(reads)]
        self.events.append(("reads_per_shot", int(reads)))

    def config_all(self, soc, load_mem=True):
        self.events.append("config_all")

    def config_bufs(self, soc, enable_avg=True, enable_buf=False):
        self.events.append("config_bufs")


class FakeSoc:
    """Hands back pre-canned poll_data payloads, one list per call."""

    def __init__(self, polls, events=None):
        self.polls = [list(poll) for poll in polls]
        self.events = events if events is not None else []
        self.stopped = 0

    def start_src(self, src):
        self.events.append(("start_src", src))

    def reload_mem(self):
        self.events.append("reload_mem")

    def start_readout(self, total, counter_addr=1, ch_list=None,
                      reads_per_shot=None, stride=None):
        self.events.append(("start_readout", int(total), stride))

    def poll_data(self, totaltime=0.1, timeout=None):
        if not self.polls:
            return []
        return [
            (len(chunk), (accumulated(chunk), None))
            for chunk in self.polls.pop(0)
        ]

    def stop_tproc(self):
        self.stopped += 1
        self.events.append("stop_tproc")


def drain(program, soc, **kwargs):
    kwargs.setdefault("stride", 2)
    kwargs.setdefault("poll_timeout", 1.0)
    return list(stream_counts(program, soc, **kwargs))


def test_the_analog_output_is_armed_after_the_program_loads_and_before_readout():
    events = []
    program = FakeProgram(4, events)
    soc = FakeSoc([[[1, 2]], [[3, 4]]], events)

    drain(program, soc, on_armed=lambda: events.append("arm"))

    # The streamer is what calls start_tproc, so anything consuming the pixel
    # clock has to be running by then, and no earlier than the upload.
    assert events == [
        ("reads_per_shot", 1),
        "config_all",
        ("start_src", "internal"),
        "config_bufs",
        "reload_mem",
        "arm",
        ("start_readout", 4, 2),
    ]


def test_counts_fill_one_array_in_raster_order_as_strides_arrive():
    program = FakeProgram(6, [])
    soc = FakeSoc([[[5, 6]], [[7, 8], [9, 10]]])

    # Snapshot each stride as it arrives: the stream fills one array in place.
    updates = [
        (counts.copy(), filled)
        for counts, filled in stream_counts(
            program, soc, stride=2, poll_timeout=1.0
        )
    ]

    assert [filled for _counts, filled in updates] == [2, 6]
    assert updates[0][0].tolist() == [5, 6, 0, 0, 0, 0]
    assert updates[-1][0].tolist() == [5, 6, 7, 8, 9, 10]


def test_a_stop_between_strides_halts_the_tproc():
    program = FakeProgram(6, [])
    soc = FakeSoc([[[1, 2]], [[3, 4]], [[5, 6]]])
    seen = []

    with pytest.raises(InterruptedError):
        for counts, filled in stream_counts(
            program, soc, stride=2, poll_timeout=1.0,
            stop_check=lambda: len(seen) == 2,
        ):
            seen.append(filled)

    assert seen == [2, 4]
    assert soc.stopped == 1


def test_abandoning_the_stream_halts_the_tproc():
    program = FakeProgram(6, [])
    soc = FakeSoc([[[1, 2]], [[3, 4]], [[5, 6]]])

    stream = stream_counts(program, soc, stride=2, poll_timeout=1.0)
    next(stream)
    stream.close()

    assert soc.stopped == 1


def test_silence_from_the_board_becomes_an_error_instead_of_a_hang():
    program = FakeProgram(4, [])
    soc = FakeSoc([[[1, 2]]])

    with pytest.raises(RuntimeError, match="2 of 4 pixels"):
        drain(program, soc)

    assert soc.stopped == 1


def test_more_readouts_than_pixels_is_refused():
    program = FakeProgram(3, [])
    soc = FakeSoc([[[1, 2, 3, 4]]])

    with pytest.raises(RuntimeError, match="expected 3"):
        drain(program, soc)
