"""
Scan control widgets for the Napari Scanning SPD application.

Contains magicgui widgets for:
- Starting new scans
- Controlling scanner position
- Saving images
- Resetting zoom
- Updating scan parameters
- Stopping ongoing scans
"""

import threading
import json
import numpy as np
from magicgui import magicgui
from napari.utils.notifications import show_info
from utils import MICRONS_PER_VOLT
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QWidget, QGridLayout, QLabel, QDoubleSpinBox, QSpinBox, QComboBox
)

# Supported scan modes exposed by the New Scan selector.
SCAN_MODES = ["XY", "XZ", "YZ", "XYZ"]


def new_scan(run_scan_func, shapes, bridge=None, scan_in_progress=None):
    """Factory function to create the New Scan widget.

    Args:
        run_scan_func: Mode-aware callable (no args) that performs the scan
            synchronously. It is dispatched on a background thread here.
        shapes: Napari shapes layer cleared after the scan starts.
    """

    @magicgui(call_button="🔬 New Scan")
    def _new_scan():
        """Initiate a new scan using the current Scan Parameters (mode-aware)."""
        if scan_in_progress and scan_in_progress[0]:
            show_info("⚠️ A scan is already in progress")
            return

        def run_new_scan():
            run_scan_func()
            if bridge:
                bridge.run_on_main(lambda: setattr(shapes, 'data', []))
            else:
                shapes.data = []
        threading.Thread(target=run_new_scan, daemon=True).start()
        show_info("🔬 New scan started")

    return _new_scan


def close_scanner(output_task):
    """Factory function to create close_scanner widget with dependencies"""
    
    @magicgui(call_button="🎯 Set to Zero")
    def _close_scanner():
        """Sets the Galvo scanner controller to its zero position.
        Runs in a separate thread.
        """
        def run_close():
            output_task.write([0, 0])
        
        threading.Thread(target=run_close, daemon=True).start()
        show_info("🎯 Scanner set to zero")
    
    return _close_scanner


def save_image(viewer, data_path_func):
    """Factory function to create save_image widget with dependencies"""
    
    @magicgui(call_button="📷 Save Image")
    def _save_image():
        """Saves the current view of the Napari canvas as a PNG image.
        The filename is derived from the data_path of the scan.
        """
        data_path = data_path_func()
        if data_path:
            viewer.screenshot(path=f"{data_path}.png", canvas_only=True, flash=True)
            show_info("📷 Image saved")
        else:
            show_info("❌ No scan data to save")
    
    return _save_image


def reset_zoom(scan_pattern_func, scan_history, scan_params_manager, scan_points_manager,
               shapes, update_scan_parameters_func, update_scan_parameters_widget_func,
               zoom_level_manager, bridge=None, scan_in_progress=None):
    """Factory function to create reset_zoom widget with dependencies"""
    
    @magicgui(call_button="🔄 Reset Zoom")
    def _reset_zoom():
        shapes.data = []  # Main thread, safe
        current_zoom = zoom_level_manager.get_zoom_level()
        
        if current_zoom == 0:
            show_info("🔁 You are already in the original view.")
            return

        if scan_in_progress and scan_in_progress[0]:
            show_info("⚠️ A scan is already in progress")
            return
        
        if scan_history:
            orig_x_points, orig_y_points = scan_history[0]
        else:
            params = scan_params_manager.get_params()
            x_range = params['scan_range']['x']
            y_range = params['scan_range']['y']
            x_res = params['resolution']['x']
            y_res = params['resolution']['y']
            orig_x_points = np.linspace(x_range[0], x_range[1], x_res)
            orig_y_points = np.linspace(y_range[0], y_range[1], y_res)
        
        scan_history.clear()
        zoom_level_manager.set_zoom_level(0)

        def run_reset():
            x_r = [orig_x_points[0], orig_x_points[-1]]
            y_r = [orig_y_points[0], orig_y_points[-1]]
            n_x = len(orig_x_points)
            n_y = len(orig_y_points)

            if bridge:
                bridge.run_on_main(lambda: update_scan_parameters_func(
                    x_range=x_r, y_range=y_r, x_res=n_x, y_res=n_y
                ))
            else:
                update_scan_parameters_func(
                    x_range=x_r, y_range=y_r, x_res=n_x, y_res=n_y
                )

            scan_points_manager.update_points(
                x_range=x_r, y_range=y_r, x_res=n_x, y_res=n_y
            )
            scan_pattern_func(orig_x_points, orig_y_points)

            if bridge:
                bridge.run_on_main(lambda: setattr(shapes, 'data', []))
            else:
                shapes.data = []

            update_scan_parameters_widget_func()
            
        threading.Thread(target=run_reset, daemon=True).start()
    
    return _reset_zoom


def update_scan_parameters(scan_params_manager):
    """Factory function to create the Scan Parameters widget.

    Parameters are read live from the spinboxes via
    ``scan_params_manager.get_params()``; New Scan rebuilds XY points from
    those values at start time (no explicit Apply step).
    """
    
    class ScanParametersWidget(QWidget):
        def __init__(self):
            super().__init__()
            self.scan_params_manager = scan_params_manager
            self.setup_ui()
            
        def setup_ui(self):
            # Compact 3-column table: X / Y / Z as columns, and Min / Max /
            # Resolution / Dwell as rows (units in the row labels).
            layout = QGridLayout()
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setHorizontalSpacing(6)
            layout.setVerticalSpacing(4)

            # All axes are edited and stored in micrometers (the canonical unit).
            # The µm <-> volt conversion happens only at the DAQ boundary.
            default_x_min = -1.0 * MICRONS_PER_VOLT
            default_x_max = 1.0 * MICRONS_PER_VOLT
            default_y_min = -1.0 * MICRONS_PER_VOLT
            default_y_max = 1.0 * MICRONS_PER_VOLT
            default_x_res = 50
            default_y_res = 50
            default_dwell_time = 1.0  # Default XY dwell time in milliseconds
            default_z_min = 0.0
            default_z_max = 450.0
            default_z_res = 50
            default_z_dwell = 5.0  # 5 ms default piezo settling (adjust per step size)

            xy_um_limit = 10.0 * MICRONS_PER_VOLT  # ±10 V galvo range in µm
            spin_w = 80  # minimum width; columns stretch to fill extra space

            def _dspin(mn, mx, step, dec, val):
                s = QDoubleSpinBox()
                s.setRange(mn, mx)
                s.setSingleStep(step)
                s.setDecimals(dec)
                s.setValue(val)
                s.setMinimumWidth(spin_w)
                return s

            def _ispin(mn, mx, val):
                s = QSpinBox()
                s.setRange(mn, mx)
                s.setValue(val)
                s.setMinimumWidth(spin_w)
                return s

            # Scan mode selector (controls what the New Scan button acquires)
            layout.addWidget(QLabel("Scan Mode:"), 0, 0)
            self.scan_mode_combo = QComboBox()
            self.scan_mode_combo.addItems(SCAN_MODES)
            self.scan_mode_combo.setCurrentText("XY")
            layout.addWidget(self.scan_mode_combo, 0, 1, 1, 3)

            # Axis column headers
            for col, name in ((1, "X"), (2, "Y"), (3, "Z")):
                header = QLabel(name)
                header.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(header, 1, col)

            # Min row
            layout.addWidget(QLabel("Min (µm):"), 2, 0)
            self.x_min_spinbox = _dspin(-xy_um_limit, xy_um_limit, 1.0, 3, default_x_min)
            self.y_min_spinbox = _dspin(-xy_um_limit, xy_um_limit, 1.0, 3, default_y_min)
            self.z_min_spinbox = _dspin(0.0, 450.0, 1.0, 3, default_z_min)
            layout.addWidget(self.x_min_spinbox, 2, 1)
            layout.addWidget(self.y_min_spinbox, 2, 2)
            layout.addWidget(self.z_min_spinbox, 2, 3)

            # Max row
            layout.addWidget(QLabel("Max (µm):"), 3, 0)
            self.x_max_spinbox = _dspin(-xy_um_limit, xy_um_limit, 1.0, 3, default_x_max)
            self.y_max_spinbox = _dspin(-xy_um_limit, xy_um_limit, 1.0, 3, default_y_max)
            self.z_max_spinbox = _dspin(0.0, 450.0, 1.0, 3, default_z_max)
            layout.addWidget(self.x_max_spinbox, 3, 1)
            layout.addWidget(self.y_max_spinbox, 3, 2)
            layout.addWidget(self.z_max_spinbox, 3, 3)

            # Resolution row
            layout.addWidget(QLabel("Res (px):"), 4, 0)
            self.x_res_spinbox = _ispin(2, 1000, default_x_res)
            self.y_res_spinbox = _ispin(2, 1000, default_y_res)
            self.z_res_spinbox = _ispin(2, 1000, default_z_res)
            layout.addWidget(self.x_res_spinbox, 4, 1)
            layout.addWidget(self.y_res_spinbox, 4, 2)
            layout.addWidget(self.z_res_spinbox, 4, 3)

            # Dwell row (milliseconds): one XY dwell (spans X+Y) and a Z dwell.
            layout.addWidget(QLabel("Dwell (ms):"), 5, 0)
            self.dwell_time_spinbox = _dspin(0.1, 10000.0, 0.1, 3, default_dwell_time)
            self.z_dwell_spinbox = _dspin(0.1, 10000.0, 0.5, 3, default_z_dwell)
            layout.addWidget(self.dwell_time_spinbox, 5, 1, 1, 2)  # XY dwell (X+Y)
            layout.addWidget(self.z_dwell_spinbox, 5, 3)

            # Let the three axis columns share the available width evenly while
            # the label column stays tight.
            layout.setColumnStretch(0, 0)
            layout.setColumnStretch(1, 1)
            layout.setColumnStretch(2, 1)
            layout.setColumnStretch(3, 1)

            self.setLayout(layout)

        def get_parameters(self):
            """Get all parameters from the GUI. All positions are in micrometers
            (the canonical unit); the µm <-> volt conversion is deferred to the
            DAQ boundary (waveform generation / analog writes).
            """
            try:
                return {
                    'scan_range': {
                        'x': [self.x_min_spinbox.value(), self.x_max_spinbox.value()],
                        'y': [self.y_min_spinbox.value(), self.y_max_spinbox.value()]
                    },
                    'resolution': {
                        'x': self.x_res_spinbox.value(),
                        'y': self.y_res_spinbox.value()
                    },
                    # Dwell times are edited in ms but returned in seconds
                    # (the acquisition core works in seconds: rate = 1/dwell).
                    'dwell_time': self.dwell_time_spinbox.value() / 1000.0,
                    'z_scan': {
                        'range': [self.z_min_spinbox.value(), self.z_max_spinbox.value()],
                        'resolution': self.z_res_spinbox.value(),
                        'dwell_time': self.z_dwell_spinbox.value() / 1000.0
                    },
                    'scan_mode': self.scan_mode_combo.currentText()
                }
            except Exception as e:
                show_info(f"Error getting parameters: {e}")
                return None

        def get_scan_mode(self):
            return self.scan_mode_combo.currentText()

        def update_values(self, x_range, y_range, x_res, y_res, dwell_time=None):
            """Update all widget values (x_range/y_range are in micrometers)."""
            self.x_min_spinbox.setValue(x_range[0])
            self.x_max_spinbox.setValue(x_range[1])
            self.y_min_spinbox.setValue(y_range[0])
            self.y_max_spinbox.setValue(y_range[1])
            self.x_res_spinbox.setValue(x_res)
            self.y_res_spinbox.setValue(y_res)

            # Update dwell time if provided (incoming value is in seconds).
            if dwell_time is not None:
                self.dwell_time_spinbox.setValue(dwell_time * 1000.0)
    
    widget_instance = ScanParametersWidget()
    # Set the widget instance in the scan_params_manager so it can get parameters from it
    scan_params_manager.set_widget_instance(widget_instance)
    return widget_instance


def update_scan_parameters_widget(widget_instance, scan_params_manager, bridge=None):
    """Update the scan parameters widget with current values.
    
    When a bridge is provided, the update is marshalled to the main thread
    so that this function is safe to call from any thread.
    """
    def _do_update():
        params = scan_params_manager.get_params()
        x_range = params['scan_range']['x']
        y_range = params['scan_range']['y']
        x_res = params['resolution']['x']
        y_res = params['resolution']['y']
        dwell_time = params['dwell_time']
        widget_instance.update_values(x_range, y_range, x_res, y_res, dwell_time)

    def _update_widget():
        if bridge:
            bridge.run_on_main(_do_update)
        else:
            _do_update()
    
    return _update_widget


def stop_scan(scan_in_progress, stop_scan_requested, scan_task_ref=None, cbm_ref=None, scan_lock=None):
    """Factory function to create stop_scan widget with dependencies.

    Args:
        scan_task_ref: Mutable list holding the hardware-timed DAQ task (or None).
        cbm_ref: Mutable list holding the CountBetweenMarkers measurement (or None).
        scan_lock: threading.Lock protecting shared scan state.
    """
    
    @magicgui(call_button="🛑 Stop Scan")
    def _stop_scan():
        """Safely stop the current scanning process."""
        if scan_lock:
            scan_lock.acquire()
        try:
            if not scan_in_progress[0]:
                show_info("ℹ️ No scan currently in progress.")
                return
            stop_scan_requested[0] = True
            task = scan_task_ref[0] if scan_task_ref is not None else None
            cbm = cbm_ref[0] if cbm_ref is not None else None
        finally:
            if scan_lock:
                scan_lock.release()

        if task is not None:
            try:
                task.stop()
            except Exception:
                pass
        if cbm is not None:
            try:
                cbm.stop()
            except Exception:
                pass
        show_info("🛑 Stopping scan... Please wait.")
    
    return _stop_scan 