"""
Scan control widgets for the Qt-based Scanning SPD application.

Contains Qt widgets for:
- Starting new scans
- Controlling scanner position
- Saving images
- Resetting zoom
- Updating scan parameters
"""

import threading
import json
import numpy as np
from PyQt5.QtWidgets import (QPushButton, QWidget, QVBoxLayout, QGridLayout, 
                             QLabel, QDoubleSpinBox, QSpinBox, QHBoxLayout, QGroupBox)
from PyQt5.QtCore import Qt


def new_scan(scan_pattern_func, scan_points_manager, status_callback=None):
    """Factory function to create new_scan widget with dependencies"""
    
    button = QPushButton("🔬 New Scan")
    button.setStyleSheet("""
        QPushButton {
            background-color: #00d4aa;
            color: #262930;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 10pt;
        }
        QPushButton:hover {
            background-color: #00ffcc;
        }
        QPushButton:pressed {
            background-color: #009980;
        }
    """)
    
    def _new_scan():
        """Initiates a new scan using the current scan parameters from scan_points_manager.
        Runs the scan in a separate thread to prevent UI freezing.
        """
        def run_new_scan():
            # Get current scan points from the manager
            x_points, y_points = scan_points_manager.get_points()
            scan_pattern_func(x_points, y_points)
        
        threading.Thread(target=run_new_scan, daemon=True).start()
        if status_callback:
            status_callback("🔬 New scan started")
    
    button.clicked.connect(_new_scan)
    return button


def close_scanner(output_task, status_callback=None):
    """Factory function to create close_scanner widget with dependencies"""
    
    button = QPushButton("🎯 Set to Zero")
    button.setStyleSheet("""
        QPushButton {
            background-color: #00d4aa;
            color: #262930;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 10pt;
        }
        QPushButton:hover {
            background-color: #00ffcc;
        }
        QPushButton:pressed {
            background-color: #009980;
        }
    """)
    
    def _close_scanner():
        """Sets the Galvo scanner controller to its zero position.
        Runs in a separate thread.
        """
        def run_close():
            output_task.write([0, 0])
        
        threading.Thread(target=run_close, daemon=True).start()
        if status_callback:
            status_callback("🎯 Scanner set to zero")
    
    button.clicked.connect(_close_scanner)
    return button


def reset_zoom(scan_pattern_func, scan_history, config_manager, scan_points_manager,
               update_scan_parameters_func, update_scan_parameters_widget_func,
               zoom_level_manager, status_callback=None):
    """Factory function to create reset_zoom widget with dependencies"""
    
    button = QPushButton("🔄 Reset Zoom")
    button.setStyleSheet("""
        QPushButton {
            background-color: #00d4aa;
            color: #262930;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 10pt;
        }
        QPushButton:hover {
            background-color: #00ffcc;
        }
        QPushButton:pressed {
            background-color: #009980;
        }
    """)
    
    def _reset_zoom():
        current_zoom = zoom_level_manager.get_zoom_level()
        
        if current_zoom == 0:
            if status_callback:
                status_callback("🔁 You are already in the original view.")
            return
        
        # Get original points from history or use default config values
        if scan_history:
            orig_x_points, orig_y_points = scan_history[0]
        else:
            # Fallback to default config values
            config = config_manager.get_config()
            x_range = config['scan_range']['x']
            y_range = config['scan_range']['y']
            x_res = config['resolution']['x']
            y_res = config['resolution']['y']
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
            update_scan_parameters_widget_func()
            
        threading.Thread(target=run_reset, daemon=True).start()
    
    button.clicked.connect(_reset_zoom)
    return button


class ScanParametersWidget(QWidget):
    """Widget for updating scan parameters"""
    
    def __init__(self, config_manager, scan_points_manager, status_callback=None):
        super().__init__()
        self.config_manager = config_manager
        self.scan_points_manager = scan_points_manager
        self.status_callback = status_callback
        
        self.init_ui()
        self.update_values()
    
    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Create group box
        group_box = QGroupBox("Scan Parameters")
        group_layout = QGridLayout()
        group_box.setLayout(group_layout)
        layout.addWidget(group_box)
        
        # Create spin boxes
        self.x_min_spin = QDoubleSpinBox()
        self.x_min_spin.setRange(-10, 10)
        self.x_min_spin.setSingleStep(0.1)
        self.x_min_spin.setDecimals(2)
        self.x_min_spin.setSuffix(" V")
        
        self.x_max_spin = QDoubleSpinBox()
        self.x_max_spin.setRange(-10, 10)
        self.x_max_spin.setSingleStep(0.1)
        self.x_max_spin.setDecimals(2)
        self.x_max_spin.setSuffix(" V")
        
        self.y_min_spin = QDoubleSpinBox()
        self.y_min_spin.setRange(-10, 10)
        self.y_min_spin.setSingleStep(0.1)
        self.y_min_spin.setDecimals(2)
        self.y_min_spin.setSuffix(" V")
        
        self.y_max_spin = QDoubleSpinBox()
        self.y_max_spin.setRange(-10, 10)
        self.y_max_spin.setSingleStep(0.1)
        self.y_max_spin.setDecimals(2)
        self.y_max_spin.setSuffix(" V")
        
        self.x_res_spin = QSpinBox()
        self.x_res_spin.setRange(2, 200)
        self.x_res_spin.setSuffix(" px")
        
        self.y_res_spin = QSpinBox()
        self.y_res_spin.setRange(2, 200)
        self.y_res_spin.setSuffix(" px")
        
        # Add labels and spin boxes to grid
        group_layout.addWidget(QLabel("X Min:"), 0, 0)
        group_layout.addWidget(self.x_min_spin, 0, 1)
        group_layout.addWidget(QLabel("X Max:"), 0, 2)
        group_layout.addWidget(self.x_max_spin, 0, 3)
        
        group_layout.addWidget(QLabel("Y Min:"), 1, 0)
        group_layout.addWidget(self.y_min_spin, 1, 1)
        group_layout.addWidget(QLabel("Y Max:"), 1, 2)
        group_layout.addWidget(self.y_max_spin, 1, 3)
        
        group_layout.addWidget(QLabel("X Res:"), 2, 0)
        group_layout.addWidget(self.x_res_spin, 2, 1)
        group_layout.addWidget(QLabel("Y Res:"), 2, 2)
        group_layout.addWidget(self.y_res_spin, 2, 3)
        
        # Apply button
        apply_button = QPushButton("Apply Changes")
        apply_button.setStyleSheet("""
            QPushButton {
                background-color: #00d4aa;
                color: #262930;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #00ffcc;
            }
            QPushButton:pressed {
                background-color: #009980;
            }
        """)
        apply_button.clicked.connect(self.apply_changes)
        layout.addWidget(apply_button)
        
        # Style the spin boxes
        spinbox_style = """
            QDoubleSpinBox, QSpinBox {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px;
                font-size: 10pt;
            }
            QDoubleSpinBox:focus, QSpinBox:focus {
                border: 2px solid #00d4aa;
            }
        """
        
        for widget in [self.x_min_spin, self.x_max_spin, self.y_min_spin, 
                      self.y_max_spin, self.x_res_spin, self.y_res_spin]:
            widget.setStyleSheet(spinbox_style)
    
    def update_values(self):
        """Update widget values from config"""
        config = self.config_manager.get_config()
        x_range = config['scan_range']['x']
        y_range = config['scan_range']['y']
        x_res = config['resolution']['x']
        y_res = config['resolution']['y']
        
        self.x_min_spin.setValue(x_range[0])
        self.x_max_spin.setValue(x_range[1])
        self.y_min_spin.setValue(y_range[0])
        self.y_max_spin.setValue(y_range[1])
        self.x_res_spin.setValue(x_res)
        self.y_res_spin.setValue(y_res)
    
    def apply_changes(self):
        """Apply parameter changes"""
        # Update config manager
        self.config_manager.update_scan_parameters(
            x_range=[self.x_min_spin.value(), self.x_max_spin.value()],
            y_range=[self.y_min_spin.value(), self.y_max_spin.value()],
            x_res=self.x_res_spin.value(),
            y_res=self.y_res_spin.value()
        )
        
        # Update scan points manager
        self.scan_points_manager.update_points(
            x_range=[self.x_min_spin.value(), self.x_max_spin.value()],
            y_range=[self.y_min_spin.value(), self.y_max_spin.value()],
            x_res=self.x_res_spin.value(),
            y_res=self.y_res_spin.value()
        )
        
        if self.status_callback:
            self.status_callback('⚠️ Scan parameters updated successfully!')


def update_scan_parameters(config_manager, scan_points_manager, status_callback=None):
    """Factory function to create update_scan_parameters widget with dependencies"""
    return ScanParametersWidget(config_manager, scan_points_manager, status_callback)


def update_scan_parameters_widget(widget_instance, config_manager):
    """Update the scan parameters widget with current values."""
    def _update_widget():
        widget_instance.update_values()
    
    return _update_widget 