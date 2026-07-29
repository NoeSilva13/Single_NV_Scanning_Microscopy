"""
Manual 3-axis (X, Y, Z) control widget for the Napari Scanning SPD application.

This widget commands every DAQ analog-output axis manually and mirrors the
current commanded position of the scanner:
- Galvo X/Y are driven through the persistent AO task (``output_task``), which
  requires writing both channels at once.
- The piezo Z is driven through the ``DAQZController`` (ephemeral ao2 write).

Each axis has a slider (coarse drag) and a spinbox (fine value) kept in sync.
There is no analog readback, so the displayed position is the last commanded
value. External updates (click-to-move, end of a scan) call
``refresh_positions(...)`` to update the display without moving hardware.
"""

import threading

from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLabel,
    QDoubleSpinBox, QSlider, QSizePolicy
)
from qtpy.QtCore import Qt, Signal as pyqtSignal, QTimer
from napari.utils.notifications import show_info

# Slider works in integers; scale µm by this factor so a slider step maps to
# 0.001 µm (1 nm), matching the piezo's fine resolution.
_SLIDER_SCALE = 1000.0


class AxisControlWidget(QWidget):
    """Widget for manually commanding the galvo X/Y and piezo Z positions."""

    # (x_um, y_um, z_um); any of them may be None to leave that axis unchanged.
    _refresh_signal = pyqtSignal(object, object, object)
    _notify_signal = pyqtSignal(str)

    def __init__(self, axis_x, axis_y, z_controller, output_task,
                 scan_in_progress=None, move_callback=None, parent=None):
        super().__init__(parent)
        self.axis_x = axis_x
        self.axis_y = axis_y
        self.z_controller = z_controller
        self.output_task = output_task
        # Mutable single-element flag shared with the scan engine; when a scan
        # owns the DAQ (ao channels reserved), manual moves must be refused.
        self.scan_in_progress = scan_in_progress
        self.move_callback = move_callback

        # Per-axis metadata: controller/ranges used to build each row.
        self._axes = {
            'x': axis_x,
            'y': axis_y,
            'z': z_controller,
        }
        self.spinboxes = {}
        self.sliders = {}
        self._timers = {}
        self._pending = {'x': 0.0, 'y': 0.0, 'z': 0.0}

        self.setup_ui()

        self._refresh_signal.connect(self._set_positions_ui)
        self._notify_signal.connect(self._on_notify)

        # Reflect the controllers' initial (last commanded) positions.
        self.refresh_positions(
            x=self.axis_x.position,
            y=self.axis_y.position,
            z=self.z_controller.position,
        )

    def setup_ui(self):
        """Build the three-row (X/Y/Z) slider + spinbox grid."""
        layout = QVBoxLayout()
        self.setLayout(layout)

        grid = QGridLayout()
        for row, name in enumerate(('x', 'y', 'z')):
            axis = self._axes[name]
            lo, hi = axis.travel_um
            # Z travel starts at 0 by convention.
            if name == 'z':
                lo = 0.0

            label = QLabel(f"{name.upper()}:")

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setMinimum(int(round(lo * _SLIDER_SCALE)))
            slider.setMaximum(int(round(hi * _SLIDER_SCALE)))
            slider.setMinimumWidth(140)

            spin = QDoubleSpinBox()
            spin.setRange(lo, hi)
            spin.setDecimals(3)
            spin.setSingleStep(0.001)
            spin.setFixedWidth(120)

            # Debounce edits so we only move after the user stops interacting.
            timer = QTimer()
            timer.setSingleShot(True)
            timer.setInterval(150)
            timer.timeout.connect(lambda n=name: self._on_move_timer_fired(n))

            slider.valueChanged.connect(lambda v, n=name: self._on_slider_changed(n, v))
            spin.valueChanged.connect(lambda v, n=name: self._on_spinbox_changed(n, v))

            grid.addWidget(label, row, 0)
            grid.addWidget(slider, row, 1)
            grid.addWidget(spin, row, 2)

            self.spinboxes[name] = spin
            self.sliders[name] = slider
            self._timers[name] = timer

        # Let the slider column absorb the extra horizontal space.
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        self.setMinimumWidth(260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    # ------------------------------------------------------------------
    # User interaction
    # ------------------------------------------------------------------
    def _on_slider_changed(self, name, value):
        """Slider moved: mirror to spinbox (which schedules the move)."""
        spin = self.spinboxes[name]
        um = value / _SLIDER_SCALE
        if abs(spin.value() - um) < 1e-6:
            return
        spin.blockSignals(True)
        spin.setValue(um)
        spin.blockSignals(False)
        self._pending[name] = spin.value()
        self._timers[name].start()

    def _on_spinbox_changed(self, name, value):
        """Spinbox edited: mirror to slider and restart the debounce timer."""
        slider = self.sliders[name]
        slider.blockSignals(True)
        slider.setValue(int(round(value * _SLIDER_SCALE)))
        slider.blockSignals(False)
        self._pending[name] = value
        self._timers[name].start()

    def _on_move_timer_fired(self, name):
        """Fire once, 150 ms after the last change on ``name``."""
        self._move_axis(name, self._pending[name])

    def _move_axis(self, name, position_um):
        """Command axis ``name`` to ``position_um`` (background thread)."""
        # Refuse manual moves while a scan owns the DAQ channels.
        if self.scan_in_progress is not None and self.scan_in_progress[0]:
            self._notify_signal.emit("⚠️ Scan in progress; move ignored")
            self._restore_display()
            return

        if name == 'z':
            self._move_z(position_um)
        else:
            self._move_galvo()

    def _move_galvo(self):
        """Write both galvo channels using the current X/Y spinbox values."""
        x_um = self.spinboxes['x'].value()
        y_um = self.spinboxes['y'].value()

        def move():
            try:
                self.output_task.write([
                    self.axis_x.position_to_voltage(x_um),
                    self.axis_y.position_to_voltage(y_um),
                ])
                if self.move_callback is not None:
                    self.move_callback(x_um, y_um, None)
            except Exception as e:
                self._notify_signal.emit(f"❌ Error moving galvo: {str(e)}")

        threading.Thread(target=move, daemon=True).start()

    def _move_z(self, position_um):
        """Command the piezo Z position on a background thread."""
        def move():
            if not self.z_controller.available:
                self._notify_signal.emit("❌ Z control via DAQ not available")
                return
            try:
                self.z_controller.set_position(position_um)
                if self.move_callback is not None:
                    self.move_callback(None, None, position_um)
            except Exception as e:
                self._notify_signal.emit(f"❌ Error moving Z: {str(e)}")

        threading.Thread(target=move, daemon=True).start()

    # ------------------------------------------------------------------
    # External updates (thread-safe display refresh, no hardware move)
    # ------------------------------------------------------------------
    def refresh_positions(self, x=None, y=None, z=None):
        """Update the displayed positions without commanding a move."""
        self._refresh_signal.emit(x, y, z)

    def _update_ui_with_current_position(self):
        """Refresh Z from the controller's last commanded value."""
        self.refresh_positions(z=self.z_controller.position)

    def z_value(self):
        """Return the current Z spinbox value (µm)."""
        return float(self.spinboxes['z'].value())

    def _set_positions_ui(self, x, y, z):
        """Apply a display refresh on the main thread (no move)."""
        for name, value in (('x', x), ('y', y), ('z', z)):
            if value is None:
                continue
            spin = self.spinboxes[name]
            slider = self.sliders[name]
            spin.blockSignals(True)
            slider.blockSignals(True)
            spin.setValue(value)
            slider.setValue(int(round(value * _SLIDER_SCALE)))
            spin.blockSignals(False)
            slider.blockSignals(False)
            self._pending[name] = spin.value()

    def _restore_display(self):
        """Revert the display to the controllers' last commanded positions."""
        self.refresh_positions(
            x=self.axis_x.position,
            y=self.axis_y.position,
            z=self.z_controller.position,
        )

    def _on_notify(self, msg):
        """Show a notification on the main thread."""
        show_info(msg)

    def cleanup(self):
        """Cleanup resources when closing."""
        self.z_controller.close()
