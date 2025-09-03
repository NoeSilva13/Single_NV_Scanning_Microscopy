"""
Z Scan Control Widgets for Napari Scanning SPD Application
--------------------------------------------------------
This module contains widgets for Z-axis scanning functionality including:
- Extended scan parameters with Z-axis controls
- Scan type selection (X-Y, X-Z, Y-Z, 3D)
- Z scan execution controls
- Progress tracking for Z scans
"""

import threading
import numpy as np
from magicgui import magicgui
from napari.utils.notifications import show_info
from PyQt5.QtWidgets import (QWidget, QGridLayout, QLabel, QDoubleSpinBox, 
                            QSpinBox, QPushButton, QComboBox, QGroupBox, 
                            QVBoxLayout, QHBoxLayout, QProgressBar)
from PyQt5.QtCore import Qt, pyqtSignal
from utils import MICRONS_PER_VOLT


class ExtendedScanParametersWidget(QWidget):
    """Extended scan parameters widget with Z-axis controls"""
    
    def __init__(self, scan_params_manager, scan_points_manager):
        super().__init__()
        self.scan_params_manager = scan_params_manager
        self.scan_points_manager = scan_points_manager
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout()
        
        # Create group boxes for organization
        xy_group = QGroupBox("X-Y Scan Parameters")
        z_group = QGroupBox("Z-Axis Parameters")
        scan_type_group = QGroupBox("Scan Configuration")
        
        # X-Y parameters (reuse existing layout)
        xy_layout = QGridLayout()
        
        # Headers
        xy_layout.addWidget(QLabel("Parameter"), 0, 0)
        xy_layout.addWidget(QLabel("Voltage (V)"), 0, 1)
        xy_layout.addWidget(QLabel("Dist (µm)"), 0, 2)
        
        # X Min
        xy_layout.addWidget(QLabel("X Min:"), 1, 0)
        self.x_min_spinbox = QDoubleSpinBox()
        self.x_min_spinbox.setRange(-10, 10)
        self.x_min_spinbox.setSingleStep(0.1)
        self.x_min_spinbox.setDecimals(4)
        self.x_min_spinbox.setValue(-1.0)
        xy_layout.addWidget(self.x_min_spinbox, 1, 1)
        
        self.x_min_label = QLabel(f"{self.x_min_spinbox.value() * MICRONS_PER_VOLT:.2f}")
        self.x_min_label.setAlignment(Qt.AlignCenter)
        xy_layout.addWidget(self.x_min_label, 1, 2)
        
        # X Max
        xy_layout.addWidget(QLabel("X Max:"), 2, 0)
        self.x_max_spinbox = QDoubleSpinBox()
        self.x_max_spinbox.setRange(-10, 10)
        self.x_max_spinbox.setSingleStep(0.1)
        self.x_max_spinbox.setDecimals(4)
        self.x_max_spinbox.setValue(1.0)
        xy_layout.addWidget(self.x_max_spinbox, 2, 1)
        
        self.x_max_label = QLabel(f"{self.x_max_spinbox.value() * MICRONS_PER_VOLT:.2f}")
        self.x_max_label.setAlignment(Qt.AlignCenter)
        xy_layout.addWidget(self.x_max_label, 2, 2)
        
        # Y Min
        xy_layout.addWidget(QLabel("Y Min:"), 3, 0)
        self.y_min_spinbox = QDoubleSpinBox()
        self.y_min_spinbox.setRange(-10, 10)
        self.y_min_spinbox.setSingleStep(0.1)
        self.y_min_spinbox.setDecimals(4)
        self.y_min_spinbox.setValue(-1.0)
        xy_layout.addWidget(self.y_min_spinbox, 3, 1)
        
        self.y_min_label = QLabel(f"{self.y_min_spinbox.value() * MICRONS_PER_VOLT:.2f}")
        self.y_min_label.setAlignment(Qt.AlignCenter)
        xy_layout.addWidget(self.y_min_label, 3, 2)
        
        # Y Max
        xy_layout.addWidget(QLabel("Y Max:"), 4, 0)
        self.y_max_spinbox = QDoubleSpinBox()
        self.y_max_spinbox.setRange(-10, 10)
        self.y_max_spinbox.setSingleStep(0.1)
        self.y_max_spinbox.setDecimals(4)
        self.y_max_spinbox.setValue(1.0)
        xy_layout.addWidget(self.y_max_spinbox, 4, 1)
        
        self.y_max_label = QLabel(f"{self.y_max_spinbox.value() * MICRONS_PER_VOLT:.2f}")
        self.y_max_label.setAlignment(Qt.AlignCenter)
        xy_layout.addWidget(self.y_max_label, 4, 2)
        
        # X Resolution
        xy_layout.addWidget(QLabel("X Resolution:"), 5, 0)
        self.x_res_spinbox = QSpinBox()
        self.x_res_spinbox.setRange(2, 1000)
        self.x_res_spinbox.setValue(50)
        self.x_res_spinbox.setSuffix(" px")
        xy_layout.addWidget(self.x_res_spinbox, 5, 1, 1, 2)
        
        # Y Resolution
        xy_layout.addWidget(QLabel("Y Resolution:"), 6, 0)
        self.y_res_spinbox = QSpinBox()
        self.y_res_spinbox.setRange(2, 1000)
        self.y_res_spinbox.setValue(50)
        self.y_res_spinbox.setSuffix(" px")
        xy_layout.addWidget(self.y_res_spinbox, 6, 1, 1, 2)
        
        xy_group.setLayout(xy_layout)
        
        # Z-axis parameters
        z_layout = QGridLayout()
        
        # Z Min
        z_layout.addWidget(QLabel("Z Min (µm):"), 0, 0)
        self.z_min_spinbox = QDoubleSpinBox()
        self.z_min_spinbox.setRange(0, 20)
        self.z_min_spinbox.setSingleStep(0.1)
        self.z_min_spinbox.setDecimals(3)
        self.z_min_spinbox.setValue(0.0)
        z_layout.addWidget(self.z_min_spinbox, 0, 1)
        
        # Z Max
        z_layout.addWidget(QLabel("Z Max (µm):"), 1, 0)
        self.z_max_spinbox = QDoubleSpinBox()
        self.z_max_spinbox.setRange(0, 20)
        self.z_max_spinbox.setSingleStep(0.1)
        self.z_max_spinbox.setDecimals(3)
        self.z_max_spinbox.setValue(5.0)
        z_layout.addWidget(self.z_max_spinbox, 1, 1)
        
        # Z Resolution
        z_layout.addWidget(QLabel("Z Resolution:"), 2, 0)
        self.z_res_spinbox = QSpinBox()
        self.z_res_spinbox.setRange(2, 100)
        self.z_res_spinbox.setValue(10)
        self.z_res_spinbox.setSuffix(" steps")
        z_layout.addWidget(self.z_res_spinbox, 2, 1)
        
        # Fixed position for X-Z and Y-Z scans
        z_layout.addWidget(QLabel("Fixed X (V):"), 3, 0)
        self.fixed_x_spinbox = QDoubleSpinBox()
        self.fixed_x_spinbox.setRange(-10, 10)
        self.fixed_x_spinbox.setSingleStep(0.1)
        self.fixed_x_spinbox.setDecimals(4)
        self.fixed_x_spinbox.setValue(0.0)
        z_layout.addWidget(self.fixed_x_spinbox, 3, 1)
        
        z_layout.addWidget(QLabel("Fixed Y (V):"), 4, 0)
        self.fixed_y_spinbox = QDoubleSpinBox()
        self.fixed_y_spinbox.setRange(-10, 10)
        self.fixed_y_spinbox.setSingleStep(0.1)
        self.fixed_y_spinbox.setDecimals(4)
        self.fixed_y_spinbox.setValue(0.0)
        z_layout.addWidget(self.fixed_y_spinbox, 4, 1)
        
        z_group.setLayout(z_layout)
        
        # Scan type and timing
        scan_layout = QGridLayout()
        
        # Scan Type Selection
        scan_layout.addWidget(QLabel("Scan Type:"), 0, 0)
        self.scan_type_combo = QComboBox()
        self.scan_type_combo.addItems(["X-Y", "X-Z", "Y-Z", "3D"])
        scan_layout.addWidget(self.scan_type_combo, 0, 1)
        
        # Dwell Time
        scan_layout.addWidget(QLabel("Dwell Time:"), 1, 0)
        self.dwell_time_spinbox = QDoubleSpinBox()
        self.dwell_time_spinbox.setRange(0.001, 10.0)
        self.dwell_time_spinbox.setSingleStep(0.001)
        self.dwell_time_spinbox.setDecimals(3)
        self.dwell_time_spinbox.setValue(0.008)
        self.dwell_time_spinbox.setSuffix(" s")
        scan_layout.addWidget(self.dwell_time_spinbox, 1, 1)
        
        # Apply button
        self.apply_button = QPushButton("Apply Changes")
        scan_layout.addWidget(self.apply_button, 2, 0, 1, 2)
        
        scan_type_group.setLayout(scan_layout)
        
        # Add all groups to main layout
        layout.addWidget(xy_group)
        layout.addWidget(z_group)
        layout.addWidget(scan_type_group)
        
        self.setLayout(layout)
        
        # Connect signals
        self.connect_signals()
        
    def connect_signals(self):
        """Connect all signal handlers"""
        # X-Y parameter signals
        self.x_min_spinbox.valueChanged.connect(self.update_x_min_distance)
        self.x_max_spinbox.valueChanged.connect(self.update_x_max_distance)
        self.y_min_spinbox.valueChanged.connect(self.update_y_min_distance)
        self.y_max_spinbox.valueChanged.connect(self.update_y_max_distance)
        
        # Scan type change
        self.scan_type_combo.currentTextChanged.connect(self.on_scan_type_changed)
        
        # Apply button
        self.apply_button.clicked.connect(self.apply_changes)
        
    def get_parameters(self):
        """Get all parameters from the GUI"""
        try:
            scan_type = self.scan_type_combo.currentText()
            
            params = {
                'scan_type': scan_type,
                'scan_range': {
                    'x': [self.x_min_spinbox.value(), self.x_max_spinbox.value()],
                    'y': [self.y_min_spinbox.value(), self.y_max_spinbox.value()],
                    'z': [self.z_min_spinbox.value(), self.z_max_spinbox.value()]
                },
                'resolution': {
                    'x': self.x_res_spinbox.value(),
                    'y': self.y_res_spinbox.value(),
                    'z': self.z_res_spinbox.value()
                },
                'dwell_time': self.dwell_time_spinbox.value(),
                'fixed_positions': {
                    'x': self.fixed_x_spinbox.value(),
                    'y': self.fixed_y_spinbox.value()
                }
            }
            
            return params
            
        except Exception as e:
            show_info(f"Error getting parameters: {e}")
            return None
            
    def update_x_min_distance(self, value):
        self.x_min_label.setText(f"{value * MICRONS_PER_VOLT:.2f}")
        
    def update_x_max_distance(self, value):
        self.x_max_label.setText(f"{value * MICRONS_PER_VOLT:.2f}")
        
    def update_y_min_distance(self, value):
        self.y_min_label.setText(f"{value * MICRONS_PER_VOLT:.2f}")
        
    def update_y_max_distance(self, value):
        self.y_max_label.setText(f"{value * MICRONS_PER_VOLT:.2f}")
        
    def on_scan_type_changed(self, scan_type):
        """Handle scan type changes"""
        # Enable/disable relevant controls based on scan type
        if scan_type == "X-Z":
            self.fixed_y_spinbox.setEnabled(True)
            self.fixed_x_spinbox.setEnabled(False)
        elif scan_type == "Y-Z":
            self.fixed_x_spinbox.setEnabled(True)
            self.fixed_y_spinbox.setEnabled(False)
        elif scan_type == "3D":
            self.fixed_x_spinbox.setEnabled(False)
            self.fixed_y_spinbox.setEnabled(False)
        else:  # X-Y
            self.fixed_x_spinbox.setEnabled(False)
            self.fixed_y_spinbox.setEnabled(False)
            
    def apply_changes(self):
        """Apply parameter changes"""
        params = self.get_parameters()
        if params:
            # Update scan points manager
            self.scan_points_manager.update_points(
                x_range=params['scan_range']['x'],
                y_range=params['scan_range']['y'],
                x_res=params['resolution']['x'],
                y_res=params['resolution']['y']
            )
            
            show_info('✅ Z scan parameters updated successfully!')
            
    def update_values(self, x_range, y_range, z_range, x_res, y_res, z_res, dwell_time=None):
        """Update all widget values"""
        # X-Y parameters
        self.x_min_spinbox.setValue(x_range[0])
        self.x_max_spinbox.setValue(x_range[1])
        self.y_min_spinbox.setValue(y_range[0])
        self.y_max_spinbox.setValue(y_range[1])
        self.x_res_spinbox.setValue(x_res)
        self.y_res_spinbox.setValue(y_res)
        
        # Z parameters
        self.z_min_spinbox.setValue(z_range[0])
        self.z_max_spinbox.setValue(z_range[1])
        self.z_res_spinbox.setValue(z_res)
        
        # Dwell time
        if dwell_time is not None:
            self.dwell_time_spinbox.setValue(dwell_time)
        
        # Update distance labels
        self.x_min_label.setText(f"{x_range[0] * MICRONS_PER_VOLT:.2f}")
        self.x_max_label.setText(f"{x_range[1] * MICRONS_PER_VOLT:.2f}")
        self.y_min_label.setText(f"{y_range[0] * MICRONS_PER_VOLT:.2f}")
        self.y_max_label.setText(f"{y_range[1] * MICRONS_PER_VOLT:.2f}")


class ZScanProgressWidget(QWidget):
    """Widget for displaying Z scan progress"""
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the progress UI"""
        layout = QVBoxLayout()
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Time remaining label
        self.time_label = QLabel("")
        self.time_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.time_label)
        
        self.setLayout(layout)
        
    def update_progress(self, percentage, status="", time_remaining=""):
        """Update progress display"""
        self.progress_bar.setValue(int(percentage))
        if status:
            self.status_label.setText(status)
        if time_remaining:
            self.time_label.setText(f"Time remaining: {time_remaining}")
            
    def reset(self):
        """Reset progress display"""
        self.progress_bar.setValue(0)
        self.status_label.setText("Ready")
        self.time_label.setText("")


def create_z_scan_widget(z_scan_controller, scan_params_manager, scan_points_manager):
    """Factory function to create Z scan widget"""
    
    @magicgui(call_button="🔬 Start Z Scan")
    def _start_z_scan():
        """Start Z scan based on current parameters"""
        params = scan_params_manager.get_params()
        if not params:
            show_info("❌ Error: Could not get scan parameters")
            return
            
        scan_type = params.get('scan_type', 'X-Y')
        
        if scan_type == "X-Y":
            show_info("ℹ️ Use regular scan for X-Y scanning")
            return
            
        def run_z_scan():
            try:
                if scan_type == "X-Z":
                    x_points = np.linspace(params['scan_range']['x'][0], 
                                         params['scan_range']['x'][1], 
                                         params['resolution']['x'])
                    z_points = np.linspace(params['scan_range']['z'][0], 
                                         params['scan_range']['z'][1], 
                                         params['resolution']['z'])
                    y_fixed = params['fixed_positions']['y']
                    
                    image, metadata = z_scan_controller.scan_xz(
                        x_points, z_points, y_fixed, params['dwell_time']
                    )
                    
                elif scan_type == "Y-Z":
                    y_points = np.linspace(params['scan_range']['y'][0], 
                                         params['scan_range']['y'][1], 
                                         params['resolution']['y'])
                    z_points = np.linspace(params['scan_range']['z'][0], 
                                         params['scan_range']['z'][1], 
                                         params['resolution']['z'])
                    x_fixed = params['fixed_positions']['x']
                    
                    image, metadata = z_scan_controller.scan_yz(
                        y_points, z_points, x_fixed, params['dwell_time']
                    )
                    
                elif scan_type == "3D":
                    x_points = np.linspace(params['scan_range']['x'][0], 
                                         params['scan_range']['x'][1], 
                                         params['resolution']['x'])
                    y_points = np.linspace(params['scan_range']['y'][0], 
                                         params['scan_range']['y'][1], 
                                         params['resolution']['y'])
                    z_points = np.linspace(params['scan_range']['z'][0], 
                                         params['scan_range']['z'][1], 
                                         params['resolution']['z'])
                    
                    volume, metadata = z_scan_controller.scan_3d(
                        x_points, y_points, z_points, params['dwell_time']
                    )
                    
                show_info(f"✅ {scan_type} scan completed successfully")
                
            except Exception as e:
                show_info(f"❌ Error during {scan_type} scan: {str(e)}")
                
        threading.Thread(target=run_z_scan, daemon=True).start()
        show_info(f"🔬 Starting {scan_type} scan...")
        
    return _start_z_scan


def create_stop_z_scan_widget(z_scan_controller):
    """Factory function to create stop Z scan widget"""
    
    @magicgui(call_button="🛑 Stop Z Scan")
    def _stop_z_scan():
        """Stop current Z scan"""
        if z_scan_controller.is_scanning():
            z_scan_controller.stop_scan()
            show_info("🛑 Stopping Z scan...")
        else:
            show_info("ℹ️ No Z scan currently in progress")
            
    return _stop_z_scan
