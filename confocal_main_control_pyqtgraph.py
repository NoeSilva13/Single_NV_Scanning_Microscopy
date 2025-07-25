"""
Confocal Single-NV Microscopy Control Software (PyQtGraph Version)
----------------------------------------------------------------
This software controls a confocal microscope setup for single NV center imaging using:
- Thorlabs LSKGG4 Galvo-Galvo Scanner
- National Instruments USB-6453 DAQ
- Single Photon Detector SPD

The system provides real-time visualization and control through a PyQtGraph-based GUI
for superior performance in scientific instrumentation applications.
"""

# Standard library imports
import sys
import threading
import time
import os

# Third-party imports
import numpy as np 
import nidaqmx
import pyqtgraph as pg
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QDockWidget, QTabWidget, QMessageBox, QStatusBar, QSplitter,
    QDesktopWidget, QLabel, QPushButton, QGridLayout
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QPixmap, QIcon
from TimeTagger import createTimeTagger, Counter, createTimeTaggerVirtual
from magicgui import magicgui

# Local imports
from galvo_controller import GalvoScannerController
from data_manager import DataManager
from plot_widgets.live_plot_pyqtgraph_widget import live_plot_pyqtgraph as live_plot
from plot_scan_results import plot_scan_results
from utils import (
    calculate_scale, 
    MAX_ZOOM_LEVEL, 
    BINWIDTH,
    save_tiff_with_imagej_metadata
)

# Import extracted widgets
from widgets.scan_controls import (
    new_scan as create_new_scan,
    close_scanner as create_close_scanner,
    save_image as create_save_image,
    reset_zoom as create_reset_zoom,
    update_scan_parameters as create_update_scan_parameters,
    update_scan_parameters_widget as create_update_scan_parameters_widget,
    stop_scan as create_stop_scan
)
from widgets.camera_controls import (
    create_camera_control_widget
)
from widgets.auto_focus import (
    auto_focus as create_auto_focus,
    SignalBridge
)
from widgets.single_axis_scan import SingleAxisScanWidget
from widgets.file_operations import load_scan as create_load_scan
from widgets.odmr_controls import launch_odmr_gui as create_launch_odmr_gui

import qickdawg as qd

# Configure PyQtGraph for better performance
pg.setConfigOptions(antialias=True, useOpenGL=True)
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')

# Initialize qickdawg client
qd.start_client('192.168.1.101')

nv_config = qd.NVConfiguration()
nv_config.adc_channel = 0
nv_config.edge_counting = True
nv_config.high_threshold = 2000
nv_config.low_threshold = 500
nv_config.mw_channel = 0
nv_config.mw_nqz = 1
nv_config.mw_gain = 5000
nv_config.laser_gate_pmod = 0
nv_config.relax_delay_tns = 50 # between each rep, wait for everything to catch up, mostly aom
nv_config.readout_integration_treg = 2**16-1 # Maximum number of integrated points

print(qd.max_int_time_tus)
print(nv_config.readout_integration_tus)

nv_config.reps = 1 

prog = qd.PLIntensity(nv_config) 

def get_cps():
    d = prog.acquire(progress=False)
    return d / qd.max_int_time_treg / qd.min_time_tns * 1e9

# --------------------- NOTIFICATION SYSTEM ---------------------
class NotificationSystem(QObject):
    """Notification system to replace napari's show_info"""
    
    def __init__(self, status_bar=None):
        super().__init__()
        self.status_bar = status_bar
    
    def show_info(self, message):
        """Display information message"""
        print(f"INFO: {message}")
        if self.status_bar:
            self.status_bar.showMessage(message, 3000)  # Show for 3 seconds

# Global notification system (will be initialized with main window)
notification_system = None

def show_info(message):
    """Global function to show info messages"""
    try:
        if notification_system:
            notification_system.show_info(message)
        else:
            print(f"INFO: {message}")
    except Exception as e:
        print(f"INFO: {message}")
        print(f"WARNING: Notification system error: {e}")

# --------------------- CUSTOM IMAGE WIDGET ---------------------
class ScientificImageWidget(QWidget):
    """Custom widget for scientific image display with PyQtGraph"""
    
    # Signals
    mouse_clicked = pyqtSignal(float, float)  # x_voltage, y_voltage
    roi_changed = pyqtSignal(object)  # ROI object
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.image_data = None
        self.x_points = None
        self.y_points = None
        self.roi = None
        
    def setup_ui(self):
        """Setup the image display UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create graphics layout widget
        self.graphics_widget = pg.GraphicsLayoutWidget()
        
        # Create plot item for image display
        self.plot_item = self.graphics_widget.addPlot(title="Live Scan")
        self.plot_item.setAspectLocked(True)
        self.plot_item.showAxis('left', True)
        self.plot_item.showAxis('bottom', True)
        self.plot_item.setLabel('left', 'Y Position (µm)')
        self.plot_item.setLabel('bottom', 'X Position (µm)')
        
        # Create image item
        self.image_item = pg.ImageItem()
        self.plot_item.addItem(self.image_item)
        
        # Create colorbar
        self.colorbar = pg.ColorBarItem(
            values=(0, 10000),
            colorMap=pg.colormap.get('viridis'),
            width=20,
            interactive=True
        )
        self.colorbar.setImageItem(self.image_item, insert_in=self.plot_item)
        
        # Setup mouse click handling
        self.image_item.mouseDoubleClickEvent = self.on_image_double_click
        
        layout.addWidget(self.graphics_widget)
        self.setLayout(layout)
        
    def set_image_data(self, image_data, x_points=None, y_points=None):
        """Set image data and update display"""
        self.image_data = image_data
        self.x_points = x_points
        self.y_points = y_points
        
        if image_data is not None:
            # Set image data
            self.image_item.setImage(image_data, autoLevels=False)
            
            # Update axes ranges if points are provided
            if x_points is not None and y_points is not None:
                # Convert voltage points to micrometers for display
                x_range_um = np.array([x_points[0], x_points[-1]]) * 1000  # Assume mV to µm conversion
                y_range_um = np.array([y_points[0], y_points[-1]]) * 1000
                
                # Set the position and scale of the image
                self.image_item.setRect(pg.QtCore.QRectF(
                    x_range_um[0], y_range_um[0],
                    x_range_um[1] - x_range_um[0],
                    y_range_um[1] - y_range_um[0]
                ))
                
            # Auto-set color levels
            if not np.all(np.isnan(image_data)) and image_data.size > 0:
                min_val = np.nanmin(image_data)
                max_val = np.nanmax(image_data)
                if not np.isclose(min_val, max_val):
                    self.image_item.setLevels([min_val, max_val])
                    self.colorbar.setLevels((min_val, max_val))
    
    def set_contrast_limits(self, vmin, vmax):
        """Set contrast limits"""
        self.image_item.setLevels([vmin, vmax])
        self.colorbar.setLevels((vmin, vmax))
    
    def add_roi(self):
        """Add ROI for zoom selection"""
        if self.roi is not None:
            self.plot_item.removeItem(self.roi)
        
        # Create rectangular ROI
        self.roi = pg.RectROI([0, 0], [100, 100], pen='r')
        self.plot_item.addItem(self.roi)
        
        # Connect ROI change signal
        self.roi.sigRegionChanged.connect(self.on_roi_changed)
        
        return self.roi
    
    def remove_roi(self):
        """Remove current ROI"""
        if self.roi is not None:
            self.plot_item.removeItem(self.roi)
            self.roi = None
    
    def on_roi_changed(self):
        """Handle ROI change"""
        if self.roi is not None:
            self.roi_changed.emit(self.roi)
    
    def on_image_double_click(self, event):
        """Handle double-click on image for scanner positioning"""
        if self.image_data is None or self.x_points is None or self.y_points is None:
            return
            
        # Get click position in image coordinates
        pos = event.pos()
        
        # Convert to data coordinates
        if hasattr(self.image_item, 'mapFromScene'):
            scene_pos = self.image_item.mapFromScene(pos)
            x_idx = int(np.clip(scene_pos.x(), 0, self.image_data.shape[1] - 1))
            y_idx = int(np.clip(scene_pos.y(), 0, self.image_data.shape[0] - 1))
            
            # Convert to voltage coordinates
            if len(self.x_points) > x_idx and len(self.y_points) > y_idx:
                x_voltage = self.x_points[x_idx]
                y_voltage = self.y_points[y_idx]
                
                self.mouse_clicked.emit(x_voltage, y_voltage)

# --------------------- MAIN APPLICATION WINDOW ---------------------
class ConfocalMainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.setup_managers()
        self.setup_hardware()
        self.setup_ui()
        self.setup_connections()
        
        # Initialize notification system
        global notification_system
        notification_system = NotificationSystem(self.statusBar())
    
    def get_native_widget(self, widget):
        """Get the native Qt widget from a magicgui or Qt widget"""
        if hasattr(widget, 'native'):
            return widget.native
        else:
            return widget
        
    def setup_managers(self):
        """Initialize all manager objects"""
        # Initialize managers (same as before)
        self.scan_params_manager = ScanParametersManager()
        self.scan_points_manager = ScanPointsManager(self.scan_params_manager)
        self.zoom_manager = ZoomLevelManager()
        
        # Initialize hardware controllers
        self.galvo_controller = GalvoScannerController()
        self.data_manager = DataManager()
        
        # Global state variables
        self.contrast_limits = (0, 10000)
        self.scan_history = []
        self.image = np.zeros((50, 50), dtype=np.float32)  # Default 50x50
        self.data_path = None
        self.single_axis_widget_ref = None
        self.scan_in_progress = [False]
        self.stop_scan_requested = [False]
        self.zoom_in_progress = False
        
    def setup_hardware(self):
        """Initialize hardware connections"""
        try:
            # Initialize DAQ output task for galvo control
            self.output_task = nidaqmx.Task()
            self.output_task.ao_channels.add_ao_voltage_chan(self.galvo_controller.xin_control)
            self.output_task.ao_channels.add_ao_voltage_chan(self.galvo_controller.yin_control)
            self.output_task.start()
            show_info("✅ DAQ initialized successfully")
        except Exception as e:
            show_info(f"❌ DAQ initialization failed: {str(e)}")
            self.output_task = None
        
        # Initialize TimeTagger
        try:
            self.tagger = createTimeTagger()
            self.tagger.reset()
            show_info("✅ Connected to real TimeTagger device")
        except Exception as e:
            show_info("⚠️ Real TimeTagger not detected, using virtual device")
            try:
                self.tagger = createTimeTaggerVirtual("TimeTagger/time_tags_test.ttbin")
                self.tagger.run()
            except Exception as e2:
                show_info(f"❌ Virtual TimeTagger failed: {str(e2)}")
                self.tagger = None
        
        # Set bin width 
        self.binwidth = BINWIDTH
        n_values = 1
        try:
            if self.tagger is not None:
                self.counter = Counter(self.tagger, [1], self.binwidth, n_values)
            else:
                self.counter = None
                show_info("⚠️ Counter not initialized - TimeTagger unavailable")
        except Exception as e:
            show_info(f"❌ Counter initialization failed: {str(e)}")
            self.counter = None
        
    def setup_ui(self):
        """Setup the main user interface"""
        self.setWindowTitle("NV Scanning Microscopy (PyQtGraph)")
        self.setGeometry(100, 100, 1400, 900)
        
        # Maximize window
        screen = QDesktopWidget().screenGeometry()
        self.resize(screen.width(), screen.height())
        
        # Create central widget with splitter
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Create splitter for resizable panels
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # Left panel for controls
        left_panel = self.create_left_panel()
        splitter.addWidget(left_panel)
        
        # Central panel for image display
        self.image_widget = ScientificImageWidget()
        splitter.addWidget(self.image_widget)
        
        # Right panel for additional controls and plots
        right_panel = self.create_right_panel()
        splitter.addWidget(right_panel)
        
        # Set splitter proportions
        splitter.setSizes([300, 800, 400])
        
        # Create status bar
        self.statusBar().showMessage("Ready")
        
        # Create menu bar (optional)
        self.create_menu_bar()
        
    def create_left_panel(self):
        """Create left control panel"""
        left_widget = QWidget()
        layout = QVBoxLayout()
        
        # Create tab widget for organized controls
        tab_widget = QTabWidget()
        
        # Scan Controls Tab
        scan_tab = QWidget()
        scan_layout = QVBoxLayout()
        
        # Create and add scan control widgets
        try:
            self.new_scan_widget = create_new_scan(self.scan_pattern, self.scan_points_manager, None)
        except Exception as e:
            show_info(f"⚠️ New scan widget failed to create: {str(e)}")
            self.new_scan_widget = QPushButton("New Scan (Error)")
            
        try:
            self.stop_scan_widget = create_stop_scan(self.scan_in_progress, self.stop_scan_requested)
        except Exception as e:
            show_info(f"⚠️ Stop scan widget failed to create: {str(e)}")
            self.stop_scan_widget = QPushButton("Stop Scan (Error)")
            
        try:
            self.save_image_widget = create_save_image(self, self.get_data_path)  # Pass self instead of viewer
        except Exception as e:
            show_info(f"⚠️ Save image widget failed to create: {str(e)}")
            self.save_image_widget = QPushButton("Save Image (Error)")
            
        try:
            self.reset_zoom_widget = create_reset_zoom(
                self.scan_pattern, self.scan_history, self.scan_params_manager, 
                self.scan_points_manager, None, 
                lambda **kwargs: self.scan_params_manager.update_scan_parameters(**kwargs), 
                None, self.zoom_manager
            )
        except Exception as e:
            show_info(f"⚠️ Reset zoom widget failed to create: {str(e)}")
            self.reset_zoom_widget = QPushButton("Reset Zoom (Error)")
        
        # Set fixed sizes and add widgets
        widgets_to_add = [
            (self.new_scan_widget, "New Scan"),
            (self.stop_scan_widget, "Stop Scan"), 
            (self.save_image_widget, "Save Image"),
            (self.reset_zoom_widget, "Reset Zoom")
        ]
        
        for widget, label in widgets_to_add:
            native_widget = self.get_native_widget(widget)
            native_widget.setFixedSize(200, 40)
            scan_layout.addWidget(native_widget)
        scan_layout.addStretch()
        
        scan_tab.setLayout(scan_layout)
        tab_widget.addTab(scan_tab, "Scan Controls")
        
        # Parameters Tab
        param_tab = QWidget()
        param_layout = QVBoxLayout()
        
        self.update_scan_parameters_widget = create_update_scan_parameters(
            self.scan_params_manager, self.scan_points_manager
        )
        native_param_widget = self.get_native_widget(self.update_scan_parameters_widget)
        param_layout.addWidget(native_param_widget)
        param_layout.addStretch()
        
        param_tab.setLayout(param_layout)
        tab_widget.addTab(param_tab, "Parameters")
        
        # System Controls Tab
        system_tab = QWidget()
        system_layout = QVBoxLayout()
        
        self.close_scanner_widget = create_close_scanner(self.output_task)
        self.auto_focus_widget = create_auto_focus(self.counter, self.binwidth, None)
        self.load_scan_widget = create_load_scan(self, self.scan_params_manager, 
                                                self.scan_points_manager, None)
        self.launch_odmr_widget = create_launch_odmr_gui(
            tagger=self.tagger, counter=self.counter, binwidth=self.binwidth
        )
        
        system_widgets = [
            (self.close_scanner_widget, "Close Scanner"),
            (self.auto_focus_widget, "Auto Focus"),
            (self.load_scan_widget, "Load Scan"), 
            (self.launch_odmr_widget, "Launch ODMR")
        ]
        
        for widget, label in system_widgets:
            native_widget = self.get_native_widget(widget)
            native_widget.setFixedSize(200, 40)
            system_layout.addWidget(native_widget)
        
        system_layout.addStretch()
        system_tab.setLayout(system_layout)
        tab_widget.addTab(system_tab, "System")
        
        layout.addWidget(tab_widget)
        left_widget.setLayout(layout)
        
        return left_widget
    
    def create_right_panel(self):
        """Create right panel for plots and additional controls"""
        right_widget = QWidget()
        layout = QVBoxLayout()
        
        # Live signal plot
        self.mpl_widget = live_plot(measure_function=lambda: get_cps(), 
                                   histogram_range=100, dt=0.2)
        layout.addWidget(QLabel("Live Signal"))
        layout.addWidget(self.mpl_widget)
        
        # Camera controls (if needed)
        try:
            camera_widget = create_camera_control_widget(self)
            layout.addWidget(QLabel("Camera Control"))
            native_camera_widget = camera_widget.native if hasattr(camera_widget, 'native') else camera_widget
            layout.addWidget(native_camera_widget)
        except:
            pass  # Camera controls might not be available
        
        # Single axis scan widget
        self.single_axis_scan_widget = SingleAxisScanWidget(
            self.scan_params_manager, None, self.output_task, 
            self.counter, self.binwidth
        )
        self.single_axis_widget_ref = self.single_axis_scan_widget
        
        layout.addWidget(QLabel("Single Axis Scan"))
        layout.addWidget(self.single_axis_scan_widget)
        
        layout.addStretch()
        right_widget.setLayout(layout)
        
        return right_widget
    
    def create_menu_bar(self):
        """Create menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('File')
        
        # View menu
        view_menu = menubar.addMenu('View')
        
        # Add zoom controls
        zoom_action = view_menu.addAction('Add Zoom ROI')
        zoom_action.triggered.connect(self.add_zoom_roi)
        
        clear_zoom_action = view_menu.addAction('Clear Zoom ROI')
        clear_zoom_action.triggered.connect(self.clear_zoom_roi)
    
    def setup_connections(self):
        """Setup signal connections"""
        # Connect image widget signals
        self.image_widget.mouse_clicked.connect(self.on_mouse_click)
        self.image_widget.roi_changed.connect(self.on_roi_changed)
        
    # --------------------- CORE FUNCTIONALITY ---------------------
    
    def scan_pattern(self, x_points, y_points):
        """Perform a raster scan pattern using the galvo mirrors and collect APD counts."""
        if self.output_task is None:
            show_info("❌ Cannot start scan - DAQ not initialized")
            return None, None
            
        self.scan_in_progress[0] = True
        self.stop_scan_requested[0] = False
        
        # Get all scan parameters once at the start
        current_scan_params = self.scan_params_manager.get_params()
        dwell_time = current_scan_params['dwell_time']
        
        try:
            height, width = len(y_points), len(x_points)
            self.image = np.zeros((height, width), dtype=np.float32)
            
            # Update image display
            self.image_widget.set_image_data(self.image, x_points, y_points)
            
            pixel_count = 0  # Counter for pixels scanned
            start_time = time.time()
            
            for y_idx, y in enumerate(y_points):
                for x_idx, x in enumerate(x_points):
                    if self.stop_scan_requested[0]:
                        show_info("🛑 Scan stopped by user")
                        self.output_task.write([0, 0])  # Return to zero position
                        self.scan_in_progress[0] = False
                        return None, None
                        
                    self.output_task.write([x, y])
                    # Use dwell time from parameters, with longer settling time for first pixel in each row
                    if x_idx == 0:
                        time.sleep(max(dwell_time * 2, 0.02))  # Longer settling time for row start
                    else:
                        time.sleep(dwell_time)
                    
                    counts = get_cps()
                    print(f"{counts}")
                    self.image[y_idx, x_idx] = counts
                    
                    # Update display every 10 pixels for performance
                    pixel_count += 1
                    if pixel_count % 10 == 0:
                        self.image_widget.set_image_data(self.image, x_points, y_points)
                        QApplication.processEvents()  # Keep UI responsive
                        
            # Final update to ensure last pixels are displayed
            self.image_widget.set_image_data(self.image, x_points, y_points)
            
            end_time = time.time()
            print(f"Scan time: {end_time - start_time} seconds, {len(x_points)}, {len(y_points)}")
            
            # Save data and create visualizations
            self.save_scan_data(x_points, y_points, current_scan_params)
            
        finally:
            # Return scanner to zero position after scan
            self.output_task.write([0, 0])
            show_info("🎯 Scanner returned to zero position")
            self.scan_in_progress[0] = False
            
        return x_points, y_points
    
    def save_scan_data(self, x_points, y_points, scan_params):
        """Save scan data and create visualizations"""
        # Calculate scale
        scale_um_per_px_x = calculate_scale(x_points[0], x_points[-1], len(x_points))
        scale_um_per_px_y = calculate_scale(y_points[0], y_points[-1], len(y_points))
        
        # Create scan data dictionary
        scan_data = {
            'image': self.image,
            'x_points': x_points,
            'y_points': y_points,
            'scale_x': scale_um_per_px_x,
            'scale_y': scale_um_per_px_y
        }
        
        # Save data
        self.data_path = self.data_manager.save_scan_data(scan_data, scan_params)
        
        # Plot scan results in pdf file
        plot_scan_results(scan_data, self.data_path)
        
        # Save additional formats
        timestamp_str = time.strftime("%Y%m%d-%H%M%S")
        np.savez(self.data_path.replace('.csv', '.npz'), 
                 image=self.image,
                 scale_x=scale_um_per_px_x,
                 scale_y=scale_um_per_px_y,
                 x_range=scan_params['scan_range']['x'],
                 y_range=scan_params['scan_range']['y'],
                 x_resolution=scan_params['resolution']['x'],
                 y_resolution=scan_params['resolution']['y'],
                 dwell_time=scan_params['dwell_time'],
                 x_points=x_points,
                 y_points=y_points,
                 timestamp=timestamp_str)
        
        # Save TIFF with ImageJ-compatible metadata
        save_tiff_with_imagej_metadata(
            image_data=self.image,
            filepath=self.data_path.replace('.csv', '.tiff'),
            x_points=x_points,
            y_points=y_points,
            scan_config=scan_params,
            timestamp=timestamp_str
        )
    
    def get_data_path(self):
        """Helper function to get current data path"""
        return self.data_path
    
    def on_mouse_click(self, x_voltage, y_voltage):
        """Handle mouse click events to move the galvo scanner to the clicked position."""
        if self.output_task is None:
            show_info("❌ Cannot move scanner - DAQ not initialized")
            return
            
        try:
            self.output_task.write([x_voltage, y_voltage])
            show_info(f"Moved scanner to: X={x_voltage:.3f}V, Y={y_voltage:.3f}V")
            
            # Update the single axis scan widget's position tracking
            if self.single_axis_widget_ref is not None:
                self.single_axis_widget_ref.update_current_position(x_voltage, y_voltage)
                
        except Exception as e:
            show_info(f"Error moving scanner: {str(e)}")
    
    def add_zoom_roi(self):
        """Add ROI for zoom selection"""
        if not self.zoom_manager.can_zoom_in():
            show_info(f"⚠️ Max zoom reached ({self.zoom_manager.max_zoom} levels).")
            return
            
        roi = self.image_widget.add_roi()
        show_info("ROI added for zoom selection. Drag to resize, then it will auto-zoom.")
    
    def clear_zoom_roi(self):
        """Clear zoom ROI"""
        self.image_widget.remove_roi()
        show_info("Zoom ROI cleared.")
    
    def on_roi_changed(self, roi):
        """Handle ROI change for zoom functionality"""
        if self.zoom_in_progress:
            return
            
        # Get ROI bounds
        pos = roi.pos()
        size = roi.size()
        
        # Convert to pixel coordinates (simplified for now)
        # This would need proper coordinate transformation based on current scan parameters
        
        # For now, just show the ROI bounds
        show_info(f"ROI updated: pos=({pos[0]:.1f}, {pos[1]:.1f}), size=({size[0]:.1f}, {size[1]:.1f})")
    
    def closeEvent(self, event):
        """Handle application close"""
        try:
            # Set scanner to zero position before closing
            if self.output_task is not None:
                self.output_task.write([0, 0])
                show_info("🎯 Scanner set to zero position")
            
            # Close hardware connections
            if hasattr(self, 'output_task') and self.output_task is not None:
                self.output_task.close()
            if hasattr(self, 'tagger') and self.tagger is not None:
                self.tagger.reset()
                
        except Exception as e:
            show_info(f"❌ Error during app closure: {str(e)}")
        
        event.accept()

# --------------------- SCAN PARAMETERS MANAGER CLASS (UNCHANGED) ---------------------
class ScanParametersManager:
    """Manages scan parameters by getting them from the GUI widget"""
    
    def __init__(self, widget_instance=None):
        self.widget_instance = widget_instance
    
    def set_widget_instance(self, widget_instance):
        """Set the widget instance to get parameters from"""
        self.widget_instance = widget_instance
    
    def get_params(self):
        """Get current scan parameters from the GUI widget"""
        if self.widget_instance and hasattr(self.widget_instance, 'get_parameters'):
            return self.widget_instance.get_parameters()
        else:
            # Fallback default values if widget is not available
            return {
                "scan_range": {"x": [-1.0, 1.0], "y": [-1.0, 1.0]},
                "resolution": {"x": 50, "y": 50},
                "dwell_time": 0.002
            }
    
    def update_scan_parameters(self, x_range=None, y_range=None, x_res=None, y_res=None, dwell_time=None):
        """Update scan parameters in the GUI widget"""
        if self.widget_instance and hasattr(self.widget_instance, 'update_values'):
            # Get current values first
            current_params = self.get_params()
            
            # Update with new values
            new_x_range = x_range if x_range is not None else current_params['scan_range']['x']
            new_y_range = y_range if y_range is not None else current_params['scan_range']['y']
            new_x_res = x_res if x_res is not None else current_params['resolution']['x']
            new_y_res = y_res if y_res is not None else current_params['resolution']['y']
            new_dwell_time = dwell_time if dwell_time is not None else current_params['dwell_time']
            
            self.widget_instance.update_values(new_x_range, new_y_range, new_x_res, new_y_res, new_dwell_time)

# --------------------- SCAN POINTS MANAGER CLASS (UNCHANGED) ---------------------
class ScanPointsManager:
    """Manages scan point generation and updates"""
    
    def __init__(self, scan_params_manager):
        self.scan_params_manager = scan_params_manager
        self.original_x_points = None
        self.original_y_points = None
        # Initialize with default values
        self._initialize_default_points()
    
    def _initialize_default_points(self):
        """Initialize with default values"""
        # Use same defaults as in the widget
        x_range = [-1.0, 1.0]
        y_range = [-1.0, 1.0]
        x_res = 50
        y_res = 50
        
        self.original_x_points = np.linspace(x_range[0], x_range[1], x_res)
        self.original_y_points = np.linspace(y_range[0], y_range[1], y_res)
    
    def _update_points_from_params(self):
        """Update points from current parameters"""
        params = self.scan_params_manager.get_params()
        x_range = params['scan_range']['x']
        y_range = params['scan_range']['y']
        x_res = params['resolution']['x']
        y_res = params['resolution']['y']
        
        self.original_x_points = np.linspace(x_range[0], x_range[1], x_res)
        self.original_y_points = np.linspace(y_range[0], y_range[1], y_res)
    
    def update_points(self, x_range=None, y_range=None, x_res=None, y_res=None):
        if x_range is not None and x_res is not None:
            self.original_x_points = np.linspace(x_range[0], x_range[1], x_res)
        if y_range is not None and y_res is not None:
            self.original_y_points = np.linspace(y_range[0], y_range[1], y_res)
    
    def get_points(self):
        return self.original_x_points, self.original_y_points

# --------------------- ZOOM LEVEL MANAGER CLASS (UNCHANGED) ---------------------
class ZoomLevelManager:
    """Manages zoom level state"""
    
    def __init__(self, max_zoom=MAX_ZOOM_LEVEL):
        self.zoom_level = 0
        self.max_zoom = max_zoom
    
    def get_zoom_level(self):
        return self.zoom_level
    
    def set_zoom_level(self, level):
        self.zoom_level = level
    
    def can_zoom_in(self):
        return self.zoom_level < self.max_zoom

# --------------------- MAIN APPLICATION ENTRY POINT ---------------------
def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("NV Scanning Microscopy")
    app.setApplicationVersion("2.0")
    app.setOrganizationName("NV Center Lab")
    
    # Create and show main window
    main_window = ConfocalMainWindow()
    main_window.show()
    
    print("NV Scanning Microscopy (PyQtGraph) started successfully!")
    print("=" * 60)
    print("Features:")
    print("• High-performance real-time imaging with PyQtGraph")
    print("• Integrated galvo scanner control")
    print("• Live signal plotting")
    print("• Zoom and pan functionality")
    print("• Data saving in multiple formats")
    print("=" * 60)
    
    # Start the application event loop
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 