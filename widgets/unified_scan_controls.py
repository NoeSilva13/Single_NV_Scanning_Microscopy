"""
UnifiedScan Control Widget
-----------------------------------------------------
This module contains widgets for scan control including:
- Unified scan control (XY and Z scanning)
- Scan parameter management
- Progress tracking
"""

import threading
import numpy as np
from magicgui import magicgui
from napari.utils.notifications import show_info
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QProgressBar, QLabel, 
                            QGridLayout, QDoubleSpinBox, QSpinBox, QPushButton, 
                            QComboBox, QGroupBox)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
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
        layout.setSpacing(2)  # Reduce spacing between widgets
        
        # Create group boxes for organization
        xy_group = QGroupBox("X-Y Scan Parameters")
        z_group = QGroupBox("Z-Axis Parameters")
        scan_type_group = QGroupBox("Scan Configuration")
        
        # Set smaller font for all group boxes
        font = xy_group.font()
        font.setPointSize(7)  # Reduce font size
        xy_group.setFont(font)
        z_group.setFont(font)
        scan_type_group.setFont(font)
        
        # X-Y parameters (reuse existing layout)
        xy_layout = QGridLayout()
        xy_layout.setSpacing(3)  # Reduce spacing between grid items
        xy_layout.setContentsMargins(3, 3, 3, 3)  # Reduce margins
        
        # Headers with smaller font
        header_font = QFont(font)
        header_font.setBold(False)
        for label_text in ["Parameter", "Voltage (V)", "Dist (µm)"]:
            label = QLabel(label_text)
            label.setFont(header_font)
            xy_layout.addWidget(label, 0, ["Parameter", "Voltage (V)", "Dist (µm)"].index(label_text))
        
        def create_spinbox(min_val, max_val, step, decimals, value, suffix=""):
            """Helper function to create spinboxes with consistent style"""
            spinbox = QDoubleSpinBox() if decimals > 0 else QSpinBox()
            spinbox.setFont(font)
            spinbox.setRange(min_val, max_val)
            spinbox.setSingleStep(step)
            if decimals > 0:
                spinbox.setDecimals(decimals)
            spinbox.setValue(value)
            if suffix:
                spinbox.setSuffix(suffix)
            spinbox.setFixedHeight(20)  # Reduce height
            return spinbox
            
        def create_label(text, alignment=None):
            """Helper function to create labels with consistent style"""
            label = QLabel(text)
            label.setFont(font)
            if alignment:
                label.setAlignment(alignment)
            label.setFixedHeight(20)  # Reduce height
            return label
        
        # X Min
        xy_layout.addWidget(create_label("X Min:"), 1, 0)
        self.x_min_spinbox = create_spinbox(-10, 10, 0.1, 4, -1.0)
        xy_layout.addWidget(self.x_min_spinbox, 1, 1)
        
        self.x_min_label = create_label(f"{self.x_min_spinbox.value() * MICRONS_PER_VOLT:.2f}", Qt.AlignCenter)
        xy_layout.addWidget(self.x_min_label, 1, 2)
        
        # X Max
        xy_layout.addWidget(create_label("X Max:"), 2, 0)
        self.x_max_spinbox = create_spinbox(-10, 10, 0.1, 4, 1.0)
        xy_layout.addWidget(self.x_max_spinbox, 2, 1)
        
        self.x_max_label = create_label(f"{self.x_max_spinbox.value() * MICRONS_PER_VOLT:.2f}", Qt.AlignCenter)
        xy_layout.addWidget(self.x_max_label, 2, 2)
        
        # Y Min
        xy_layout.addWidget(create_label("Y Min:"), 3, 0)
        self.y_min_spinbox = create_spinbox(-10, 10, 0.1, 4, -1.0)
        xy_layout.addWidget(self.y_min_spinbox, 3, 1)
        
        self.y_min_label = create_label(f"{self.y_min_spinbox.value() * MICRONS_PER_VOLT:.2f}", Qt.AlignCenter)
        xy_layout.addWidget(self.y_min_label, 3, 2)
        
        # Y Max
        xy_layout.addWidget(create_label("Y Max:"), 4, 0)
        self.y_max_spinbox = create_spinbox(-10, 10, 0.1, 4, 1.0)
        xy_layout.addWidget(self.y_max_spinbox, 4, 1)
        
        self.y_max_label = create_label(f"{self.y_max_spinbox.value() * MICRONS_PER_VOLT:.2f}", Qt.AlignCenter)
        xy_layout.addWidget(self.y_max_label, 4, 2)
        
        # X Resolution
        xy_layout.addWidget(create_label("X Resolution:"), 5, 0)
        self.x_res_spinbox = create_spinbox(2, 1000, 1, 0, 50, " px")
        xy_layout.addWidget(self.x_res_spinbox, 5, 1, 1, 2)
        
        # Y Resolution
        xy_layout.addWidget(create_label("Y Resolution:"), 6, 0)
        self.y_res_spinbox = create_spinbox(2, 1000, 1, 0, 50, " px")
        xy_layout.addWidget(self.y_res_spinbox, 6, 1, 1, 2)
        
        xy_group.setLayout(xy_layout)
        
        # Z-axis parameters
        z_layout = QGridLayout()
        z_layout.setSpacing(3)  # Reduce spacing between grid items
        z_layout.setContentsMargins(3, 3, 3, 3)  # Reduce margins
        
        # Z Min
        z_layout.addWidget(create_label("Z Min (µm):"), 0, 0)
        self.z_min_spinbox = create_spinbox(0, 20, 0.1, 3, 0.0)
        z_layout.addWidget(self.z_min_spinbox, 0, 1)
        
        # Z Max
        z_layout.addWidget(create_label("Z Max (µm):"), 1, 0)
        self.z_max_spinbox = create_spinbox(0, 20, 0.1, 3, 5.0)
        z_layout.addWidget(self.z_max_spinbox, 1, 1)
        
        # Z Resolution
        z_layout.addWidget(create_label("Z Resolution:"), 2, 0)
        self.z_res_spinbox = create_spinbox(2, 100, 1, 0, 10, " steps")
        z_layout.addWidget(self.z_res_spinbox, 2, 1)
        
        # Fixed position for X-Z and Y-Z scans
        z_layout.addWidget(create_label("Fixed X (V):"), 3, 0)
        self.fixed_x_spinbox = create_spinbox(-10, 10, 0.1, 4, 0.0)
        z_layout.addWidget(self.fixed_x_spinbox, 3, 1)
        
        z_layout.addWidget(create_label("Fixed Y (V):"), 4, 0)
        self.fixed_y_spinbox = create_spinbox(-10, 10, 0.1, 4, 0.0)
        z_layout.addWidget(self.fixed_y_spinbox, 4, 1)
        
        z_group.setLayout(z_layout)
        
        # Scan type and timing
        scan_layout = QGridLayout()
        scan_layout.setSpacing(3)  # Reduce spacing between grid items
        scan_layout.setContentsMargins(3, 3, 3, 3)  # Reduce margins
        
        # Scan Type Selection
        scan_layout.addWidget(create_label("Scan Type:"), 0, 0)
        self.scan_type_combo = QComboBox()
        self.scan_type_combo.setFont(font)
        self.scan_type_combo.addItems(["X-Y", "X-Z", "Y-Z", "3D"])
        self.scan_type_combo.setFixedHeight(20)  # Reduce height
        scan_layout.addWidget(self.scan_type_combo, 0, 1)
        
        # Dwell Time
        scan_layout.addWidget(create_label("Dwell Time:"), 1, 0)
        self.dwell_time_spinbox = create_spinbox(0.001, 10.0, 0.001, 3, 0.008, " s")
        scan_layout.addWidget(self.dwell_time_spinbox, 1, 1)
        
        # Apply button
        self.apply_button = QPushButton("Apply Changes")
        self.apply_button.setFont(font)
        self.apply_button.setFixedHeight(25)  # Slightly taller for better clickability
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
            
            show_info('✅ Scan parameters updated successfully!')
            
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


class UnifiedScanProgressWidget(QWidget):
    """Unified widget for controlling both XY and Z scans"""
    
    def __init__(self, scan_pattern, scan_points_manager, shapes, z_scan_controller):
        super().__init__()
        self.scan_pattern = scan_pattern
        self.scan_points_manager = scan_points_manager
        self.shapes = shapes
        self.z_scan_controller = z_scan_controller
        self.is_scanning = False
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the user interface"""
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
        self.is_scanning = False


def create_unified_scan_widget(scan_pattern, scan_points_manager, shapes, z_scan_controller, scan_params_manager, z_scan_data_manager):
    """Factory function to create unified scan control widget"""
    
    progress_widget = UnifiedScanProgressWidget(scan_pattern, scan_points_manager, shapes, z_scan_controller)
    
    @magicgui(call_button="🔬 Start Scan")
    def _start_scan():
        """Start scan based on current parameters"""
        if progress_widget.is_scanning:
            show_info("⚠️ Scan already in progress")
            return
            
        params = scan_params_manager.get_params()
        if not params:
            show_info("❌ Error: Could not get scan parameters")
            return
            
        scan_type = params.get('scan_type', 'X-Y')
        progress_widget.is_scanning = True
        
        def run_scan():
            try:
                if scan_type == "X-Y":
                    # Get scan points
                    x_points, y_points = scan_points_manager.get_points()
                    # Run XY scan
                    scan_pattern(x_points, y_points)
                    
                elif scan_type == "X-Z":
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
                    # Save the scan data
                    z_scan_data_manager.save_xz_scan(image, metadata)
                    
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
                    # Save the scan data
                    z_scan_data_manager.save_yz_scan(image, metadata)
                    
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
                    # Save the scan data
                    z_scan_data_manager.save_3d_scan(volume, metadata)
                
                show_info(f"✅ {scan_type} scan completed successfully")
                
            except Exception as e:
                show_info(f"❌ Error during {scan_type} scan: {str(e)}")
                
            finally:
                progress_widget.is_scanning = False
                progress_widget.reset()
                
        threading.Thread(target=run_scan, daemon=True).start()
        show_info(f"🔬 Starting {scan_type} scan...")
        
    return _start_scan


def create_unified_stop_scan_widget(scan_in_progress, stop_scan_requested, z_scan_controller):
    """Factory function to create unified stop scan widget"""
    
    @magicgui(call_button="🛑 Stop Scan")
    def _stop_scan():
        """Stop current scan"""
        if scan_in_progress[0]:
            stop_scan_requested[0] = True
            show_info("🛑 Stopping XY scan...")
        elif z_scan_controller.is_scanning():
            z_scan_controller.stop_scan()
            show_info("🛑 Stopping Z scan...")
        else:
            show_info("ℹ️ No scan currently in progress")
            
    return _stop_scan
