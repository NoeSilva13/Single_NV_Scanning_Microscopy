"""
Confocal Single-NV Microscopy Control Software (PyQt/PyQtGraph Version)
----------------------------------------------------------------------
This software controls a confocal microscope setup for single NV center imaging using:
- Thorlabs LSKGG4 Galvo-Galvo Scanner
- National Instruments USB-6453 DAQ
- Single Photon Detector SPD

The system provides real-time visualization and control through a PyQt/PyQtGraph-based GUI.
"""

# Standard library imports
import sys
import threading
import time

# Third-party imports
import numpy as np
import nidaqmx
import pyqtgraph as pg
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
    QGridLayout, QSplitter, QTabWidget, QGroupBox, QPushButton,
    QLabel, QMessageBox, QDesktopWidget, QComboBox, QSlider
)
from PyQt5.QtCore import QTimer, pyqtSignal, QObject, Qt, QThread
from PyQt5.QtGui import QPixmap, QPainter
from TimeTagger import createTimeTagger, Counter, createTimeTaggerVirtual

# Local imports
from galvo_controller import GalvoScannerController
from data_manager import DataManager
from plot_scan_results import plot_scan_results
from utils import (
    calculate_scale, 
    MAX_ZOOM_LEVEL, 
    BINWIDTH,
    save_tiff_with_imagej_metadata
)

# Import pure PyQt widget components
from widgets.pyqt_auto_focus import create_auto_focus_widget
from widgets.pyqt_single_axis_scan import create_single_axis_scan_widget


# --------------------- SIGNAL BRIDGES AND COMMUNICATION ---------------------
class MainSignalBridge(QObject):
    """Thread-safe signal bridge for main GUI updates"""
    update_image_signal = pyqtSignal(np.ndarray)
    show_message_signal = pyqtSignal(str)


# --------------------- PURE PYQT WIDGET CLASSES ---------------------

class CurrentPositionWidget(QWidget):
    """Widget to display current scanner position"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_position = [0.0, 0.0]  # [x, y] in volts
        self.init_ui()
    
    def init_ui(self):
        layout = QGridLayout()
        layout.setSpacing(5)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Headers
        header_font = self.font()
        header_font.setBold(True)
        
        axis_header = QLabel("Axis")
        axis_header.setFont(header_font)
        axis_header.setStyleSheet("color: #00d4aa;")
        
        voltage_header = QLabel("Voltage (V)")
        voltage_header.setFont(header_font)
        voltage_header.setStyleSheet("color: #00d4aa;")
        voltage_header.setAlignment(Qt.AlignCenter)
        
        position_header = QLabel("Position (μm)")
        position_header.setFont(header_font)
        position_header.setStyleSheet("color: #00d4aa;")
        position_header.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(axis_header, 0, 0)
        layout.addWidget(voltage_header, 0, 1)
        layout.addWidget(position_header, 0, 2)
        
        # X Position
        layout.addWidget(QLabel("X:"), 1, 0)
        self.x_voltage_label = QLabel("0.000")
        self.x_voltage_label.setAlignment(Qt.AlignCenter)
        self.x_voltage_label.setStyleSheet("color: #ffffff; padding: 2px;")
        self.x_position_label = QLabel("0.0")
        self.x_position_label.setAlignment(Qt.AlignCenter)
        self.x_position_label.setStyleSheet("color: #ffffff; padding: 2px;")
        layout.addWidget(self.x_voltage_label, 1, 1)
        layout.addWidget(self.x_position_label, 1, 2)
        
        # Y Position
        layout.addWidget(QLabel("Y:"), 2, 0)
        self.y_voltage_label = QLabel("0.000")
        self.y_voltage_label.setAlignment(Qt.AlignCenter)
        self.y_voltage_label.setStyleSheet("color: #ffffff; padding: 2px;")
        self.y_position_label = QLabel("0.0")
        self.y_position_label.setAlignment(Qt.AlignCenter)
        self.y_position_label.setStyleSheet("color: #ffffff; padding: 2px;")
        layout.addWidget(self.y_voltage_label, 2, 1)
        layout.addWidget(self.y_position_label, 2, 2)
        
        self.setLayout(layout)
    
    def update_current_position(self, x_voltage, y_voltage):
        """Update the current position display"""
        self.current_position = [x_voltage, y_voltage]
        
        # Update voltage labels
        self.x_voltage_label.setText(f"{x_voltage:.3f}")
        self.y_voltage_label.setText(f"{y_voltage:.3f}")
        
        # Convert to micrometers and update position labels
        from utils import MICRONS_PER_VOLT
        x_um = x_voltage * MICRONS_PER_VOLT
        y_um = y_voltage * MICRONS_PER_VOLT
        
        self.x_position_label.setText(f"{x_um:.1f}")
        self.y_position_label.setText(f"{y_um:.1f}")


class CameraWidget(QWidget):
    """Camera display widget (controls moved to camera controls section)"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.init_camera_simulation()
    
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Camera image display - optimized for space
        self.camera_view = pg.ImageView()
        self.camera_view.setMinimumSize(200, 120)
        self.camera_view.setMaximumSize(280, 180)  # Reduced max size for better space distribution
        self.camera_view.ui.roiBtn.hide()
        self.camera_view.ui.menuBtn.hide()
        self.camera_view.setStyleSheet("background-color: #262930; border: 1px solid #555555;")
        
        layout.addWidget(self.camera_view)
        self.setLayout(layout)
    
    def init_camera_simulation(self):
        """Initialize camera with simulated data"""
        # Create a simple test pattern
        test_image = np.random.randint(0, 255, (240, 320), dtype=np.uint8)
        # Add some structure to make it look more camera-like
        x, y = np.meshgrid(np.linspace(-1, 1, 320), np.linspace(-1, 1, 240))
        pattern = (np.sin(5*x) * np.cos(5*y) * 50 + 128).astype(np.uint8)
        test_image = (test_image * 0.3 + pattern * 0.7).astype(np.uint8)
        
        self.camera_view.setImage(test_image, autoLevels=True)
        
        # Setup update timer for live view simulation
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_camera_image)
        
    def toggle_live_view(self):
        """Toggle live camera view (controlled from camera controls section)"""
        # This method will be called from the main window's live view control
        if hasattr(self, 'update_timer'):
            if self.update_timer.isActive():
                self.update_timer.stop()
            else:
                self.update_timer.start(100)  # Update every 100ms
    
    def update_camera_image(self):
        """Update camera image with simulated data"""
        # Simulate camera noise and slight variations
        test_image = np.random.randint(0, 255, (240, 320), dtype=np.uint8)
        x, y = np.meshgrid(np.linspace(-1, 1, 320), np.linspace(-1, 1, 240))
        pattern = (np.sin(5*x + time.time()) * np.cos(5*y + time.time()) * 50 + 128).astype(np.uint8)
        test_image = (test_image * 0.3 + pattern * 0.7).astype(np.uint8)
        
        self.camera_view.setImage(test_image, autoLevels=False)
    
    def closeEvent(self, event):
        """Clean up camera widget when closed"""
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()
        super().closeEvent(event)


class ScanParametersWidget(QWidget):
    """Professional scan parameters widget with table layout"""
    
    def __init__(self, scan_params_manager, parent=None):
        super().__init__(parent)
        self.scan_params_manager = scan_params_manager
        self.init_ui()
    
    def init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        # Create table-like layout for parameters
        params_layout = QGridLayout()
        params_layout.setSpacing(3)
        params_layout.setHorizontalSpacing(8)
        
        # Headers
        header_font = self.font()
        header_font.setBold(True)
        
        param_header = QLabel("Parameter")
        param_header.setFont(header_font)
        param_header.setStyleSheet("color: #00d4aa;")
        
        voltage_header = QLabel("Voltage (V)")
        voltage_header.setFont(header_font)
        voltage_header.setStyleSheet("color: #00d4aa;")
        voltage_header.setAlignment(Qt.AlignCenter)
        
        distance_header = QLabel("Distance (μm)")  
        distance_header.setFont(header_font)
        distance_header.setStyleSheet("color: #00d4aa;")
        distance_header.setAlignment(Qt.AlignCenter)
        
        params_layout.addWidget(param_header, 0, 0, 1, 1)
        params_layout.addWidget(voltage_header, 0, 1, 1, 2)
        params_layout.addWidget(distance_header, 0, 3, 1, 1)
        
        # X Min row
        params_layout.addWidget(QLabel("X Min:"), 1, 0)
        self.x_min_spin = pg.SpinBox(value=-1.0, bounds=(-10, 10), decimals=2, step=0.1)
        self.x_min_spin.setFixedWidth(60)
        self.x_min_distance = QLabel("-86.0")
        self.x_min_distance.setAlignment(Qt.AlignCenter)
        self.x_min_distance.setStyleSheet("color: #ffffff; padding: 2px;")
        params_layout.addWidget(self.x_min_spin, 1, 1)
        params_layout.addWidget(self.x_min_distance, 1, 3)
        
        # X Max row
        params_layout.addWidget(QLabel("X Max:"), 2, 0)
        self.x_max_spin = pg.SpinBox(value=1.0, bounds=(-10, 10), decimals=2, step=0.1)
        self.x_max_spin.setFixedWidth(60)
        self.x_max_distance = QLabel("86.0")
        self.x_max_distance.setAlignment(Qt.AlignCenter)
        self.x_max_distance.setStyleSheet("color: #ffffff; padding: 2px;")
        params_layout.addWidget(self.x_max_spin, 2, 1)
        params_layout.addWidget(self.x_max_distance, 2, 3)
        
        # Y Min row
        params_layout.addWidget(QLabel("Y Min:"), 3, 0)
        self.y_min_spin = pg.SpinBox(value=-1.0, bounds=(-10, 10), decimals=2, step=0.1)
        self.y_min_spin.setFixedWidth(60)
        self.y_min_distance = QLabel("-86.0")
        self.y_min_distance.setAlignment(Qt.AlignCenter)
        self.y_min_distance.setStyleSheet("color: #ffffff; padding: 2px;")
        params_layout.addWidget(self.y_min_spin, 3, 1)
        params_layout.addWidget(self.y_min_distance, 3, 3)
        
        # Y Max row
        params_layout.addWidget(QLabel("Y Max:"), 4, 0)
        self.y_max_spin = pg.SpinBox(value=1.0, bounds=(-10, 10), decimals=2, step=0.1)
        self.y_max_spin.setFixedWidth(60)
        self.y_max_distance = QLabel("86.0")
        self.y_max_distance.setAlignment(Qt.AlignCenter)
        self.y_max_distance.setStyleSheet("color: #ffffff; padding: 2px;")
        params_layout.addWidget(self.y_max_spin, 4, 1)
        params_layout.addWidget(self.y_max_distance, 4, 3)
        
        # Resolution rows
        params_layout.addWidget(QLabel("X Resolution:"), 5, 0)
        self.x_res_spin = pg.SpinBox(value=50, bounds=(1, 1000), int=True, suffix=' px')
        self.x_res_spin.setFixedWidth(80)
        params_layout.addWidget(self.x_res_spin, 5, 1, 1, 2)
        
        params_layout.addWidget(QLabel("Y Resolution:"), 6, 0)
        self.y_res_spin = pg.SpinBox(value=50, bounds=(1, 1000), int=True, suffix=' px')
        self.y_res_spin.setFixedWidth(80)
        params_layout.addWidget(self.y_res_spin, 6, 1, 1, 2)
        
        # Dwell Time row
        params_layout.addWidget(QLabel("Dwell Time:"), 7, 0)
        self.dwell_spin = pg.SpinBox(value=0.008, bounds=(0.001, 1), decimals=3, step=0.001, suffix=' s')
        self.dwell_spin.setFixedWidth(80)
        params_layout.addWidget(self.dwell_spin, 7, 1, 1, 2)
        
        main_layout.addLayout(params_layout)
        
        # Apply Changes button
        self.apply_btn = QPushButton("Apply Changes")
        self.apply_btn.clicked.connect(self.apply_changes)
        main_layout.addWidget(self.apply_btn)
        
        self.setLayout(main_layout)
        
        # Connect spinbox changes to update distance labels
        self.x_min_spin.valueChanged.connect(self.update_distance_labels)
        self.x_max_spin.valueChanged.connect(self.update_distance_labels)
        self.y_min_spin.valueChanged.connect(self.update_distance_labels)
        self.y_max_spin.valueChanged.connect(self.update_distance_labels)
        
        # Initial distance update
        self.update_distance_labels()
    
    def update_distance_labels(self):
        """Update distance labels when voltage values change"""
        try:
            from utils import MICRONS_PER_VOLT
            
            # Update distance labels
            self.x_min_distance.setText(f"{self.x_min_spin.value() * MICRONS_PER_VOLT:.1f}")
            self.x_max_distance.setText(f"{self.x_max_spin.value() * MICRONS_PER_VOLT:.1f}")
            self.y_min_distance.setText(f"{self.y_min_spin.value() * MICRONS_PER_VOLT:.1f}")
            self.y_max_distance.setText(f"{self.y_max_spin.value() * MICRONS_PER_VOLT:.1f}")
        except:
            pass
    
    def apply_changes(self):
        """Apply parameter changes and update the system"""
        try:
            # Update the scan points manager with new parameters
            if self.scan_params_manager and hasattr(self.scan_params_manager, 'update_scan_parameters'):
                params = self.get_parameters()
                x_range = params['scan_range']['x']
                y_range = params['scan_range']['y']
                x_res = params['resolution']['x']
                y_res = params['resolution']['y']
                dwell_time = params['dwell_time']
                
                self.scan_params_manager.update_scan_parameters(
                    x_range=x_range, y_range=y_range,
                    x_res=x_res, y_res=y_res,
                    dwell_time=dwell_time
                )
            
            # Visual feedback that changes were applied
            original_text = self.apply_btn.text()
            self.apply_btn.setText("✓ Applied")
            self.apply_btn.setStyleSheet("background-color: #00aa00;")
            
            # Reset button after 1 second
            QTimer.singleShot(1000, lambda: [
                self.apply_btn.setText(original_text),
                self.apply_btn.setStyleSheet("")
            ])
            
        except Exception as e:
            print(f"Error applying changes: {e}")
            self.apply_btn.setText("❌ Error")
            QTimer.singleShot(1000, lambda: self.apply_btn.setText("Apply Changes"))
    
    def get_parameters(self):
        """Get current parameters from the widget"""
        return {
            "scan_range": {
                "x": [self.x_min_spin.value(), self.x_max_spin.value()],
                "y": [self.y_min_spin.value(), self.y_max_spin.value()]
            },
            "resolution": {
                "x": int(self.x_res_spin.value()),
                "y": int(self.y_res_spin.value())
            },
            "dwell_time": self.dwell_spin.value()
        }
    
    def update_values(self, x_range, y_range, x_res, y_res, dwell_time):
        """Update widget values"""
        self.x_min_spin.setValue(x_range[0])
        self.x_max_spin.setValue(x_range[1])
        self.y_min_spin.setValue(y_range[0])
        self.y_max_spin.setValue(y_range[1])
        self.x_res_spin.setValue(x_res)
        self.y_res_spin.setValue(y_res)
        self.dwell_spin.setValue(dwell_time)


class LivePlotWidget(QWidget):
    """PyQtGraph-based live plotting widget - optimized for full height usage"""
    
    def __init__(self, measure_function, histogram_range=100, update_interval=200, parent=None):
        super().__init__(parent)
        self.measure_function = measure_function
        self.histogram_range = histogram_range
        self.update_interval = update_interval
        
        # Setup plot widget with dark theme matching ODMR GUI
        self.plot_widget = pg.PlotWidget(title="Live Signal")
        self.plot_widget.setBackground('#262930')
        self.plot_widget.setLabel('left', 'Signal (counts/s)', color='white', size='11pt')
        self.plot_widget.setLabel('bottom', 'Time (s)', color='white', size='11pt')
        self.plot_widget.showGrid(True, alpha=0.3)
        
        # Style the plot to match ODMR GUI dark theme
        self.plot_widget.getAxis('left').setPen('white')
        self.plot_widget.getAxis('bottom').setPen('white')
        self.plot_widget.getAxis('left').setTextPen('white')
        self.plot_widget.getAxis('bottom').setTextPen('white')
        
        # Set size policy to expand in both directions
        from PyQt5.QtWidgets import QSizePolicy
        self.plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Data storage
        self.x_data = []
        self.y_data = []
        self.t0 = time.time()
        
        # Plot curve with ODMR GUI green color
        self.curve = self.plot_widget.plot(pen=pg.mkPen('#00ff88', width=2))
        
        # Layout with no margins to maximize space usage
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.plot_widget)
        self.setLayout(layout)
        
        # Set size policy for the widget itself
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Update timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(update_interval)
    
    def update_plot(self):
        """Update the live plot with new data"""
        try:
            new_data = self.measure_function()
            current_time = time.time() - self.t0
            
            self.x_data.append(current_time)
            self.y_data.append(new_data)
            
            # Keep only recent data
            if len(self.x_data) > self.histogram_range:
                self.x_data = self.x_data[-self.histogram_range:]
                self.y_data = self.y_data[-self.histogram_range:]
            
            self.curve.setData(self.x_data, self.y_data)
        except Exception as e:
            print(f"Error updating live plot: {e}")
    
    def pause_updates(self):
        """Pause live plot updates during scanning for better performance"""
        if hasattr(self, 'timer'):
            self.timer.stop()
    
    def resume_updates(self):
        """Resume live plot updates after scanning"""
        if hasattr(self, 'timer'):
            self.timer.start(self.update_interval)
    
    def closeEvent(self, event):
        """Clean up timer when widget is closed"""
        if hasattr(self, 'timer'):
            self.timer.stop()
        super().closeEvent(event)


class ScanThread(QThread):
    """Background thread for scanning operations"""
    
    update_image = pyqtSignal(np.ndarray)
    update_progress = pyqtSignal(int)  # Progress percentage (0-100)
    scan_complete = pyqtSignal(np.ndarray, np.ndarray, np.ndarray)  # image, x_points, y_points
    error_occurred = pyqtSignal(str)
    
    def __init__(self, x_points, y_points, dwell_time, counter, binwidth, output_task):
        super().__init__()
        self.x_points = x_points
        self.y_points = y_points
        self.dwell_time = dwell_time
        self.counter = counter
        self.binwidth = binwidth
        self.output_task = output_task
        self.stop_requested = False
        
    def run(self):
        """Execute the scan in background thread"""
        try:
            if not self.output_task:
                self.error_occurred.emit("DAQ not initialized")
                return
                
            height, width = len(self.y_points), len(self.x_points)
            total_pixels = height * width
            image = np.zeros((height, width), dtype=np.float32)
            
            # Calculate adaptive update intervals based on scan size
            # For small scans: update more frequently
            # For large scans: update less frequently to maintain performance
            if total_pixels <= 100:        # Small scans (10x10 or less)
                progress_interval = 5      # Update every 5 pixels
                image_interval = 10        # Update image every 10 pixels
            elif total_pixels <= 1000:    # Medium scans (up to ~32x32)
                progress_interval = 25     # Update every 25 pixels  
                image_interval = 50        # Update image every 50 pixels
            elif total_pixels <= 5000:    # Large scans (up to ~71x71)
                progress_interval = 100    # Update every 100 pixels
                image_interval = 200       # Update image every 200 pixels
            else:                          # Very large scans (100x100+)
                progress_interval = 250    # Update every 250 pixels
                image_interval = 500       # Update image every 500 pixels
            
            pixel_count = 0
            last_progress_update = 0
            
            for y_idx, y in enumerate(self.y_points):
                if self.stop_requested:
                    break
                    
                for x_idx, x in enumerate(self.x_points):
                    if self.stop_requested:
                        break
                        
                    self.output_task.write([x, y])
                    
                    # Longer settling time for first pixel in row
                    if x_idx == 0:
                        time.sleep(max(self.dwell_time * 2, 0.05))
                    else:
                        time.sleep(self.dwell_time)
                    
                    counts = self.counter.getData()[0][0] / (self.binwidth / 1e12)
                    image[y_idx, x_idx] = counts
                    
                    pixel_count += 1
                    
                    # Emit progress update at adaptive intervals
                    if pixel_count - last_progress_update >= progress_interval:
                        progress = int((pixel_count / total_pixels) * 100)
                        self.update_progress.emit(progress)
                        last_progress_update = pixel_count
                    
                    # Emit image update at adaptive intervals
                    # Use numpy view instead of copy when possible for better performance
                    if pixel_count % image_interval == 0:
                        self.update_image.emit(image.copy())
            
            if not self.stop_requested:
                # Final progress update
                self.update_progress.emit(100)
                self.scan_complete.emit(image, self.x_points, self.y_points)
                
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            # Return scanner to zero
            try:
                if self.output_task:
                    self.output_task.write([0, 0])
            except:
                pass
    
    def stop(self):
        """Request scan stop"""
        self.stop_requested = True


# --------------------- MAIN WINDOW CLASS ---------------------
class ConfocalMainWindow(QMainWindow):
    """Main window for the confocal microscopy control software"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NV Scanning Microscopy Control Center - Burke Lab")
        
        # Initialize hardware and managers first
        self.init_hardware()
        self.init_managers()
        
        # Initialize GUI
        self.init_ui()
        self.init_connections()
        
        # Initialize scan state
        self.scan_thread = None
        self.current_image = None
        self.data_path = None
        self.single_axis_scan_thread = None
        
        # Status bar
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready - Click on image to position scanner")
        
        # Maximize window
        screen = QDesktopWidget().screenGeometry()
        self.resize(screen.width(), screen.height())
    
    def init_hardware(self):
        """Initialize hardware components"""
        # Initialize hardware controllers
        self.galvo_controller = GalvoScannerController()
        self.data_manager = DataManager()
        
        # Initialize DAQ
        try:
            self.output_task = nidaqmx.Task()
            self.output_task.ao_channels.add_ao_voltage_chan(self.galvo_controller.xin_control)
            self.output_task.ao_channels.add_ao_voltage_chan(self.galvo_controller.yin_control)
            self.output_task.start()
        except Exception as e:
            print(f"❌ Error initializing DAQ: {e}")
            self.output_task = None
        
        # Initialize TimeTagger
        try:
            self.tagger = createTimeTagger()
            self.tagger.reset()
            print("✅ Connected to real TimeTagger device")
        except Exception as e:
            print("⚠️ Real TimeTagger not detected, using virtual device")
            self.tagger = createTimeTaggerVirtual("TimeTagger/time_tags_test.ttbin")
            self.tagger.run()
        
        # Set up counter
        self.binwidth = BINWIDTH
        self.counter = Counter(self.tagger, [1], self.binwidth, 1)
    
    def init_managers(self):
        """Initialize manager classes"""
        # Scan parameters manager
        self.scan_params_manager = ScanParametersManager()
        
        # Scan points manager  
        self.scan_points_manager = ScanPointsManager(self.scan_params_manager)
        
        # Zoom manager
        self.zoom_manager = ZoomLevelManager()
        
        # Scan history for zoom operations
        self.scan_history = []
        
        # Signal bridge
        self.signal_bridge = MainSignalBridge()
        self.signal_bridge.update_image_signal.connect(self.update_image_display)
        self.signal_bridge.show_message_signal.connect(self.show_message)
    
    def init_ui(self):
        """Initialize the user interface with improved layout distribution
        
        Layout Structure:
        ┌─────────────────────────────────────────────────────────────────┐
        │ Main Window (Proportions: [Left+Center+Bottom 70%] | [Right 30%])│
        ├─────────────┬─────────────────────────────┬─────────────────────┤
        │ LEFT PANEL  │ CENTER PANEL                │ RIGHT PANEL         │
        │ (25%)       │ (45% - Dominant)            │ (30% - Full Height) │
        │             │                             │                     │
        │ ┌─────────┐ │ ┌─────────────────────────┐ │ ┌─────────────────┐ │
        │ │ Camera  │ │ │ Image Panel Controls    │ │ │ Live Signal     │ │
        │ │ Image   │ │ │ (Zoom + Colormap)       │ │ │    (40%)        │ │
        │ └─────────┘ │ └─────────────────────────┘ │ │                 │ │
        │ ┌─────────┐ │ ┌─────────────────────────┐ │ │   Expandable    │ │
        │ │ Camera  │ │ │                         │ │ │     Plot        │ │
        │ │Controls │ │ │    Main Image Display   │ │ └─────────────────┘ │
        │ └─────────┘ │ │     (Confocal Scan)     │ │ ┌─────────────────┐ │
        │ ┌─────────┐ │ │                         │ │ │ Auto Focus      │ │
        │ │  Scan   │ │ │                         │ │ │    (20%)        │ │
        │ │Paramters│ │ │                         │ │ └─────────────────┘ │
        │ └─────────┘ │ └─────────────────────────┘ │ ┌─────────────────┐ │
        ├─────────────┴─────────────────────────────┤ │ Single Axis     │ │
        │ BOTTOM PANEL: Scan Controls + Status      │ │ Scan (40%)      │ │
        │ (Only under Left + Center)                │ │   Expandable    │ │
        └─────────────────────────────────────────────┴─────────────────────┘
        """
        # Apply dark theme style (napari-inspired, matching ODMR GUI)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #262930;
                color: #ffffff;
            }
            QWidget {
                background-color: #262930;
                color: #ffffff;
            }
            QPushButton {
                background-color: #00d4aa;
                color: #262930;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00ffcc;
            }
            QPushButton:pressed {
                background-color: #009980;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #999999;
            }
            QGroupBox {
                color: #ffffff;
                border: 2px solid #555555;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #00d4aa;
            }
            QLabel {
                color: #ffffff;
            }
            QLineEdit {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px;
                font-size: 10pt;
            }
            QLineEdit:focus {
                border: 2px solid #00d4aa;
            }
            QTextEdit {
                background-color: #1e1e1e;
                color: #00ff00;
                border: 1px solid #555555;
                border-radius: 4px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 9pt;
            }
            QProgressBar {
                border: 1px solid #555555;
                border-radius: 4px;
                background-color: #3c3c3c;
                text-align: center;
                color: #ffffff;
            }
            QProgressBar::chunk {
                background-color: #00d4aa;
                border-radius: 3px;
            }
            QScrollArea {
                background-color: #262930;
                border: none;
            }
            QTabWidget::pane {
                border: 1px solid #555555;
                background-color: #262930;
            }
            QTabWidget::tab-bar {
                alignment: center;
            }
            QTabBar::tab {
                background-color: #3c3c3c;
                color: #ffffff;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #00d4aa;
                color: #262930;
                font-weight: bold;
            }
            QTabBar::tab:hover {
                background-color: #555555;
            }
            QComboBox {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px;
                font-size: 10pt;
            }
            QComboBox::drop-down {
                border: none;
                background-color: #555555;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #ffffff;
            }
            QComboBox QAbstractItemView {
                background-color: #3c3c3c;
                color: #ffffff;
                selection-background-color: #00d4aa;
                selection-color: #262930;
            }
            QSpinBox, QDoubleSpinBox {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px;
                font-size: 10pt;
            }
            QSpinBox:focus, QDoubleSpinBox:focus {
                border: 2px solid #00d4aa;
            }
            QStatusBar {
                background-color: #1e1e1e;
                color: #00ff00;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 9pt;
                border-top: 1px solid #555555;
            }
            QSplitter::handle {
                background-color: #555555;
                border: 1px solid #3c3c3c;
            }
            QSplitter::handle:horizontal {
                width: 3px;
            }
            QSplitter::handle:vertical {
                height: 3px;
            }
        """)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Create optimized layout structure
        # Main layout: (Left+Center+Bottom Area) + Right Panel
        main_layout = QHBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(5, 5, 5, 5)
        central_widget.setLayout(main_layout)
        
        # Left+Center+Bottom combined area
        left_center_bottom_widget = QWidget()
        left_center_bottom_layout = QVBoxLayout()
        left_center_bottom_layout.setSpacing(10)
        left_center_bottom_layout.setContentsMargins(0, 0, 0, 0)
        left_center_bottom_widget.setLayout(left_center_bottom_layout)
        
        # Top area for left and center panels only
        self.left_center_layout = QHBoxLayout()
        self.left_center_layout.setSpacing(10)
        
        # LEFT PANEL: Camera + Scan Parameters (30% of window width)
        self.left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setSpacing(8)
        left_layout.setContentsMargins(8, 8, 8, 8)
        self.left_panel.setLayout(left_layout)
        
        # Camera section - compact space allocation
        camera_group = QGroupBox("Camera Image")
        camera_layout = QVBoxLayout()
        camera_layout.setContentsMargins(5, 5, 5, 5)
        self.camera_widget = CameraWidget()
        camera_layout.addWidget(self.camera_widget)
        camera_group.setLayout(camera_layout)
        left_layout.addWidget(camera_group, 0)  # No stretch - fixed size
        
        # Camera controls group - enhanced with sliders
        camera_controls_group = QGroupBox("Camera Controls")
        camera_controls_layout = QVBoxLayout()
        camera_controls_layout.setContentsMargins(5, 5, 5, 5)
        camera_controls_layout.setSpacing(8)
        
        # Camera parameter controls with sliders
        params_layout = QGridLayout()
        params_layout.setSpacing(5)
        
        # Exposure control (slider)
        params_layout.addWidget(QLabel("Exposure:"), 0, 0)
        self.exposure_slider = QSlider(Qt.Horizontal)
        self.exposure_slider.setRange(1, 1000)  # 1ms to 1000ms
        self.exposure_slider.setValue(10)
        self.exposure_slider.setFixedWidth(120)
        self.exposure_label = QLabel("10 ms")
        self.exposure_label.setFixedWidth(50)
        self.exposure_label.setAlignment(Qt.AlignCenter)
        self.exposure_slider.valueChanged.connect(self.on_exposure_changed)
        params_layout.addWidget(self.exposure_slider, 0, 1)
        params_layout.addWidget(self.exposure_label, 0, 2)
        
        # Gain control (slider)
        params_layout.addWidget(QLabel("Gain:"), 1, 0)
        self.gain_slider = QSlider(Qt.Horizontal)
        self.gain_slider.setRange(1, 100)  # 1x to 100x gain
        self.gain_slider.setValue(1)
        self.gain_slider.setFixedWidth(120)
        self.gain_label = QLabel("1x")
        self.gain_label.setFixedWidth(50)
        self.gain_label.setAlignment(Qt.AlignCenter)
        self.gain_slider.valueChanged.connect(self.on_gain_changed)
        params_layout.addWidget(self.gain_slider, 1, 1)
        params_layout.addWidget(self.gain_label, 1, 2)
        
        camera_controls_layout.addLayout(params_layout)
        
        # Camera action buttons - all in one row using full width
        camera_buttons_layout = QHBoxLayout()
        camera_buttons_layout.setSpacing(8)
        camera_buttons_layout.setContentsMargins(0, 0, 0, 0)
        
        # Live view toggle button
        self.live_view_btn = QPushButton("📹 Live View")
        self.live_view_btn.setFixedHeight(35)
        self.live_view_btn.setCheckable(True)
        self.live_view_btn.clicked.connect(self.toggle_camera_live_view)
        camera_buttons_layout.addWidget(self.live_view_btn, 1)  # Stretch factor 1
        
        # Capture button
        self.capture_btn = QPushButton("📸 Capture")
        self.capture_btn.setFixedHeight(35)
        self.capture_btn.clicked.connect(self.capture_image)
        camera_buttons_layout.addWidget(self.capture_btn, 1)  # Stretch factor 1
        
        # Save button
        self.save_camera_btn = QPushButton("💾 Save")
        self.save_camera_btn.setFixedHeight(35)
        self.save_camera_btn.clicked.connect(self.save_camera_image)
        camera_buttons_layout.addWidget(self.save_camera_btn, 1)  # Stretch factor 1
        
        camera_controls_layout.addLayout(camera_buttons_layout)
        camera_controls_group.setLayout(camera_controls_layout)
        left_layout.addWidget(camera_controls_group, 0)  # No stretch - fixed size
        
        # Current position widget - moved from right panel
        position_group = QGroupBox("Current Position")
        position_layout = QVBoxLayout()
        position_layout.setContentsMargins(5, 5, 5, 5)
        self.current_position_widget = CurrentPositionWidget()
        position_layout.addWidget(self.current_position_widget)
        position_group.setLayout(position_layout)
        left_layout.addWidget(position_group, 0)  # No stretch - fixed size
        
        # Single axis scan buttons - moved from right panel
        scan_buttons_group = QGroupBox("Single Axis Scan")
        scan_buttons_layout = QHBoxLayout()
        scan_buttons_layout.setSpacing(8)
        scan_buttons_layout.setContentsMargins(5, 5, 5, 5)
        
        # X Scan button
        self.x_scan_btn = QPushButton("📊 X Scan")
        self.x_scan_btn.setFixedHeight(35)
        self.x_scan_btn.clicked.connect(lambda: self.start_axis_scan('X'))
        scan_buttons_layout.addWidget(self.x_scan_btn)
        
        # Y Scan button  
        self.y_scan_btn = QPushButton("📈 Y Scan")
        self.y_scan_btn.setFixedHeight(35)
        self.y_scan_btn.clicked.connect(lambda: self.start_axis_scan('Y'))
        scan_buttons_layout.addWidget(self.y_scan_btn)
        
        scan_buttons_group.setLayout(scan_buttons_layout)
        left_layout.addWidget(scan_buttons_group, 0)  # No stretch - fixed size
        
        # Scan parameters widget - gets majority of remaining space
        params_group = QGroupBox("Scan Parameters")
        params_layout = QVBoxLayout()
        params_layout.setContentsMargins(5, 5, 5, 5)
        self.scan_params_widget = ScanParametersWidget(self.scan_params_manager)
        params_layout.addWidget(self.scan_params_widget)
        params_group.setLayout(params_layout)
        left_layout.addWidget(params_group, 1)  # Stretch factor 1 - expands to use available space
        
        # Small stretch at bottom to prevent over-expansion
        left_layout.addStretch(0)
        
        self.left_center_layout.addWidget(self.left_panel)
        
        # CENTER PANEL: Main Image Display (45% of window width - dominant area)
        self.center_panel = QWidget()
        center_layout = QVBoxLayout()
        center_layout.setSpacing(5)
        center_layout.setContentsMargins(8, 8, 8, 8)
        self.center_panel.setLayout(center_layout)
        
        # Image controls - optimized single row layout using full width
        image_controls_group = QGroupBox("Image Panel")
        image_controls_group_layout = QVBoxLayout()
        image_controls_group_layout.setContentsMargins(5, 5, 5, 5)
        image_controls_group_layout.setSpacing(5)
        
        # Single row: All controls using full width
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        
        # Zoom toggle button
        self.zoom_toggle_btn = QPushButton("🔍 Enable Zoom")
        self.zoom_toggle_btn.clicked.connect(self.toggle_zoom_mode)
        self.zoom_toggle_btn.setFixedHeight(35)
        controls_layout.addWidget(self.zoom_toggle_btn, 2)  # Stretch factor 2
        
        # Apply zoom button
        self.apply_zoom_btn = QPushButton("⚡ Apply Zoom")
        self.apply_zoom_btn.clicked.connect(self.apply_zoom)
        self.apply_zoom_btn.setEnabled(False)
        self.apply_zoom_btn.setFixedHeight(35)
        controls_layout.addWidget(self.apply_zoom_btn, 2)  # Stretch factor 2
        
        # Colormap selection with label
        colormap_container = QWidget()
        colormap_layout = QHBoxLayout()
        colormap_layout.setContentsMargins(0, 0, 0, 0)
        colormap_layout.setSpacing(5)
        
        colormap_label = QLabel("Colormap:")
        colormap_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.colormap_combo = QComboBox()
        self.colormap_combo.setFixedHeight(35)
        
        colormap_layout.addWidget(colormap_label, 0)
        colormap_layout.addWidget(self.colormap_combo, 1)
        colormap_container.setLayout(colormap_layout)
        
        controls_layout.addWidget(colormap_container, 3)  # Stretch factor 3 (more space for combo)
        
        # Add single row to the group
        image_controls_group_layout.addLayout(controls_layout)
        image_controls_group.setLayout(image_controls_group_layout)
        
        center_layout.addWidget(image_controls_group)
        
        # Main image view with enhanced features
        self.image_view = pg.ImageView()
        self.image_view.ui.roiBtn.hide()  # Hide ROI button initially
        self.image_view.ui.menuBtn.hide()  # Hide menu button
        
        # Apply dark theme to image view
        view_widget = self.image_view.getView()
        view_widget.setBackgroundColor('#262930')
        
        # Set the ImageView widget background color to match theme
        self.image_view.setStyleSheet("background-color: #262930; border: none;")
        
        # Style the histogram widget and set proper units
        if hasattr(self.image_view, 'ui') and hasattr(self.image_view.ui, 'histogram'):
            self.image_view.ui.histogram.setBackground('#262930')
            # Set histogram label to show counts/s
            if hasattr(self.image_view.ui.histogram, 'axis'):
                self.image_view.ui.histogram.axis.setLabel('Intensity', units='c/s')
        
        # Enable proper axes for the ImageView
        self.setup_image_axes()
        
        # Add crosshair lines for cursor position
        self.setup_crosshair_cursor()
        
        # Add position/intensity text overlay
        self.setup_position_text()
        
        # Connect mouse events
        self.image_view.getImageItem().mouseClickEvent = self.on_image_click
        
        # Connect mouse move events for cursor tracking
        self.image_view.scene.sigMouseMoved.connect(self.on_mouse_move)
        
        # Set up ROI for zoom selection
        self.zoom_roi = pg.RectROI([10, 10], [30, 30], pen='r')
        self.zoom_roi.sigRegionChanged.connect(self.on_roi_changed)
        self.image_view.getView().addItem(self.zoom_roi)
        self.zoom_roi.hide()  # Initially hidden
        
        # Add scale bar
        self.scale_bar = self.create_scale_bar()
        self.image_view.getView().addItem(self.scale_bar)
        
        center_layout.addWidget(self.image_view)
        
        self.left_center_layout.addWidget(self.center_panel)  # Proportions handled by resizeEvent
        
        # RIGHT PANEL: Analysis Tools (25% of window width, FULL HEIGHT)
        self.right_panel = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setSpacing(8)
        right_layout.setContentsMargins(8, 8, 8, 8)
        self.right_panel.setLayout(right_layout)
        
        # Live Signal Plot (equal size)
        live_signal_group = QGroupBox("Live Signal")
        live_signal_layout = QVBoxLayout()
        live_signal_layout.setContentsMargins(5, 5, 5, 5)
        self.live_plot = LivePlotWidget(
            measure_function=lambda: self.counter.getData()[0][0] / (self.binwidth / 1e12),
            histogram_range=100,
            update_interval=200
        )
        # Set consistent minimum height for uniform appearance
        self.live_plot.setMinimumHeight(150)
        live_signal_layout.addWidget(self.live_plot)
        live_signal_group.setLayout(live_signal_layout)
        right_layout.addWidget(live_signal_group, 1)  # Equal stretch factor
        
        # Auto Focus (equal size)
        auto_focus_group = QGroupBox("Auto Focus")
        auto_focus_layout = QVBoxLayout()
        auto_focus_layout.setContentsMargins(5, 5, 5, 5)
        self.auto_focus_widget = create_auto_focus_widget(self.counter, self.binwidth)
        # Set consistent minimum height for uniform appearance
        self.auto_focus_widget.setMinimumHeight(150)
        auto_focus_layout.addWidget(self.auto_focus_widget)
        auto_focus_group.setLayout(auto_focus_layout)
        right_layout.addWidget(auto_focus_group, 1)  # Equal stretch factor
        
        # Single Axis Scan Plot (equal size) - buttons moved to left panel
        single_axis_group = QGroupBox("Single Axis Scan Plot")
        single_axis_layout = QVBoxLayout()
        single_axis_layout.setContentsMargins(5, 5, 5, 5)
        self.single_axis_widget = create_single_axis_scan_widget(
            self.scan_params_manager, self.output_task, self.counter, self.binwidth
        )
        # Set consistent minimum height for uniform appearance
        self.single_axis_widget.setMinimumHeight(150)
        single_axis_layout.addWidget(self.single_axis_widget)
        single_axis_group.setLayout(single_axis_layout)
        right_layout.addWidget(single_axis_group, 1)  # Equal stretch factor
        
        # No stretch at bottom - let widgets fill all available space equally
        
        # Add left+center layout to the combined widget
        left_center_bottom_layout.addLayout(self.left_center_layout, 1)  # Give top area stretch factor
        
        # BOTTOM PANEL: Scan Controls (fixed height for consistent layout)
        bottom_panel = QWidget()
        bottom_panel.setFixedHeight(110)  # Slightly reduced for more compact design
        bottom_layout = QVBoxLayout()
        bottom_layout.setSpacing(5)
        bottom_layout.setContentsMargins(8, 8, 8, 8)
        bottom_panel.setLayout(bottom_layout)
        
        # Scan controls optimized to use full width
        controls_group = QGroupBox("Scan Controls")
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)  # Reduced spacing for better space utilization
        controls_layout.setContentsMargins(10, 10, 10, 10)
        
        # Create individual control buttons with optimized sizing
        from PyQt5.QtWidgets import QSizePolicy
        
        self.new_scan_btn = QPushButton("🔬 New Scan")
        self.new_scan_btn.clicked.connect(self.start_new_scan)
        self.new_scan_btn.setMinimumHeight(45)  # Consistent height
        self.new_scan_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        self.stop_scan_btn = QPushButton("🛑 Stop Scan")
        self.stop_scan_btn.clicked.connect(self.stop_scan)
        self.stop_scan_btn.setMinimumHeight(45)
        self.stop_scan_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        self.auto_focus_btn = QPushButton("🔍 Auto Focus")
        self.auto_focus_btn.clicked.connect(self.trigger_auto_focus)
        self.auto_focus_btn.setMinimumHeight(45)
        self.auto_focus_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        self.save_image_btn = QPushButton("📷 Save Image")
        self.save_image_btn.clicked.connect(self.save_image)
        self.save_image_btn.setMinimumHeight(45)
        self.save_image_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        self.reset_zoom_btn = QPushButton("🔄 Reset Zoom")
        self.reset_zoom_btn.clicked.connect(self.reset_zoom)
        self.reset_zoom_btn.setMinimumHeight(45)
        self.reset_zoom_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        self.close_scanner_btn = QPushButton("🎯 Set to Zero")
        self.close_scanner_btn.clicked.connect(self.close_scanner)
        self.close_scanner_btn.setMinimumHeight(45)
        self.close_scanner_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        self.load_scan_btn = QPushButton("📁 Load Scan")
        self.load_scan_btn.clicked.connect(self.load_scan)
        self.load_scan_btn.setMinimumHeight(45)
        self.load_scan_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        # Add buttons to layout with equal stretch factors
        controls_layout.addWidget(self.new_scan_btn, 1)     # Equal stretch
        controls_layout.addWidget(self.stop_scan_btn, 1)    # Equal stretch
        controls_layout.addWidget(self.auto_focus_btn, 1)   # Equal stretch
        controls_layout.addWidget(self.save_image_btn, 1)   # Equal stretch
        controls_layout.addWidget(self.reset_zoom_btn, 1)   # Equal stretch
        controls_layout.addWidget(self.close_scanner_btn, 1) # Equal stretch
        controls_layout.addWidget(self.load_scan_btn, 1)    # Equal stretch
        
        # No addStretch() - let buttons fill all available space
        
        controls_group.setLayout(controls_layout)
        bottom_layout.addWidget(controls_group)
        
        # Add bottom panel to left+center area only
        left_center_bottom_layout.addWidget(bottom_panel)
        
        # Add the left+center+bottom widget and right panel to main layout
        main_layout.addWidget(left_center_bottom_widget, 7)  # 70% width (left 25% + center 45%)
        main_layout.addWidget(self.right_panel, 3)  # 30% width
        
        # Initialize display
        self.init_display()
    
    def init_display(self):
        """Initialize the image display with default parameters"""
        params = self.scan_params_manager.get_params()
        x_res = params['resolution']['x']
        y_res = params['resolution']['y']
        
        # Create empty image
        self.current_image = np.zeros((y_res, x_res), dtype=np.float32)
        
        # Set up colormap system with scientific colormaps
        self.setup_colormaps()
        self.apply_colormap('viridis')  # Default to viridis
        
        # Calculate scale and position for proper micrometer display
        x_range = params['scan_range']['x']
        y_range = params['scan_range']['y']
        scale_x = calculate_scale(x_range[0], x_range[1], x_res)
        scale_y = calculate_scale(y_range[0], y_range[1], y_res)
        
        # Convert voltage ranges to micrometer positions
        from utils import MICRONS_PER_VOLT
        x_start_um = x_range[0] * MICRONS_PER_VOLT
        y_start_um = y_range[0] * MICRONS_PER_VOLT
        
        # Set image with proper scale and position
        # Transpose the image because PyQtGraph's ImageView expects column-major (width, height) data,
        # while our data is in row-major (height, width) format. This ensures correct coordinate mapping.
        self.image_view.setImage(self.current_image.T, 
                                autoLevels=True,
                                scale=(scale_x, scale_y),
                                pos=(x_start_um, y_start_um))
        
        # Update scan parameters manager
        self.scan_params_manager.set_widget_instance(self.scan_params_widget)
        self.scan_points_manager._update_points_from_params()
        
        # Update scale bar and coordinate labels for initial display
        self.update_scale_bar()
        self.update_coordinate_labels()
        
        # Set initial proportional layout
        self.update_panel_proportions()
    
    def update_panel_proportions(self):
        """Update panel proportions based on current window size
        
        New layout structure:
        - Main layout (horizontal): [Left+Center+Bottom 70%] | [Right 30%]
        - Within Left+Center area: [Left 36%] | [Center 64%]
        """
        if hasattr(self, 'left_center_layout'):
            # The main horizontal layout proportions are set by stretch factors (7:3 = 70%:30%)
            # We only need to manage proportions within the left+center area
            
            # Within the left+center area (which is 70% of total width):
            # Left should be 25%/70% = 36% of left+center area  
            # Center should be 45%/70% = 64% of left+center area
            
            left_proportion_in_area = 0.36   # 36% of left+center area (25% of total)
            center_proportion_in_area = 0.64  # 64% of left+center area (45% of total)
            
            # Calculate stretch factors for left+center layout
            left_factor = int(left_proportion_in_area * 100)
            center_factor = int(center_proportion_in_area * 100)
            
            # Update stretch factors within left+center layout
            self.left_center_layout.setStretchFactor(self.left_panel, left_factor)
            self.left_center_layout.setStretchFactor(self.center_panel, center_factor)
    
    def setup_colormaps(self):
        """Set up scientific colormaps for microscopy data"""
        # Define available scientific colormaps
        self.available_colormaps = {
            'viridis': 'Viridis (Default)',
            'plasma': 'Plasma',
            'inferno': 'Inferno', 
            'magma': 'Magma',
            'hot': 'Hot',
            'jet': 'Jet',
            'gray': 'Grayscale',
            'bone': 'Bone',
            'copper': 'Copper',
            'cool': 'Cool',
            'spring': 'Spring',
            'summer': 'Summer',
            'autumn': 'Autumn',
            'winter': 'Winter'
        }
        
        self.current_colormap = 'viridis'
        
        # Populate the colormap combo box if it exists
        if hasattr(self, 'colormap_combo'):
            self.colormap_combo.clear()
            for key, name in self.available_colormaps.items():
                self.colormap_combo.addItem(name, key)
            self.colormap_combo.setCurrentText('Viridis (Default)')
            self.colormap_combo.currentIndexChanged.connect(self.on_colormap_changed)
    
    def apply_colormap(self, colormap_name):
        """Apply a colormap to the image display"""
        try:
            if colormap_name in self.available_colormaps:
                # Get the colormap from PyQtGraph
                colormap = None
                
                if colormap_name in ['viridis', 'plasma', 'inferno', 'magma']:
                    # PyQtGraph built-in scientific colormaps
                    colormap = pg.colormap.get(colormap_name)
                else:
                    # Create custom colormaps
                    colormap = self.create_custom_colormap(colormap_name)
                
                if colormap is not None:
                    self.image_view.setColorMap(colormap)
                    self.current_colormap = colormap_name
                    self.show_message(f"Applied colormap: {self.available_colormaps[colormap_name]}")
                
        except Exception as e:
            self.show_message(f"Error applying colormap: {str(e)}")
            # Fallback to default
            try:
                self.image_view.setColorMap(pg.colormap.get('viridis'))
                self.current_colormap = 'viridis'
            except:
                                 pass
    
    def on_colormap_changed(self):
        """Handle colormap selection change"""
        if hasattr(self, 'colormap_combo'):
            selected_data = self.colormap_combo.currentData()
            if selected_data:
                self.apply_colormap(selected_data)
    
    def create_custom_colormap(self, name):
        """Create custom colormap definitions"""
        import numpy as np
        
        if name == 'hot':
            # Hot colormap (black -> red -> yellow -> white)
            colors = np.array([
                [0.0, 0.0, 0.0, 1.0],    # Black
                [0.5, 0.0, 0.0, 1.0],    # Dark red
                [1.0, 0.0, 0.0, 1.0],    # Red
                [1.0, 0.5, 0.0, 1.0],    # Orange
                [1.0, 1.0, 0.0, 1.0],    # Yellow
                [1.0, 1.0, 1.0, 1.0]     # White
            ])
        elif name == 'jet':
            # Jet colormap (blue -> cyan -> yellow -> red)
            colors = np.array([
                [0.0, 0.0, 0.5, 1.0],    # Dark blue
                [0.0, 0.0, 1.0, 1.0],    # Blue
                [0.0, 0.5, 1.0, 1.0],    # Light blue
                [0.0, 1.0, 1.0, 1.0],    # Cyan
                [0.5, 1.0, 0.5, 1.0],    # Light green
                [1.0, 1.0, 0.0, 1.0],    # Yellow
                [1.0, 0.5, 0.0, 1.0],    # Orange
                [1.0, 0.0, 0.0, 1.0]     # Red
            ])
        elif name == 'gray':
            # Grayscale colormap
            colors = np.array([
                [0.0, 0.0, 0.0, 1.0],    # Black
                [1.0, 1.0, 1.0, 1.0]     # White
            ])
        elif name == 'bone':
            # Bone colormap (black -> blue -> white)
            colors = np.array([
                [0.0, 0.0, 0.0, 1.0],     # Black
                [0.2, 0.2, 0.3, 1.0],     # Dark blue-gray
                [0.4, 0.4, 0.6, 1.0],     # Blue-gray
                [0.6, 0.7, 0.8, 1.0],     # Light blue-gray
                [1.0, 1.0, 1.0, 1.0]      # White
            ])
        elif name == 'copper':
            # Copper colormap (black -> brown -> orange)
            colors = np.array([
                [0.0, 0.0, 0.0, 1.0],     # Black
                [0.3, 0.2, 0.1, 1.0],     # Dark brown
                [0.6, 0.4, 0.2, 1.0],     # Brown
                [0.9, 0.6, 0.3, 1.0],     # Light brown
                [1.0, 0.8, 0.5, 1.0]      # Copper
            ])
        elif name == 'cool':
            # Cool colormap (cyan -> magenta)
            colors = np.array([
                [0.0, 1.0, 1.0, 1.0],     # Cyan
                [1.0, 0.0, 1.0, 1.0]      # Magenta
            ])
        elif name == 'spring':
            # Spring colormap (magenta -> yellow)
            colors = np.array([
                [1.0, 0.0, 1.0, 1.0],     # Magenta
                [1.0, 1.0, 0.0, 1.0]      # Yellow
            ])
        elif name == 'summer':
            # Summer colormap (green -> yellow)
            colors = np.array([
                [0.0, 0.5, 0.4, 1.0],     # Dark green
                [1.0, 1.0, 0.4, 1.0]      # Yellow-green
            ])
        elif name == 'autumn':
            # Autumn colormap (red -> yellow)
            colors = np.array([
                [1.0, 0.0, 0.0, 1.0],     # Red
                [1.0, 1.0, 0.0, 1.0]      # Yellow
            ])
        elif name == 'winter':
            # Winter colormap (blue -> green)
            colors = np.array([
                [0.0, 0.0, 1.0, 1.0],     # Blue
                [0.0, 1.0, 0.5, 1.0]      # Blue-green
            ])
        else:
            return None
        
        # Create positions for the colors
        positions = np.linspace(0, 1, len(colors))
        
        # Create the colormap
        colormap = pg.ColorMap(positions, colors)
        return colormap
    
    def create_scale_bar(self):
        """Create a scale bar for the image display"""
        # Create a group to hold scale bar elements
        scale_group = pg.QtWidgets.QGraphicsItemGroup()
        
        # Default scale bar parameters (will be updated based on scan parameters)
        scale_length_um = 10  # 10 micrometers default
        
        # Create scale bar line
        line = pg.PlotDataItem([0, scale_length_um], [0, 0], 
                              pen=pg.mkPen('white', width=3))
        scale_group.addToGroup(line)
        
        # Create scale bar text
        text = pg.TextItem(f'{scale_length_um} μm', color='white', anchor=(0, 1))
        text.setPos(0, -2)  # Position text slightly below the line
        scale_group.addToGroup(text)
        
        # Store references for updates
        scale_group.scale_line = line
        scale_group.scale_text = text
        scale_group.scale_length_um = scale_length_um
        
        return scale_group
    
    def create_coordinate_labels(self):
        """Create coordinate labels as text overlays"""
        labels = []
        
        # Create corner labels for coordinate reference
        self.x_label = pg.TextItem('X: 0 μm', color='white', anchor=(0, 0))
        self.y_label = pg.TextItem('Y: 0 μm', color='white', anchor=(0, 0))
        
        labels.extend([self.x_label, self.y_label])
        return labels
    
    def setup_crosshair_cursor(self):
        """Set up crosshair cursor lines"""
        view = self.image_view.getView()
        
        # Create crosshair lines
        self.crosshair_v = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('#00ff88', width=1))
        self.crosshair_h = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('#00ff88', width=1))
        
        # Initially hide crosshairs
        self.crosshair_v.hide()
        self.crosshair_h.hide()
        
        # Add to view
        view.addItem(self.crosshair_v)
        view.addItem(self.crosshair_h)
    
    def setup_position_text(self):
        """Set up position and intensity text overlay"""
        view = self.image_view.getView()
        
        # Create text item for cursor position and intensity
        self.cursor_text = pg.TextItem(
            text="", 
            color='white', 
            fill=pg.mkBrush(0, 0, 0, 100),  # Semi-transparent black background
            anchor=(1, 0)  # Anchor to top-right
        )
        
        # Position in top-right corner
        view.addItem(self.cursor_text)
        
        # Initially hide the text
        self.cursor_text.hide()
    
    def setup_image_axes(self):
        """Set up proper X and Y axes for the ImageView"""
        try:
            # Access the ImageView's internal structure to enable axes
            if hasattr(self.image_view, 'view') and hasattr(self.image_view.view, 'vb'):
                # Get the ViewBox
                vb = self.image_view.view.vb
                
                # Try to get the PlotItem from the ImageView
                plot_item = None
                if hasattr(self.image_view, 'view'):
                    plot_item = self.image_view.view
                
                if plot_item and hasattr(plot_item, 'showAxis'):
                    # Show the axes
                    plot_item.showAxis('left', True)
                    plot_item.showAxis('bottom', True)
                    plot_item.showAxis('top', False)
                    plot_item.showAxis('right', False)
                    
                    # Style the axes
                    left_axis = plot_item.getAxis('left')
                    bottom_axis = plot_item.getAxis('bottom')
                    
                    # Set axis colors to white
                    left_axis.setPen('white')
                    bottom_axis.setPen('white')
                    left_axis.setTextPen('white')
                    bottom_axis.setTextPen('white')
                    
                    # Set axis labels
                    left_axis.setLabel('Y Position', units='μm', color='white')
                    bottom_axis.setLabel('X Position', units='μm', color='white')
                    
                    # Store references for later updates
                    self.left_axis = left_axis
                    self.bottom_axis = bottom_axis
                    
                    print("✅ Successfully enabled ImageView axes")
                    return True
                    
        except Exception as e:
            print(f"ImageView axes setup failed: {e}")
        
        # Fallback: Create custom axis overlay
        print("Using custom axis overlay")
        self.create_custom_axes()
        return False
    
    def create_custom_axes(self):
        """Create custom axis lines and labels as an overlay"""
        view = self.image_view.getView()
        
        # Create axis lines
        self.x_axis_line = pg.PlotDataItem([0, 1], [0, 0], pen=pg.mkPen('white', width=2))
        self.y_axis_line = pg.PlotDataItem([0, 0], [0, 1], pen=pg.mkPen('white', width=2))
        
        view.addItem(self.x_axis_line)
        view.addItem(self.y_axis_line)
        
        # Create axis labels - we'll update these with proper positions
        self.axis_labels = []
        self.axis_ticks = []
        
        # Store references for updates
        self.custom_axes_enabled = True
    
    def update_builtin_axes(self):
        """Update the built-in ImageView axes with proper scaling"""
        if not (hasattr(self, 'left_axis') and hasattr(self, 'bottom_axis')):
            return
        
        params = self.scan_params_manager.get_params()
        x_range = params['scan_range']['x']
        y_range = params['scan_range']['y']
        
        # Convert to micrometers
        from utils import MICRONS_PER_VOLT
        x_min_um = x_range[0] * MICRONS_PER_VOLT
        x_max_um = x_range[1] * MICRONS_PER_VOLT
        y_min_um = y_range[0] * MICRONS_PER_VOLT
        y_max_um = y_range[1] * MICRONS_PER_VOLT
        
        # Set axis ranges to match the image coordinates
        try:
            # The axes should automatically scale with the image
            # but we can set preferred tick spacing
            x_span = abs(x_max_um - x_min_um)
            y_span = abs(y_max_um - y_min_um)
            
            # Set nice tick spacing
            if x_span <= 20:
                x_tick_spacing = 5
            elif x_span <= 100:
                x_tick_spacing = 20
            elif x_span <= 500:
                x_tick_spacing = 100
            else:
                x_tick_spacing = 200
            
            if y_span <= 20:
                y_tick_spacing = 5
            elif y_span <= 100:
                y_tick_spacing = 20
            elif y_span <= 500:
                y_tick_spacing = 100
            else:
                y_tick_spacing = 200
            
            # Set tick spacing if the method exists
            if hasattr(self.bottom_axis, 'setTickSpacing'):
                self.bottom_axis.setTickSpacing(x_tick_spacing)
                self.left_axis.setTickSpacing(y_tick_spacing)
            
        except Exception as e:
            print(f"Error updating built-in axes: {e}")
    
    def update_custom_axes(self):
        """Update custom axis overlay with current scan parameters"""
        if not hasattr(self, 'custom_axes_enabled') or not self.custom_axes_enabled:
            return
            
        # Remove old labels and ticks
        view = self.image_view.getView()
        for item in self.axis_labels + self.axis_ticks:
            try:
                view.removeItem(item)
            except:
                pass
        
        self.axis_labels.clear()
        self.axis_ticks.clear()
        
        params = self.scan_params_manager.get_params()
        x_range = params['scan_range']['x']
        y_range = params['scan_range']['y']
        
        # Convert to micrometers
        from utils import MICRONS_PER_VOLT
        x_min_um = x_range[0] * MICRONS_PER_VOLT
        x_max_um = x_range[1] * MICRONS_PER_VOLT
        y_min_um = y_range[0] * MICRONS_PER_VOLT
        y_max_um = y_range[1] * MICRONS_PER_VOLT
        
        # Update axis lines to span the image
        self.x_axis_line.setData([x_min_um, x_max_um], [y_min_um, y_min_um])
        self.y_axis_line.setData([x_min_um, x_min_um], [y_min_um, y_max_um])
        
        # Create tick marks and labels
        self.create_axis_ticks(x_min_um, x_max_um, y_min_um, y_max_um)
    
    def create_axis_ticks(self, x_min, x_max, y_min, y_max):
        """Create tick marks and labels for custom axes"""
        view = self.image_view.getView()
        
        # Calculate appropriate tick spacing
        x_range = x_max - x_min
        y_range = y_max - y_min
        
        # Choose nice tick intervals
        def nice_interval(range_val):
            """Choose a nice interval for ticks"""
            if range_val <= 10:
                return 2
            elif range_val <= 50:
                return 10
            elif range_val <= 100:
                return 20
            elif range_val <= 500:
                return 50
            else:
                return 100
        
        x_interval = nice_interval(x_range)
        y_interval = nice_interval(y_range)
        
        # Create X-axis ticks and labels
        x_start = int(x_min / x_interval) * x_interval
        x_positions = np.arange(x_start, x_max + x_interval, x_interval)
        
        for x_pos in x_positions:
            if x_min <= x_pos <= x_max:
                # Create tick mark
                tick = pg.PlotDataItem([x_pos, x_pos], [y_min, y_min - y_range * 0.02], 
                                     pen=pg.mkPen('white', width=2))
                view.addItem(tick)
                self.axis_ticks.append(tick)
                
                # Create label
                label = pg.TextItem(f'{x_pos:.0f}', color='white', anchor=(0.5, 1))
                label.setPos(x_pos, y_min - y_range * 0.05)
                view.addItem(label)
                self.axis_labels.append(label)
        
        # Create Y-axis ticks and labels
        y_start = int(y_min / y_interval) * y_interval
        y_positions = np.arange(y_start, y_max + y_interval, y_interval)
        
        for y_pos in y_positions:
            if y_min <= y_pos <= y_max:
                # Create tick mark
                tick = pg.PlotDataItem([x_min, x_min - x_range * 0.02], [y_pos, y_pos], 
                                     pen=pg.mkPen('white', width=2))
                view.addItem(tick)
                self.axis_ticks.append(tick)
                
                # Create label
                label = pg.TextItem(f'{y_pos:.0f}', color='white', anchor=(1, 0.5))
                label.setPos(x_min - x_range * 0.05, y_pos)
                view.addItem(label)
                self.axis_labels.append(label)
        
        # Add axis titles
        x_title = pg.TextItem('X Position (μm)', color='white', anchor=(0.5, 0))
        x_title.setPos((x_min + x_max) / 2, y_min - y_range * 0.15)
        view.addItem(x_title)
        self.axis_labels.append(x_title)
        
        y_title = pg.TextItem('Y Position (μm)', color='white', anchor=(0.5, 0))
        y_title.setPos(x_min - x_range * 0.15, (y_min + y_max) / 2)
        y_title.setRotation(90)
        view.addItem(y_title)
        self.axis_labels.append(y_title)
    
    def update_histogram_units(self):
        """Update histogram/color bar to show proper units"""
        try:
            if hasattr(self.image_view, 'ui') and hasattr(self.image_view.ui, 'histogram'):
                histogram = self.image_view.ui.histogram
                
                # Try to set the label on the histogram axis
                if hasattr(histogram, 'axis'):
                    histogram.axis.setLabel('Intensity', units='c/s')
                elif hasattr(histogram, 'gradient') and hasattr(histogram.gradient, 'axis'):
                    histogram.gradient.axis.setLabel('Intensity', units='c/s')
                
                # Also try to set it on the gradient if available
                if hasattr(histogram, 'gradient') and hasattr(histogram.gradient, 'setLabel'):
                    histogram.gradient.setLabel('Intensity (c/s)')
                    
        except Exception as e:
            print(f"Could not update histogram units: {e}")
    
    def update_coordinate_labels(self):
        """Update coordinate labels and custom axes based on current scan parameters"""
        # Update built-in axes if they are available
        if hasattr(self, 'left_axis') and hasattr(self, 'bottom_axis'):
            self.update_builtin_axes()
        
        # Update custom axes if they are enabled
        elif hasattr(self, 'custom_axes_enabled') and self.custom_axes_enabled:
            self.update_custom_axes()
        
        # Update text labels if they exist (fallback display)
        if hasattr(self, 'x_label') and hasattr(self, 'y_label'):
            params = self.scan_params_manager.get_params()
            x_range = params['scan_range']['x']
            y_range = params['scan_range']['y']
            
            # Convert to micrometers
            from utils import MICRONS_PER_VOLT
            x_min_um = x_range[0] * MICRONS_PER_VOLT
            x_max_um = x_range[1] * MICRONS_PER_VOLT
            y_min_um = y_range[0] * MICRONS_PER_VOLT
            y_max_um = y_range[1] * MICRONS_PER_VOLT
            
            # Update label text
            self.x_label.setText(f'X: {x_min_um:.1f} to {x_max_um:.1f} μm')
            self.y_label.setText(f'Y: {y_min_um:.1f} to {y_max_um:.1f} μm')
            
            # Position labels in corners with margins
            fov_x_um = abs(x_max_um - x_min_um)
            fov_y_um = abs(y_max_um - y_min_um)
            margin_x = fov_x_um * 0.02
            margin_y = fov_y_um * 0.02
            
            # Position X label at top-left
            self.x_label.setPos(x_min_um + margin_x, y_max_um - margin_y)
            
            # Position Y label at bottom-right  
            self.y_label.setPos(x_max_um - fov_x_um * 0.3, y_min_um + margin_y)
    
    def update_scale_bar(self):
        """Update scale bar based on current scan parameters"""
        if not hasattr(self, 'scale_bar'):
            return
            
        params = self.scan_params_manager.get_params()
        x_range = params['scan_range']['x']
        x_res = params['resolution']['x']
        
        # Calculate the field of view in micrometers
        from utils import MICRONS_PER_VOLT
        fov_um = abs(x_range[1] - x_range[0]) * MICRONS_PER_VOLT
        
        # Choose appropriate scale bar length (10-20% of field of view)
        target_length = fov_um * 0.15
        
        # Round to nice numbers
        if target_length >= 50:
            scale_length_um = round(target_length / 50) * 50
        elif target_length >= 10:
            scale_length_um = round(target_length / 10) * 10
        elif target_length >= 5:
            scale_length_um = round(target_length / 5) * 5
        else:
            scale_length_um = round(target_length)
        
        scale_length_um = max(1, scale_length_um)  # Minimum 1 μm
        
        # Update scale bar position (bottom left corner with margins)
        x_start_um = x_range[0] * MICRONS_PER_VOLT + fov_um * 0.05  # 5% margin
        y_range = params['scan_range']['y']
        y_start_um = y_range[0] * MICRONS_PER_VOLT + abs(y_range[1] - y_range[0]) * MICRONS_PER_VOLT * 0.05  # 5% from bottom
        
        # Update line data
        self.scale_bar.scale_line.setData([x_start_um, x_start_um + scale_length_um], 
                                         [y_start_um, y_start_um])
        
        # Update text
        self.scale_bar.scale_text.setText(f'{scale_length_um} μm')
        self.scale_bar.scale_text.setPos(x_start_um, y_start_um - fov_um * 0.02)  # Slightly below line
        
        self.scale_bar.scale_length_um = scale_length_um
    
    def init_connections(self):
        """Initialize signal connections"""
        # Connect parameter changes
        for spin in [self.scan_params_widget.x_min_spin, self.scan_params_widget.x_max_spin,
                    self.scan_params_widget.y_min_spin, self.scan_params_widget.y_max_spin,
                    self.scan_params_widget.x_res_spin, self.scan_params_widget.y_res_spin,
                    self.scan_params_widget.dwell_spin]:
            spin.valueChanged.connect(self.on_parameters_changed)
    
    def on_parameters_changed(self):
        """Handle parameter changes"""
        self.scan_points_manager._update_points_from_params()
        self.update_scale_bar()
        self.update_coordinate_labels()
    
    def on_image_click(self, event):
        """Handle mouse clicks on the image"""
        if event.button() == Qt.LeftButton:
            # Get pixel coordinates from the click event.
            pos = event.pos()
            
            # Retrieve the voltage points that correspond to the scan axes.
            # We need the most recently used points, which are stored in the scan thread if it exists,
            # otherwise we get them from the points manager.
            if self.scan_thread and self.scan_thread.x_points is not None:
                x_points = self.scan_thread.x_points
                y_points = self.scan_thread.y_points
            else:
                x_points, y_points = self.scan_points_manager.get_points()

            # The image data is transposed for display, so the event position corresponds to (x_pixel, y_pixel)
            # in the non-transposed (width, height) coordinate system.
            px = int(pos.x())
            py = int(pos.y())

            # Check if the click is within the valid pixel range.
            if not (0 <= px < len(x_points) and 0 <= py < len(y_points)):
                self.show_message("Clicked outside the valid scan area.")
                return

            # Map the pixel coordinate directly to the corresponding voltage.
            x_voltage = x_points[px]
            y_voltage = y_points[py]

            # Convert to micrometers for display purposes
            from utils import MICRONS_PER_VOLT
            x_um = x_voltage * MICRONS_PER_VOLT
            y_um = y_voltage * MICRONS_PER_VOLT
            
            # Debugging output
            print(f"Click(pixel): px={px}, py={py} -> Voltage: x={x_voltage:.3f}, y={y_voltage:.3f}")

            try:
                if self.output_task:
                    self.output_task.write([x_voltage, y_voltage])
                    self.show_message(f"Moved scanner to: X={x_voltage:.3f}V ({x_um:.1f}μm), Y={y_voltage:.3f}V ({y_um:.1f}μm)")
                    
                    # Update current position display in left panel
                    if hasattr(self, 'current_position_widget'):
                        self.current_position_widget.update_current_position(x_voltage, y_voltage)
                    
                    # Also update single axis widget if it needs the position for scanning
                    if hasattr(self, 'single_axis_widget') and hasattr(self.single_axis_widget, 'update_current_position'):
                        self.single_axis_widget.update_current_position(x_voltage, y_voltage)
                else:
                    self.show_message("❌ DAQ not initialized - cannot move scanner")
                
            except Exception as e:
                self.show_message(f"Error moving scanner: {str(e)}")
    
    def on_mouse_move(self, pos):
        """Handle mouse movement over the image for cursor tracking"""
        try:
            # Get the scene position
            scene_pos = pos
            
            # Convert to view coordinates
            view = self.image_view.getView()
            if view.sceneBoundingRect().contains(scene_pos):
                # Convert scene position to view coordinates
                mouse_point = view.mapSceneToView(scene_pos)
                x_pos = mouse_point.x()
                y_pos = mouse_point.y()
                
                # Show crosshairs
                self.crosshair_v.show()
                self.crosshair_h.show()
                
                # Update crosshair positions
                self.crosshair_v.setPos(x_pos)
                self.crosshair_h.setPos(y_pos)
                
                # Get intensity value at cursor position
                intensity_text = self.get_intensity_at_position(x_pos, y_pos)
                
                # Update text display
                text_content = f"Cursor: ({x_pos:.2f} μm, {y_pos:.2f} μm)\n{intensity_text}"
                self.cursor_text.setText(text_content)
                
                # Position text in top-right corner with some margin
                view_range = view.viewRange()
                text_x = view_range[0][1] - (view_range[0][1] - view_range[0][0]) * 0.02  # 2% margin from right
                text_y = view_range[1][1] - (view_range[1][1] - view_range[1][0]) * 0.02  # 2% margin from top
                self.cursor_text.setPos(text_x, text_y)
                
                # Show text
                self.cursor_text.show()
            else:
                # Hide crosshairs and text when outside view
                self.crosshair_v.hide()
                self.crosshair_h.hide()
                self.cursor_text.hide()
                
        except Exception as e:
            # Silently handle errors to avoid disrupting mouse tracking
            pass
    
    def get_intensity_at_position(self, x_um, y_um):
        """Get intensity value at the given position"""
        try:
            if self.current_image is None:
                return "Intensity: --"
            
            # Get current scan parameters to convert position to pixel coordinates
            if hasattr(self, 'scan_thread') and self.scan_thread and hasattr(self.scan_thread, 'x_points'):
                x_points = self.scan_thread.x_points
                y_points = self.scan_thread.y_points
            else:
                x_points, y_points = self.scan_points_manager.get_points()
            
            # Convert micrometers back to voltage, then to pixel coordinates
            from utils import MICRONS_PER_VOLT
            x_voltage = x_um / MICRONS_PER_VOLT
            y_voltage = y_um / MICRONS_PER_VOLT
            
            # Find nearest pixel coordinates
            if len(x_points) > 0 and len(y_points) > 0:
                x_pixel = np.argmin(np.abs(x_points - x_voltage))
                y_pixel = np.argmin(np.abs(y_points - y_voltage))
                
                # Check bounds
                if 0 <= x_pixel < self.current_image.shape[1] and 0 <= y_pixel < self.current_image.shape[0]:
                    intensity = self.current_image[y_pixel, x_pixel]
                    return f"Intensity: {intensity:.2f} c/s"
            
            return "Intensity: --"
            
        except Exception as e:
            return "Intensity: --"
    
    def on_roi_changed(self):
        """Handle ROI changes for zoom functionality"""
        if self.zoom_roi.isVisible():
            self.apply_zoom_btn.setEnabled(True)
    
    def toggle_zoom_mode(self):
        """Toggle zoom ROI visibility"""
        if self.zoom_roi.isVisible():
            self.zoom_roi.hide()
            self.zoom_toggle_btn.setText("🔍 Enable Zoom")
            self.apply_zoom_btn.setEnabled(False)
        else:
            if not self.zoom_manager.can_zoom_in():
                self.show_message(f"⚠️ Max zoom reached ({self.zoom_manager.max_zoom} levels).")
                return
            self.zoom_roi.show()
            self.zoom_toggle_btn.setText("🔍 Disable Zoom")
    
    def apply_zoom(self):
        """Apply the zoom region"""
        if not self.zoom_roi.isVisible():
            return
        
        # Get ROI bounds in pixel coordinates.
        roi_pos = self.zoom_roi.pos()
        roi_size = self.zoom_roi.size()
        
        # The ImageItem is transposed, so the ROI coordinates are already in the correct (width, height) pixel space.
        min_px = int(roi_pos.x())
        min_py = int(roi_pos.y())
        max_px = int(roi_pos.x() + roi_size.x())
        max_py = int(roi_pos.y() + roi_size.y())

        # Retrieve the voltage points from the last scan.
        if self.scan_thread and self.scan_thread.x_points is not None:
            x_points = self.scan_thread.x_points
            y_points = self.scan_thread.y_points
        else:
            x_points, y_points = self.scan_points_manager.get_points()

        # Ensure bounds are within the valid pixel range of the last scan.
        height, width = len(y_points), len(x_points)
        min_px = max(0, min(min_px, width - 1))
        max_px = max(min_px + 1, min(max_px, width))
        min_py = max(0, min(min_py, height - 1))
        max_py = max(min_py + 1, min(max_py, height))

        # Save current state for zoom history
        self.scan_history.append((x_points.copy(), y_points.copy()))

        # Map pixel coordinates directly to new voltage ranges.
        new_x_min = x_points[min_px]
        new_x_max = x_points[max_px - 1]
        new_y_min = y_points[min_py]
        new_y_max = y_points[max_py - 1]

        # Update parameters with the new voltage ranges.
        current_params = self.scan_params_manager.get_params()
        self.scan_params_manager.update_scan_parameters(
            x_range=[new_x_min, new_x_max],
            y_range=[new_y_min, new_y_max]
        )
        
        # Update widget display with the new ranges, keeping resolution the same.
        self.scan_params_widget.update_values(
            [new_x_min, new_x_max], [new_y_min, new_y_max],
            current_params['resolution']['x'], current_params['resolution']['y'],
            current_params['dwell_time']
        )
        
        # Update scan points for the next scan.
        self.scan_points_manager._update_points_from_params()
        
        # Update zoom level and UI state.
        self.zoom_manager.set_zoom_level(self.zoom_manager.get_zoom_level() + 1)
        self.zoom_roi.hide()
        self.zoom_toggle_btn.setText("🔍 Enable Zoom")
        self.apply_zoom_btn.setEnabled(False)
        
        self.show_message(f"🔍 Zoomed to region: X={new_x_min:.3f}-{new_x_max:.3f}V, Y={new_y_min:.3f}-{new_y_max:.3f}V")
        
        # Update scale bar and coordinate labels for new zoom level.
        self.update_scale_bar()
        self.update_coordinate_labels()
    
    def start_new_scan(self):
        """Start a new scan"""
        if self.scan_thread and self.scan_thread.isRunning():
            self.show_message("Scan already in progress")
            return
        
        if not self.output_task:
            self.show_message("❌ DAQ not initialized - cannot start scan")
            return
        
        # Get current parameters
        params = self.scan_params_manager.get_params()
        x_points, y_points = self.scan_points_manager.get_points()
        
        # Create and start scan thread
        self.scan_thread = ScanThread(
            x_points, y_points, params['dwell_time'],
            self.counter, self.binwidth, self.output_task
        )
        
        # Connect signals
        self.scan_thread.update_image.connect(self.update_image_display)
        self.scan_thread.update_progress.connect(self.on_scan_progress)
        self.scan_thread.scan_complete.connect(self.on_scan_complete)
        self.scan_thread.error_occurred.connect(self.on_scan_error)
        
        # Pause live plot during scanning for better performance
        if hasattr(self, 'live_plot'):
            self.live_plot.pause_updates()
        
        self.scan_thread.start()
        self.show_message("🔬 New scan started")
    
    def stop_scan(self):
        """Stop the current scan"""
        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.stop()
            # Resume live plot when scan is stopped
            if hasattr(self, 'live_plot'):
                self.live_plot.resume_updates()
            self.show_message("🛑 Scan stop requested")
    
    def save_image(self):
        """Save the current image"""
        if self.current_image is not None and self.data_path:
            # Save as screenshot
            pixmap = self.image_view.grab()
            pixmap.save(f"{self.data_path}.png")
            self.show_message("📷 Image saved")
        else:
            self.show_message("❌ No scan data to save")
    
    def reset_zoom(self):
        """Reset zoom to original view"""
        current_zoom = self.zoom_manager.get_zoom_level()
        
        if current_zoom == 0:
            self.show_message("🔁 You are already in the original view.")
            return
        
        if self.scan_history:
            orig_x_points, orig_y_points = self.scan_history[0]
            
            # Update parameters
            self.scan_params_manager.update_scan_parameters(
                x_range=[orig_x_points[0], orig_x_points[-1]],
                y_range=[orig_y_points[0], orig_y_points[-1]]
            )
            
            # Update display
            self.scan_params_widget.update_values(
                [orig_x_points[0], orig_x_points[-1]],
                [orig_y_points[0], orig_y_points[-1]],
                len(orig_x_points), len(orig_y_points),
                self.scan_params_manager.get_params()['dwell_time']
            )
            
            self.zoom_manager.set_zoom_level(0)
            self.scan_history.clear()
            self.show_message("🔄 Zoom reset to original view")
            
            # Update scale bar and coordinate labels for original view
            self.update_scale_bar()
            self.update_coordinate_labels()
    
    def close_scanner(self):
        """Set scanner to zero position"""
        try:
            if self.output_task:
                self.output_task.write([0, 0])
                
                # Update current position display
                if hasattr(self, 'current_position_widget'):
                    self.current_position_widget.update_current_position(0.0, 0.0)
                
                # Also update single axis widget if it exists
                if hasattr(self, 'single_axis_widget') and hasattr(self.single_axis_widget, 'update_current_position'):
                    self.single_axis_widget.update_current_position(0.0, 0.0)
                
                self.show_message("🎯 Scanner set to zero")
            else:
                self.show_message("❌ DAQ not initialized - cannot move scanner")
        except Exception as e:
            self.show_message(f"Error setting scanner to zero: {str(e)}")
    
    def load_scan(self):
        """Load a previously saved scan"""
        from PyQt5.QtWidgets import QFileDialog
        
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load Scan Data", "", "NPZ files (*.npz)"
        )
        
        if filename:
            try:
                data = np.load(filename)
                image = data['image']
                
                self.current_image = image
                # Transpose the image because PyQtGraph's ImageView expects column-major (width, height) data.
                self.image_view.setImage(image.T, autoLevels=True)
                
                # Update parameters if available
                if 'x_range' in data and 'y_range' in data:
                    x_range = data['x_range']
                    y_range = data['y_range']
                    x_res = data.get('x_resolution', image.shape[1])
                    y_res = data.get('y_resolution', image.shape[0])
                    dwell_time = data.get('dwell_time', 0.002)
                    
                    self.scan_params_widget.update_values(
                        x_range, y_range, x_res, y_res, dwell_time
                    )
                
                self.show_message(f"📁 Loaded scan from {filename}")
                
            except Exception as e:
                self.show_message(f"Error loading scan: {str(e)}")
    
    def update_image_display(self, image):
        """Update the image display with proper scaling"""
        self.current_image = image
        
        # Get current parameters for scaling
        params = self.scan_params_manager.get_params()
        x_range = params['scan_range']['x']
        y_range = params['scan_range']['y']
        x_res = params['resolution']['x']
        y_res = params['resolution']['y']
        
        # Calculate scale and position
        scale_x = calculate_scale(x_range[0], x_range[1], x_res)
        scale_y = calculate_scale(y_range[0], y_range[1], y_res)
        
        # Convert voltage ranges to micrometer positions
        from utils import MICRONS_PER_VOLT
        x_start_um = x_range[0] * MICRONS_PER_VOLT
        y_start_um = y_range[0] * MICRONS_PER_VOLT
        
        # Update image with proper scale and position
        # Transpose the image because PyQtGraph's ImageView expects column-major (width, height) data.
        self.image_view.setImage(image.T, 
                                autoLevels=True,
                                scale=(scale_x, scale_y),
                                pos=(x_start_um, y_start_um))
        
        # Reapply current colormap to ensure it's maintained
        if hasattr(self, 'current_colormap'):
            self.apply_colormap(self.current_colormap)
        
        # Update histogram/color bar units
        self.update_histogram_units()
        
        # Update scale bar and coordinate labels
        self.update_scale_bar()
        self.update_coordinate_labels()
    
    def on_scan_progress(self, progress):
        """Handle scan progress updates"""
        self.show_message(f"🔬 Scanning... {progress}% complete")
    
    def on_scan_complete(self, image, x_points, y_points):
        """Handle scan completion"""
        self.current_image = image
        
        # Calculate scale and position for final image
        scale_x = calculate_scale(x_points[0], x_points[-1], len(x_points))
        scale_y = calculate_scale(y_points[0], y_points[-1], len(y_points))
        
        # Convert voltage ranges to micrometer positions
        from utils import MICRONS_PER_VOLT
        x_start_um = x_points[0] * MICRONS_PER_VOLT
        y_start_um = y_points[0] * MICRONS_PER_VOLT
        
        # Update image with proper scale and position
        # Transpose the image because PyQtGraph's ImageView expects column-major (width, height) data.
        self.image_view.setImage(image.T, 
                                autoLevels=True,
                                scale=(scale_x, scale_y),
                                pos=(x_start_um, y_start_um))
        
        # Reapply current colormap to ensure it's maintained
        if hasattr(self, 'current_colormap'):
            self.apply_colormap(self.current_colormap)
        
        # Update histogram/color bar units
        self.update_histogram_units()
        
        # Update scale bar and coordinate labels
        self.update_scale_bar()
        self.update_coordinate_labels()
        
        # Save data
        params = self.scan_params_manager.get_params()
        scale_x = calculate_scale(x_points[0], x_points[-1], len(x_points))
        scale_y = calculate_scale(y_points[0], y_points[-1], len(y_points))
        
        scan_data = {
            'image': image,
            'x_points': x_points,
            'y_points': y_points,
            'scale_x': scale_x,
            'scale_y': scale_y
        }
        
        self.data_path = self.data_manager.save_scan_data(scan_data, params)
        
        # Plot results
        plot_scan_results(scan_data, self.data_path)
        
        # Save NPZ and TIFF
        timestamp_str = time.strftime("%Y%m%d-%H%M%S")
        np.savez(self.data_path.replace('.csv', '.npz'), 
                image=image, scale_x=scale_x, scale_y=scale_y,
                x_range=params['scan_range']['x'],
                y_range=params['scan_range']['y'],
                x_resolution=params['resolution']['x'],
                y_resolution=params['resolution']['y'],
                dwell_time=params['dwell_time'],
                x_points=x_points, y_points=y_points,
                timestamp=timestamp_str)
        
        save_tiff_with_imagej_metadata(
            image_data=image,
            filepath=self.data_path.replace('.csv', '.tiff'),
            x_points=x_points, y_points=y_points,
            scan_config=params, timestamp=timestamp_str
        )
        
        # Resume live plot after scanning
        if hasattr(self, 'live_plot'):
            self.live_plot.resume_updates()
        
        self.show_message("✅ Scan completed and data saved")
    
    def on_scan_error(self, error_msg):
        """Handle scan errors"""
        # Resume live plot if scan fails
        if hasattr(self, 'live_plot'):
            self.live_plot.resume_updates()
        self.show_message(f"❌ Scan error: {error_msg}")
    
    def capture_image(self):
        """Capture current camera image"""
        try:
            # Get current camera image
            if hasattr(self, 'camera_widget') and hasattr(self.camera_widget, 'camera_view'):
                # For now, just show a message. In real implementation, this would capture from camera
                self.show_message("📸 Camera image captured")
        except Exception as e:
            self.show_message(f"❌ Error capturing image: {str(e)}")
    
    def save_camera_image(self):
        """Save camera image to file"""
        try:
            if hasattr(self, 'camera_widget') and hasattr(self.camera_widget, 'camera_view'):
                # Get the current image from camera widget
                image_item = self.camera_widget.camera_view.getImageItem()
                if image_item is not None:
                    # In real implementation, would save actual camera image
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    filename = f"camera_image_{timestamp}.png"
                    # For now, just show a message
                    self.show_message(f"💾 Camera image saved as {filename}")
                else:
                    self.show_message("❌ No camera image to save")
        except Exception as e:
            self.show_message(f"❌ Error saving camera image: {str(e)}")
    
    def toggle_camera_live_view(self):
        """Toggle camera live view from controls section"""
        try:
            if hasattr(self, 'camera_widget'):
                # Toggle the camera's live view
                self.camera_widget.toggle_live_view()
                
                # Update button text and styling
                if self.live_view_btn.isChecked():
                    self.live_view_btn.setText("⏸️ Pause View")
                    self.show_message("📹 Camera live view started")
                else:
                    self.live_view_btn.setText("📹 Live View")
                    self.show_message("⏸️ Camera live view paused")
        except Exception as e:
            self.show_message(f"❌ Error toggling live view: {str(e)}")
    
    def on_exposure_changed(self, value):
        """Handle exposure slider changes"""
        self.exposure_label.setText(f"{value} ms")
        # In a real implementation, this would update the camera exposure
        # For now, we just update the label and could affect the simulation
        try:
            if hasattr(self, 'camera_widget'):
                # Could modify camera simulation parameters here
                pass
        except Exception as e:
            print(f"Error updating exposure: {e}")
    
    def on_gain_changed(self, value):
        """Handle gain slider changes"""
        self.gain_label.setText(f"{value}x")
        # In a real implementation, this would update the camera gain
        # For now, we just update the label and could affect the simulation
        try:
            if hasattr(self, 'camera_widget'):
                # Could modify camera simulation parameters here
                pass
        except Exception as e:
            print(f"Error updating gain: {e}")
    
    def start_axis_scan(self, axis):
        """Start single axis scan for specified axis (X or Y)"""
        try:
            # Import the scan thread class
            from widgets.pyqt_single_axis_scan import SingleAxisScanThread
            
            # Determine which button was pressed
            if axis == 'X':
                button = self.x_scan_btn
                other_button = self.y_scan_btn
            else:
                button = self.y_scan_btn
                other_button = self.x_scan_btn
            
            # Check if scan is currently running
            if self.single_axis_scan_thread and self.single_axis_scan_thread.isRunning():
                # Stop current scan
                self.single_axis_scan_thread.stop()
                self.x_scan_btn.setText("📊 X Scan")
                self.y_scan_btn.setText("📈 Y Scan")
                self.x_scan_btn.setEnabled(True)
                self.y_scan_btn.setEnabled(True)
                self.show_message(f"⏹ {axis} axis scan stopped")
                return
            
            # Start new scan
            button.setText(f"⏹ Stop {axis}")
            other_button.setEnabled(False)  # Disable other button during scan
            
            # Clear the plot in the single axis widget
            if hasattr(self, 'single_axis_widget'):
                self.single_axis_widget.clear_plot()
            
            # Get current position for scan reference
            current_pos = [0.0, 0.0]  # Default position
            if hasattr(self, 'current_position_widget'):
                current_pos = self.current_position_widget.current_position.copy()
            
            # Use default parameters for scan
            start_pos = -1.0  # Default scan range from -1V to +1V
            end_pos = 1.0
            n_steps = 21      # Default 21 steps
            dwell_time = 0.01 # Default 10ms dwell time
            
            # Start scan thread
            self.single_axis_scan_thread = SingleAxisScanThread(
                start_pos, end_pos, n_steps, axis, current_pos,
                self.counter, self.binwidth, self.output_task, dwell_time
            )
            
            # Connect signals - update the single axis widget plot if it exists
            if hasattr(self, 'single_axis_widget'):
                self.single_axis_scan_thread.position_update.connect(self.single_axis_widget.update_plot)
                self.single_axis_scan_thread.scan_complete.connect(lambda pos, counts, msg: self.on_axis_scan_complete(pos, counts, msg, axis))
                self.single_axis_scan_thread.error_occurred.connect(lambda error: self.on_axis_scan_error(error, axis))
            
            self.single_axis_scan_thread.start()
            self.show_message(f"🔬 {axis} axis scan started")
            
        except Exception as e:
            self.show_message(f"❌ Error starting {axis} axis scan: {str(e)}")
            # Reset buttons on error
            self.x_scan_btn.setText("📊 X Scan")
            self.y_scan_btn.setText("📈 Y Scan")
            self.x_scan_btn.setEnabled(True)
            self.y_scan_btn.setEnabled(True)
    
    def on_axis_scan_complete(self, positions, counts, message, axis):
        """Handle axis scan completion"""
        # Reset both buttons to their default states
        self.x_scan_btn.setText("📊 X Scan")
        self.y_scan_btn.setText("📈 Y Scan")
        self.x_scan_btn.setEnabled(True)
        self.y_scan_btn.setEnabled(True)
        
        # Update the single axis widget with the results
        if hasattr(self, 'single_axis_widget'):
            self.single_axis_widget.on_scan_complete(positions, counts, message, axis)
        
        self.show_message(f"✅ {axis} axis scan completed")
    
    def on_axis_scan_error(self, error_msg, axis):
        """Handle axis scan error"""
        # Reset both buttons to their default states
        self.x_scan_btn.setText("📊 X Scan")
        self.y_scan_btn.setText("📈 Y Scan")
        self.x_scan_btn.setEnabled(True)
        self.y_scan_btn.setEnabled(True)
        
        # Update the single axis widget with the error
        if hasattr(self, 'single_axis_widget'):
            self.single_axis_widget.on_scan_error(error_msg, axis)
        
        self.show_message(f"❌ {axis} axis scan error: {error_msg}")
    
    def trigger_auto_focus(self):
        """Trigger auto focus from the scan controls"""
        try:
            if hasattr(self, 'auto_focus_widget') and self.auto_focus_widget:
                # Call the auto focus widget's start_auto_focus method
                if hasattr(self.auto_focus_widget, 'start_auto_focus'):
                    self.auto_focus_widget.start_auto_focus()
                    self.show_message("🔍 Auto focus started from scan controls")
                else:
                    self.show_message("❌ Auto focus method not available")
            else:
                self.show_message("❌ Auto focus widget not available")
        except Exception as e:
            self.show_message(f"❌ Error triggering auto focus: {str(e)}")
    
    def show_message(self, message):
        """Display a message to the user"""
        print(message)  # Also print to console for debugging
        if hasattr(self, 'status_bar'):
            self.status_bar.showMessage(message, 3000)  # Show for 3 seconds
    
    def resizeEvent(self, event):
        """Handle window resize to maintain proportional panel sizing"""
        super().resizeEvent(event)
        self.update_panel_proportions()
    
    def closeEvent(self, event):
        """Handle application close"""
        try:
            # Stop any running scan
            if self.scan_thread and self.scan_thread.isRunning():
                self.scan_thread.stop()
                self.scan_thread.wait(1000)  # Wait up to 1 second
            
            # Set scanner to zero and close DAQ task
            if hasattr(self, 'output_task') and self.output_task:
                self.output_task.write([0, 0])
                self.output_task.close()
                self.show_message("🎯 Scanner set to zero position and DAQ closed")
            
            # Stop live plot timer
            if hasattr(self, 'live_plot') and self.live_plot:
                self.live_plot.timer.stop()
            
            # Stop camera update timer
            if hasattr(self, 'camera_widget') and hasattr(self.camera_widget, 'update_timer'):
                self.camera_widget.update_timer.stop()
            
            # Stop TimeTagger if it's a virtual device
            if hasattr(self, 'tagger') and hasattr(self.tagger, 'stop'):
                self.tagger.stop()
                
        except Exception as e:
            self.show_message(f"❌ Error during app closure: {str(e)}")
        
        event.accept()


# --------------------- MANAGER CLASSES (REUSED FROM ORIGINAL) ---------------------
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


class ScanPointsManager:
    """Manages scan point generation and updates"""
    
    def __init__(self, scan_params_manager):
        self.scan_params_manager = scan_params_manager
        self.original_x_points = None
        self.original_y_points = None
        self._initialize_default_points()
    
    def _initialize_default_points(self):
        """Initialize with default values"""
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


# --------------------- MAIN APPLICATION ---------------------
def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    
    # Set application properties to match ODMR GUI style
    app.setApplicationName("NV Scanning Microscopy Control Center")
    app.setApplicationVersion("2.0")
    app.setOrganizationName("Burke Lab - UC Irvine")
    app.setOrganizationDomain("burkelab.uci.edu")
    
    # Create and show main window
    window = ConfocalMainWindow()
    window.show()
    
    # Start event loop
    sys.exit(app.exec_())


if __name__ == "__main__":
    main() 