"""
Laser control widget for the Napari Scanning SPD application.

Provides a single toggle button that drives channel 0 of the Swabian Pulse
Streamer HIGH (laser ON) or LOW (laser OFF). The laser starts OFF by default
and can be turned on manually for alignment, or automatically by the scan
routine for the duration of an image acquisition.

Author: Javier Noé Ramos Silva
Contact: jramossi@uci.edu
Lab: Burke Lab, Department of Electrical Engineering and Computer Science,
     University of California, Irvine
"""

import threading
from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from napari.utils.notifications import show_info


class LaserControlWidget(QWidget):
    """Widget that toggles the laser (AOM) channel of the Pulse Streamer.

    The widget calls :meth:`SwabianPulseController.laser_on` /
    :meth:`SwabianPulseController.laser_off` to drive channel 0 of the
    Pulse Streamer HIGH or LOW. It also exposes :meth:`set_laser_on` and
    :meth:`set_laser_off` helpers so the scan routine (or any other caller)
    can programmatically switch the laser while keeping the GUI in sync.
    """

    _set_button_state_signal = pyqtSignal(bool)
    _set_status_signal = pyqtSignal(str)
    _notify_signal = pyqtSignal(str)

    def __init__(self, pulse_controller=None, parent=None):
        super().__init__(parent)
        self.pulse_controller = pulse_controller
        self._is_on = False
        self._scan_override = False  # True while a scan is forcing the laser ON
        self._lock = threading.Lock()

        self._build_ui()

        self._set_button_state_signal.connect(self._apply_button_state)
        self._set_status_signal.connect(self._apply_status)
        self._notify_signal.connect(self._on_notify)

        self._refresh_connection_status()
        # Ensure the laser is OFF at startup regardless of prior state.
        self.set_laser_off(notify=False)

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 4, 8, 4)
        self.setLayout(layout)

        title = QLabel("Laser (PS Ch 0)")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        controls_layout = QHBoxLayout()

        self.toggle_button = QPushButton("Laser OFF")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(False)
        self.toggle_button.setFixedSize(140, 40)
        self.toggle_button.clicked.connect(self._on_button_clicked)
        self._style_button(False)
        controls_layout.addWidget(self.toggle_button)

        self.status_label = QLabel("Disconnected")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFixedWidth(120)
        controls_layout.addWidget(self.status_label)
        controls_layout.addStretch()

        layout.addLayout(controls_layout)
        self.setFixedSize(320, 90)

    def _style_button(self, is_on: bool):
        """Update button label, color and checked state to reflect laser state."""
        if is_on:
            self.toggle_button.setText("Laser ON")
            self.toggle_button.setStyleSheet(
                "QPushButton { background-color: #4CAF50; color: white; "
                "font-weight: bold; border-radius: 4px; }"
            )
        else:
            self.toggle_button.setText("Laser OFF")
            self.toggle_button.setStyleSheet(
                "QPushButton { background-color: #555; color: white; "
                "font-weight: bold; border-radius: 4px; }"
            )
        self.toggle_button.blockSignals(True)
        self.toggle_button.setChecked(is_on)
        self.toggle_button.blockSignals(False)

    def _on_button_clicked(self, checked: bool):
        """Handle user clicks on the toggle button."""
        if self._scan_override:
            self._notify_signal.emit(
                "⚠️ Laser is locked ON during scan. Stop the scan to control it manually."
            )
            self._set_button_state_signal.emit(True)
            return

        if checked:
            self.set_laser_on()
        else:
            self.set_laser_off()

    def set_laser_on(self, notify: bool = True) -> bool:
        """Drive Pulse Streamer channel 0 HIGH (laser ON). Thread-safe.

        Args:
            notify: If True, emits a Napari notification on success/failure.

        Returns:
            bool: True if the command succeeded.
        """
        with self._lock:
            if not self._has_controller():
                if notify:
                    self._notify_signal.emit("❌ Pulse Streamer not connected")
                return False
            ok = self.pulse_controller.laser_on()
            self._is_on = ok
            self._set_button_state_signal.emit(ok)
            if notify:
                self._notify_signal.emit(
                    "💡 Laser ON" if ok else "❌ Failed to turn laser ON"
                )
            return ok

    def set_laser_off(self, notify: bool = True) -> bool:
        """Drive all Pulse Streamer channels LOW (laser OFF). Thread-safe.

        Args:
            notify: If True, emits a Napari notification on success/failure.

        Returns:
            bool: True if the command succeeded.
        """
        with self._lock:
            if not self._has_controller():
                # Still reflect intended OFF state in UI even if not connected.
                self._is_on = False
                self._set_button_state_signal.emit(False)
                if notify:
                    self._notify_signal.emit("❌ Pulse Streamer not connected")
                return False
            ok = self.pulse_controller.laser_off()
            self._is_on = False if ok else self._is_on
            self._set_button_state_signal.emit(self._is_on)
            if notify:
                self._notify_signal.emit(
                    "💡 Laser OFF" if ok else "❌ Failed to turn laser OFF"
                )
            return ok

    def begin_scan_override(self) -> bool:
        """Force the laser ON for the duration of a scan.

        While the override is active, manual toggling is disabled and the
        button reflects the ON state. The previous laser state is remembered
        so it can be restored by :meth:`end_scan_override`.

        Returns:
            bool: True if the laser was successfully turned ON.
        """
        with self._lock:
            self._pre_scan_state = self._is_on
            self._scan_override = True
        ok = self.set_laser_on(notify=False)
        if ok:
            self._notify_signal.emit("💡 Laser ON for scan")
        return ok

    def end_scan_override(self):
        """Release the scan override and restore the pre-scan laser state.

        If the laser was OFF before the scan, it is turned OFF again. If it
        was ON, it stays ON.
        """
        with self._lock:
            previous = getattr(self, "_pre_scan_state", False)
            self._scan_override = False

        if previous:
            self.set_laser_on(notify=False)
            self._notify_signal.emit("💡 Scan finished, laser restored to ON")
        else:
            self.set_laser_off(notify=False)
            self._notify_signal.emit("💡 Scan finished, laser OFF")

    def is_on(self) -> bool:
        """Return True if the laser is currently driven HIGH."""
        return self._is_on

    def _has_controller(self) -> bool:
        return (
            self.pulse_controller is not None
            and getattr(self.pulse_controller, "is_connected", False)
        )

    def _refresh_connection_status(self):
        status = "Connected" if self._has_controller() else "Disconnected"
        self._set_status_signal.emit(status)

    def _apply_button_state(self, is_on: bool):
        self._style_button(is_on)

    def _apply_status(self, status: str):
        colors = {
            "Connected": "#4CAF50",
            "Disconnected": "#F44336",
        }
        color = colors.get(status, "#F44336")
        self.status_label.setText(status)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _on_notify(self, msg: str):
        show_info(msg)

    def cleanup(self):
        """Ensure the laser is OFF when the application closes."""
        try:
            if self._has_controller():
                self.pulse_controller.laser_off()
        except Exception as exc:
            print(f"❌ Error turning laser off during cleanup: {exc}")
