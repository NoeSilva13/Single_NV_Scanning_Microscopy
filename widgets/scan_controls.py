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
from PyQt5.QtWidgets import QWidget, QGridLayout, QLabel, QDoubleSpinBox, QSpinBox, QPushButton
from PyQt5.QtCore import Qt


def new_scan(scan_pattern_func, scan_points_manager, shapes):
    """Factory function to create new_scan widget with dependencies"""
    
    @magicgui(call_button="🔬 New Scan")
    def _new_scan():
        """Initiates a new scan using the current scan parameters from scan_points_manager.
        Runs the scan in a separate thread to prevent UI freezing.
        """
        def run_new_scan():
            # Get current scan points from the manager
            x_points, y_points = scan_points_manager.get_points()
            scan_pattern_func(x_points, y_points)
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
               zoom_level_manager):
    """Factory function to create reset_zoom widget with dependencies"""
    
    @magicgui(call_button="🔄 Reset Zoom")
    def _reset_zoom():
        shapes.data = []  # Clear rectangle
        current_zoom = zoom_level_manager.get_zoom_level()
        
        if current_zoom == 0:
            show_info("🔁 You are already in the original view.")
            return
        
        # Get original points from history or use default values
        if scan_history:
            orig_x_points, orig_y_points = scan_history[0]
        else:
            # Fallback to default values
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
            # Update both managers with the original values
            update_scan_parameters_func(
                x_range=[orig_x_points[0], orig_x_points[-1]],
                y_range=[orig_y_points[0], orig_y_points[-1]],
                x_res=len(orig_x_points),
                y_res=len(orig_y_points)
            )
            scan_points_manager.update_points(
                x_range=[orig_x_points[0], orig_x_points[-1]],
                y_range=[orig_y_points[0], orig_y_points[-1]],
                x_res=len(orig_x_points),
                y_res=len(orig_y_points)
            )
            scan_pattern_func(orig_x_points, orig_y_points)
            shapes.data = []
            update_scan_parameters_widget_func()
            
        threading.Thread(target=run_reset, daemon=True).start()
    
    return _reset_zoom


def update_scan_parameters(scan_params_manager, scan_points_manager):
    """Factory function to create update_scan_parameters widget with dependencies"""
    
    class ScanParametersWidget(QWidget):
        def __init__(self):
            super().__init__()
            self.scan_params_manager = scan_params_manager
            self.scan_points_manager = scan_points_manager
            self.setup_ui()
            
        def setup_ui(self):
            # Create the main layout
            layout = QGridLayout()
            
            # Headers
            layout.addWidget(QLabel("Parameter"), 0, 0)
            layout.addWidget(QLabel("Voltage (V)"), 0, 1)
            layout.addWidget(QLabel("Distance (µm)"), 0, 2)
            
            # Set default values directly in the widget
            default_x_min = -1.0
            default_x_max = 1.0
            default_y_min = -1.0
            default_y_max = 1.0
            default_x_res = 50
            default_y_res = 50
            default_dwell_time = 0.008  # Default dwell time in seconds
            
            # X Min
            layout.addWidget(QLabel("X Min:"), 1, 0)
            self.x_min_spinbox = QDoubleSpinBox()
            self.x_min_spinbox.setRange(-10, 10)
            self.x_min_spinbox.setSingleStep(0.1)
            self.x_min_spinbox.setDecimals(2)
            self.x_min_spinbox.setValue(default_x_min)
            layout.addWidget(self.x_min_spinbox, 1, 1)
            
            self.x_min_label = QLabel(f"{default_x_min * MICRONS_PER_VOLT:.1f}")
            self.x_min_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.x_min_label, 1, 2)
            
            # X Max
            layout.addWidget(QLabel("X Max:"), 2, 0)
            self.x_max_spinbox = QDoubleSpinBox()
            self.x_max_spinbox.setRange(-10, 10)
            self.x_max_spinbox.setSingleStep(0.1)
            self.x_max_spinbox.setDecimals(2)
            self.x_max_spinbox.setValue(default_x_max)
            layout.addWidget(self.x_max_spinbox, 2, 1)
            
            self.x_max_label = QLabel(f"{default_x_max * MICRONS_PER_VOLT:.1f}")
            self.x_max_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.x_max_label, 2, 2)
            
            # Y Min
            layout.addWidget(QLabel("Y Min:"), 3, 0)
            self.y_min_spinbox = QDoubleSpinBox()
            self.y_min_spinbox.setRange(-10, 10)
            self.y_min_spinbox.setSingleStep(0.1)
            self.y_min_spinbox.setDecimals(2)
            self.y_min_spinbox.setValue(default_y_min)
            layout.addWidget(self.y_min_spinbox, 3, 1)
            
            self.y_min_label = QLabel(f"{default_y_min * MICRONS_PER_VOLT:.1f}")
            self.y_min_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.y_min_label, 3, 2)
            
            # Y Max
            layout.addWidget(QLabel("Y Max:"), 4, 0)
            self.y_max_spinbox = QDoubleSpinBox()
            self.y_max_spinbox.setRange(-10, 10)
            self.y_max_spinbox.setSingleStep(0.1)
            self.y_max_spinbox.setDecimals(2)
            self.y_max_spinbox.setValue(default_y_max)
            layout.addWidget(self.y_max_spinbox, 4, 1)
            
            self.y_max_label = QLabel(f"{default_y_max * MICRONS_PER_VOLT:.1f}")
            self.y_max_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.y_max_label, 4, 2)
            
            # X Resolution
            layout.addWidget(QLabel("X Resolution:"), 5, 0)
            self.x_res_spinbox = QSpinBox()
            self.x_res_spinbox.setRange(2, 200)
            self.x_res_spinbox.setValue(default_x_res)
            self.x_res_spinbox.setSuffix(" px")
            layout.addWidget(self.x_res_spinbox, 5, 1, 1, 2)  # Span 2 columns
            
            # Y Resolution
            layout.addWidget(QLabel("Y Resolution:"), 6, 0)
            self.y_res_spinbox = QSpinBox()
            self.y_res_spinbox.setRange(2, 200)
            self.y_res_spinbox.setValue(default_y_res)
            self.y_res_spinbox.setSuffix(" px")
            layout.addWidget(self.y_res_spinbox, 6, 1, 1, 2)  # Span 2 columns
            
            # Dwell Time
            layout.addWidget(QLabel("Dwell Time:"), 7, 0)
            self.dwell_time_spinbox = QDoubleSpinBox()
            self.dwell_time_spinbox.setRange(0.001, 10.0)  # 1ms to 10s
            self.dwell_time_spinbox.setSingleStep(0.001)
            self.dwell_time_spinbox.setDecimals(3)
            self.dwell_time_spinbox.setValue(default_dwell_time)
            self.dwell_time_spinbox.setSuffix(" s")
            layout.addWidget(self.dwell_time_spinbox, 7, 1, 1, 2)  # Span 2 columns
            
            # Apply button
            self.apply_button = QPushButton("Apply Changes")
            layout.addWidget(self.apply_button, 8, 0, 1, 3)  # Span all columns
            
            self.setLayout(layout)
            
            # Connect signals
            self.x_min_spinbox.valueChanged.connect(self.update_x_min_distance)
            self.x_max_spinbox.valueChanged.connect(self.update_x_max_distance)
            self.y_min_spinbox.valueChanged.connect(self.update_y_min_distance)
            self.y_max_spinbox.valueChanged.connect(self.update_y_max_distance)
            self.apply_button.clicked.connect(self.apply_changes)
        
        def get_parameters(self):
            """Get all parameters from the GUI (similar to odmr_gui_qt.py)"""
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
                    'dwell_time': self.dwell_time_spinbox.value()
                }
            except Exception as e:
                show_info(f"Error getting parameters: {e}")
                return None
            
        def update_x_min_distance(self, value):
            self.x_min_label.setText(f"{value * MICRONS_PER_VOLT:.1f}")
            
        def update_x_max_distance(self, value):
            self.x_max_label.setText(f"{value * MICRONS_PER_VOLT:.1f}")
            
        def update_y_min_distance(self, value):
            self.y_min_label.setText(f"{value * MICRONS_PER_VOLT:.1f}")
            
        def update_y_max_distance(self, value):
            self.y_max_label.setText(f"{value * MICRONS_PER_VOLT:.1f}")
            
        def apply_changes(self):
            # Update scan parameters manager (this will call back to get_parameters)
            params = self.get_parameters()
            if params:
                # Update scan points manager
                self.scan_points_manager.update_points(
                    x_range=params['scan_range']['x'],
                    y_range=params['scan_range']['y'],
                    x_res=params['resolution']['x'],
                    y_res=params['resolution']['y']
                )
                
                show_info('⚠️ Scan parameters updated successfully!')
            
        def update_values(self, x_range, y_range, x_res, y_res, dwell_time=None):
            """Update all widget values"""
            self.x_min_spinbox.setValue(x_range[0])
            self.x_max_spinbox.setValue(x_range[1])
            self.y_min_spinbox.setValue(y_range[0])
            self.y_max_spinbox.setValue(y_range[1])
            self.x_res_spinbox.setValue(x_res)
            self.y_res_spinbox.setValue(y_res)
            
            # Update dwell time if provided
            if dwell_time is not None:
                self.dwell_time_spinbox.setValue(dwell_time)
            
            # Update distance labels
            self.x_min_label.setText(f"{x_range[0] * MICRONS_PER_VOLT:.1f}")
            self.x_max_label.setText(f"{x_range[1] * MICRONS_PER_VOLT:.1f}")
            self.y_min_label.setText(f"{y_range[0] * MICRONS_PER_VOLT:.1f}")
            self.y_max_label.setText(f"{y_range[1] * MICRONS_PER_VOLT:.1f}")
    
    widget_instance = ScanParametersWidget()
    # Set the widget instance in the scan_params_manager so it can get parameters from it
    scan_params_manager.set_widget_instance(widget_instance)
    return widget_instance


def update_scan_parameters_widget(widget_instance, scan_params_manager):
    """Update the scan parameters widget with current values."""
    def _update_widget():
        params = scan_params_manager.get_params()
        x_range = params['scan_range']['x']
        y_range = params['scan_range']['y']
        x_res = params['resolution']['x']
        y_res = params['resolution']['y']
        dwell_time = params['dwell_time']
        
        widget_instance.update_values(x_range, y_range, x_res, y_res, dwell_time)
    
    return _update_widget


def stop_scan(scan_in_progress, stop_scan_requested):
    """Factory function to create stop_scan widget with dependencies"""
    
    @magicgui(call_button="🛑 Stop Scan")
    def _stop_scan():
        """Safely stop the current scanning process."""
        if scan_in_progress[0]:  # Use list to allow modification of mutable object
            stop_scan_requested[0] = True
            show_info("🛑 Stopping scan... Please wait.")
        else:
            show_info("ℹ️ No scan currently in progress.")
    
    return _stop_scan 