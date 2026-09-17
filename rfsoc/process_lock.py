"""The claim on the RFSoC, held across processes.

The board daemon exposes a single ``QickSoc``: one tProc, one readout chain, one
set of PMOD pins.  QICK's ``start_readout`` stops whatever readout is already
running, so two Python processes driving the board do not queue behind each
other, they abort each other's acquisitions.  The claim therefore has to live
outside the process, which is what a file lock gives: the kernel drops it even
if the holder is killed, so a crash cannot leave the board unusable.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
import time

# Byte 0 carries the claim itself.  Byte 1 is taken by a process that is waiting
# for it, which is how a caller that cannot wait -- the live count plot, polling
# several times a second -- knows to stand down instead of taking every gap
# between two of the waiter's polls.  The holder writes its identity past both,
# where it stays readable while the claim is locked.
_CLAIM_BYTE = 0
_QUEUE_BYTE = 1
_HOLDER_OFFSET = 2
_HOLDER_BYTES = 30
_POLL_SECONDS = 0.02


class RFSoCBusyError(RuntimeError):
    """Another thread or another process is driving the board."""


if os.name == "nt":
    import msvcrt

    def _lock_byte(handle, offset):
        handle.seek(offset)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    def _unlock_byte(handle, offset):
        handle.seek(offset)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock_byte(handle, offset):
        try:
            fcntl.lockf(
                handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
                1,
                offset,
                os.SEEK_SET,
            )
        except OSError:
            return False
        return True

    def _unlock_byte(handle, offset):
        fcntl.lockf(handle.fileno(), fcntl.LOCK_UN, 1, offset, os.SEEK_SET)


def claim_path(host):
    """Where the claim on *host* lives: one file per board, outside the repo."""
    name = "".join(
        char if char.isalnum() or char in "-._" else "_" for char in str(host)
    )
    return Path(tempfile.gettempdir()) / f"nv_rfsoc_{name}.claim"


def _open(path):
    # O_CREAT without O_TRUNC: whoever arrives second must not wipe the file the
    # first one is holding.
    return os.fdopen(os.open(os.fspath(path), os.O_RDWR | os.O_CREAT), "r+b")


def _write_holder(handle):
    handle.seek(_HOLDER_OFFSET)
    handle.write(f"pid {os.getpid()}".encode().ljust(_HOLDER_BYTES)[:_HOLDER_BYTES])
    handle.flush()


def _read_holder(handle):
    try:
        handle.seek(_HOLDER_OFFSET)
        holder = handle.read(_HOLDER_BYTES).decode(errors="replace").strip()
    except OSError:
        return "unknown process"
    return holder or "unknown process"


def _queue_is_empty(handle):
    if not _lock_byte(handle, _QUEUE_BYTE):
        return False
    _unlock_byte(handle, _QUEUE_BYTE)
    return True


@contextmanager
def file_claim(path, *, timeout=0.0, yield_to_waiters=False):
    """Hold the claim recorded in *path* for the duration of the block.

    Waits up to *timeout* seconds, announcing the wait so that a caller which
    cannot wait stands down.  The wait is bounded rather than indefinite because
    the callers are a GUI scan thread and a batch script: both would rather
    report who holds the board than look hung.

    With *yield_to_waiters* the claim is refused outright while somebody is
    waiting for it, which is what keeps a fast polling caller from starving a
    scan or an experiment that asked first.
    """
    handle = _open(path)
    queued = False
    try:
        if yield_to_waiters and not _queue_is_empty(handle):
            raise RFSoCBusyError(
                "another process is waiting for the RFSoC; standing down"
            )
        deadline = time.monotonic() + max(0.0, float(timeout))
        while True:
            # Announced on every poll until it takes, because the announcement
            # byte is briefly held by whoever else is reading or claiming it, and
            # a waiter that gave up announcing would be starved by a caller that
            # polls the board several times a second.
            if timeout > 0 and not queued:
                queued = _lock_byte(handle, _QUEUE_BYTE)
            if _lock_byte(handle, _CLAIM_BYTE):
                break
            if time.monotonic() >= deadline:
                raise RFSoCBusyError(
                    f"the RFSoC is being driven by another process "
                    f"({_read_holder(handle)}) and did not release it within "
                    f"{max(0.0, float(timeout)):.3g} s; pause the live count "
                    f"plot or let the running scan finish, then retry"
                )
            time.sleep(_POLL_SECONDS)
        if queued:
            _unlock_byte(handle, _QUEUE_BYTE)
            queued = False
        _write_holder(handle)
        try:
            yield path
        finally:
            _unlock_byte(handle, _CLAIM_BYTE)
    finally:
        if queued:
            _unlock_byte(handle, _QUEUE_BYTE)
        handle.close()


def board_claim(host, *, timeout=0.0, yield_to_waiters=False):
    """Hold the claim on the board reachable at *host*."""
    return file_claim(
        claim_path(host), timeout=timeout, yield_to_waiters=yield_to_waiters
    )
