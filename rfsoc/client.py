"""One QICK-DAWG client session per Python process."""

from __future__ import annotations

from contextlib import contextmanager
import threading

from common.utils import RFSOC_IP, RFSOC_SERVER_NAME


class RFSoCSession:
    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, host=RFSOC_IP, server_name=RFSOC_SERVER_NAME):
        if getattr(self, "_initialized", False):
            if (host, server_name) != (self.host, self.server_name):
                raise RuntimeError("RFSoCSession already initialized for another server")
            return
        self.host = host
        self.server_name = server_name
        self._acquire_lock = threading.Lock()
        self._connected = False
        self._qd = None
        self._initialized = True

    @property
    def connected(self):
        return self._connected

    @property
    def busy(self):
        acquired = self._acquire_lock.acquire(blocking=False)
        if acquired:
            self._acquire_lock.release()
        return not acquired

    def connect(self):
        if self._connected:
            return self
        try:
            import qickdawg as qd
        except ImportError as exc:
            raise RuntimeError(
                "QICK-DAWG is not installed; install the RFSoC requirements"
            ) from exc
        qd.start_client(self.host, server_name=self.server_name)
        if getattr(qd, "soc", None) is None or getattr(qd, "soccfg", None) is None:
            raise RuntimeError("QICK-DAWG did not initialize soc/soccfg")
        self._qd = qd
        self._connected = True
        return self

    @property
    def qd(self):
        return self.connect()._qd

    @property
    def soc(self):
        return self.qd.soc

    @property
    def soccfg(self):
        return self.qd.soccfg

    def new_config(self):
        return self.qd.NVConfiguration()

    @contextmanager
    def acquisition(self, blocking=True):
        self.connect()
        acquired = self._acquire_lock.acquire(blocking=blocking)
        if not acquired:
            raise RuntimeError("RFSoC is busy")
        try:
            yield self
        finally:
            self._acquire_lock.release()

    def close(self):
        """Release local references; the board daemon remains running."""
        self._connected = False
        self._qd = None
