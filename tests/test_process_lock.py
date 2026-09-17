"""The claim has to hold between processes, so these tests use real ones."""

from pathlib import Path
import subprocess
import sys
import time

import pytest

from rfsoc.process_lock import RFSoCBusyError, claim_path, file_claim

REPO_ROOT = Path(__file__).resolve().parents[1]

# Claims, waits and releases the claim on argv[1] on the parent's cue.  Kept as a
# script because a thread of the test process would not prove anything: the point
# of the claim is that it is the operating system, not Python, that arbitrates.
CLAIMER = """
import os, sys, time
from rfsoc.process_lock import RFSoCBusyError, file_claim

path, timeout, ready, got, release = sys.argv[1:6]
open(ready, "w").close()
try:
    with file_claim(path, timeout=float(timeout)):
        open(got, "w").close()
        while not os.path.exists(release):
            time.sleep(0.01)
except RFSoCBusyError:
    sys.exit(3)
"""


@pytest.fixture
def claimer(tmp_path):
    """Start claimer processes and make sure none outlive the test."""
    started = []
    counter = [0]

    def start(timeout=0.0):
        counter[0] += 1
        tag = counter[0]
        markers = {
            name: tmp_path / f"{name}{tag}"
            for name in ("ready", "got", "release")
        }
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                CLAIMER,
                str(tmp_path / "board.claim"),
                str(timeout),
                *(str(markers[n]) for n in ("ready", "got", "release")),
            ],
            cwd=REPO_ROOT,
        )
        started.append((process, markers))
        return process, markers

    yield start

    for process, markers in started:
        markers["release"].touch()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def appears(path, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if Path(path).exists():
            return True
        time.sleep(0.01)
    return False


def test_the_claim_names_the_process_that_holds_it(tmp_path, claimer):
    holder, markers = claimer()
    assert appears(markers["got"])

    with pytest.raises(RFSoCBusyError) as refused:
        with file_claim(tmp_path / "board.claim", timeout=0.0):
            pass

    assert f"pid {holder.pid}" in str(refused.value)


def test_the_claim_is_free_again_once_the_holder_lets_go(tmp_path, claimer):
    _holder, markers = claimer()
    assert appears(markers["got"])
    markers["release"].touch()

    with file_claim(tmp_path / "board.claim", timeout=10.0) as claimed:
        assert claimed == tmp_path / "board.claim"


def test_a_killed_holder_does_not_leave_the_board_claimed(tmp_path, claimer):
    holder, markers = claimer()
    assert appears(markers["got"])
    holder.kill()
    holder.wait(timeout=10)

    with file_claim(tmp_path / "board.claim", timeout=10.0):
        pass


def test_a_waiter_gives_up_at_its_deadline(tmp_path, claimer):
    _holder, markers = claimer()
    assert appears(markers["got"])

    start = time.monotonic()
    with pytest.raises(RFSoCBusyError, match="did not release it within"):
        with file_claim(tmp_path / "board.claim", timeout=0.3):
            pass
    assert time.monotonic() - start >= 0.3


def test_a_claimant_that_cannot_wait_stands_down_for_one_that_is_waiting(
    tmp_path, claimer
):
    holder, holder_markers = claimer()
    assert appears(holder_markers["got"])
    _waiter, waiter_markers = claimer(timeout=30.0)
    assert appears(waiter_markers["ready"])
    time.sleep(0.5)  # let the waiter announce itself

    # A caller that yields -- the live count plot -- is turned away by the queued
    # waiter, not merely by the claim, so it will still be standing down at the
    # moment the holder lets go and the waiter can take its turn.
    with pytest.raises(RFSoCBusyError, match="waiting for the RFSoC"):
        with file_claim(
            tmp_path / "board.claim", timeout=0.0, yield_to_waiters=True
        ):
            pass

    holder_markers["release"].touch()
    assert appears(waiter_markers["got"])


def test_each_board_is_claimed_on_its_own_file():
    assert claim_path("192.168.0.236") != claim_path("192.168.0.237")
    assert claim_path("192.168.0.236").name == "nv_rfsoc_192.168.0.236.claim"
