"""Thread-safe bridge for GUI operations in the Napari Scanning SPD application.

Provides a QObject-based bridge that uses pyqtSignal to safely marshal
GUI operations from background threads to the main Qt thread.
"""

from PyQt5.QtCore import QObject, pyqtSignal
from napari.utils.notifications import show_info


class GUIBridge(QObject):
    """Centralized bridge for thread-safe GUI updates.

    All public methods can be called safely from any thread.
    They emit Qt signals that are processed on the main thread
    via Qt's queued connection mechanism.
    """
    _notify_signal = pyqtSignal(str)
    _run_on_main_signal = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._notify_signal.connect(self._on_notify)
        self._run_on_main_signal.connect(self._on_run_on_main)

    def notify(self, msg: str):
        """Thread-safe wrapper for napari show_info. Safe to call from any thread."""
        self._notify_signal.emit(msg)

    def run_on_main(self, func):
        """Schedule a callable to execute on the main (GUI) thread.

        The callable is executed asynchronously -- this method returns immediately.
        """
        self._run_on_main_signal.emit(func)

    def _on_notify(self, msg):
        show_info(msg)

    def _on_run_on_main(self, func):
        try:
            func()
        except Exception as e:
            show_info(f"Error in main-thread callback: {e}")
