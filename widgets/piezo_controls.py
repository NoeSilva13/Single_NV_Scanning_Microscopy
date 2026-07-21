"""
Piezo Z-axis control widget for the Napari Scanning SPD application.

This widget commands the objective piezo Z position through the DAQ analog
output (see ``DAQZController``). It lets the user:
- View the last commanded position
- Set a position via a spinbox (debounced)

The piezo is initialized/kept in closed loop by external Thorlabs software; this
widget only sends the position command as a voltage. There is no analog
readback, so the displayed position is the last commanded value.
"""

import threading

from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QDoubleSpinBox
)
from qtpy.QtCore import Qt, Signal as pyqtSignal, QTimer
from napari.utils.notifications import show_info

from utils import Z_MAX_TRAVEL_UM


class PiezoControlWidget(QWidget):
    """Widget for commanding the Z-axis piezo via the DAQ analog output."""
    _update_position_signal = pyqtSignal(float)
    _notify_signal = pyqtSignal(str)

    def __init__(self, z_controller, scan_in_progress=None, parent=None):
        super().__init__(parent)
        self.z_controller = z_controller
        # Mutable single-element flag shared with the scan engine; when a scan
        # owns the DAQ (ao2 reserved), manual Z moves must be refused.
        self.scan_in_progress = scan_in_progress
        self._pending_position = 0.0
        self.setup_ui()

        self._update_position_signal.connect(self._set_position_ui)
        self._notify_signal.connect(self._on_notify)

        self.pos_spinbox.setEnabled(self.z_controller.available)
        self._update_position_signal.emit(self.z_controller.position)

    def setup_ui(self):
        """Set up the user interface"""
        layout = QVBoxLayout()
        self.setLayout(layout)

        title = QLabel("Z-Axis Control (µm)")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        controls_layout = QHBoxLayout()

        pos_label = QLabel("Position:")
        controls_layout.addWidget(pos_label)

        # Position spinbox spanning the full travel range.
        self.pos_spinbox = QDoubleSpinBox()
        self.pos_spinbox.setRange(0, Z_MAX_TRAVEL_UM)
        self.pos_spinbox.setDecimals(2)
        self.pos_spinbox.setSingleStep(0.1)  # 100 nm step for fine control
        self.pos_spinbox.setFixedWidth(105)

        # Debounce spinbox edits so we only move after the user stops typing.
        self._move_timer = QTimer()
        self._move_timer.setSingleShot(True)
        # DAQ writes are far faster than the old USB path, so a short debounce
        # is enough to coalesce rapid spinbox edits without flooding ao2.
        self._move_timer.setInterval(150)
        self._move_timer.timeout.connect(self._on_move_timer_fired)
        self.pos_spinbox.valueChanged.connect(self._on_spinbox_changed)

        controls_layout.addWidget(self.pos_spinbox)
        controls_layout.addStretch()
        layout.addLayout(controls_layout)

        self.setFixedSize(220, 60)

    def _on_spinbox_changed(self, value):
        """Restart the debounce timer on every value change"""
        self._pending_position = value
        self._move_timer.start()

    def _on_move_timer_fired(self):
        """Called once, 500 ms after the last spinbox change"""
        self._move_piezo(self._pending_position)

    def _move_piezo(self, position_um: float):
        """Command the piezo to ``position_um`` in a background thread."""
        # Refuse manual moves while a scan owns the DAQ (ao2 is reserved by the
        # hardware-timed task; an ephemeral write would collide).
        if self.scan_in_progress is not None and self.scan_in_progress[0]:
            self._notify_signal.emit("⚠️ Scan in progress; Z move ignored")
            self._update_position_signal.emit(self.z_controller.position)
            return

        def move():
            if not self.z_controller.available:
                self._notify_signal.emit("❌ Z control via DAQ not available")
                return
            try:
                effective = self.z_controller.set_position(position_um)
                self._notify_signal.emit(f"✓ Moved to {effective:.2f} µm")
            except Exception as e:
                self._notify_signal.emit(f"❌ Error: {str(e)}")

        threading.Thread(target=move, daemon=True).start()

    def _update_ui_with_current_position(self):
        """Refresh the displayed position (last commanded value)."""
        self._update_position_signal.emit(self.z_controller.position)

    def _set_position_ui(self, position):
        """Update position widgets on the main thread"""
        self.pos_spinbox.blockSignals(True)
        self.pos_spinbox.setValue(position)
        self.pos_spinbox.blockSignals(False)

    def _on_notify(self, msg):
        """Show notification on the main thread"""
        show_info(msg)

    def cleanup(self):
        """Cleanup resources when closing"""
        self.z_controller.close()
