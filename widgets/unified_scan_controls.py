"""
Scan Control Widgets for Napari Scanning SPD Application
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
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QProgressBar, QLabel
from PyQt5.QtCore import Qt

class UnifiedScanControlWidget(QWidget):
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


def create_unified_scan_widget(scan_pattern, scan_points_manager, shapes, z_scan_controller, scan_params_manager):
    """Factory function to create unified scan control widget"""
    
    progress_widget = UnifiedScanControlWidget(scan_pattern, scan_points_manager, shapes, z_scan_controller)
    
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
                    
                    z_scan_controller.scan_xz(
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
                    
                    z_scan_controller.scan_yz(
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
                    
                    z_scan_controller.scan_3d(
                        x_points, y_points, z_points, params['dwell_time']
                    )
                
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
