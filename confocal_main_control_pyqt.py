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
    QLabel, QMessageBox, QDesktopWidget, QComboBox
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

class ScanParametersWidget(QWidget):
    """Pure PyQt scan parameters widget"""
    
    def __init__(self, scan_params_manager, parent=None):
        super().__init__(parent)
        self.scan_params_manager = scan_params_manager
        self.init_ui()
    
    def init_ui(self):
        layout = QGridLayout()
        
        # X Range
        layout.addWidget(QLabel("X Range (V):"), 0, 0)
        self.x_min_spin = pg.SpinBox(value=-1.0, bounds=(-10, 10), decimals=3, step=0.1)
        self.x_max_spin = pg.SpinBox(value=1.0, bounds=(-10, 10), decimals=3, step=0.1)
        layout.addWidget(self.x_min_spin, 0, 1)
        layout.addWidget(self.x_max_spin, 0, 2)
        
        # Y Range  
        layout.addWidget(QLabel("Y Range (V):"), 1, 0)
        self.y_min_spin = pg.SpinBox(value=-1.0, bounds=(-10, 10), decimals=3, step=0.1)
        self.y_max_spin = pg.SpinBox(value=1.0, bounds=(-10, 10), decimals=3, step=0.1)
        layout.addWidget(self.y_min_spin, 1, 1)
        layout.addWidget(self.y_max_spin, 1, 2)
        
        # Resolution
        layout.addWidget(QLabel("X Resolution:"), 2, 0)
        self.x_res_spin = pg.SpinBox(value=50, bounds=(1, 1000), int=True)
        layout.addWidget(self.x_res_spin, 2, 1, 1, 2)
        
        layout.addWidget(QLabel("Y Resolution:"), 3, 0)
        self.y_res_spin = pg.SpinBox(value=50, bounds=(1, 1000), int=True)
        layout.addWidget(self.y_res_spin, 3, 1, 1, 2)
        
        # Dwell Time
        layout.addWidget(QLabel("Dwell Time (s):"), 4, 0)
        self.dwell_spin = pg.SpinBox(value=0.002, bounds=(0.001, 1), decimals=4, step=0.001)
        layout.addWidget(self.dwell_spin, 4, 1, 1, 2)
        
        self.setLayout(layout)
    
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
    """PyQtGraph-based live plotting widget"""
    
    def __init__(self, measure_function, histogram_range=100, update_interval=200, parent=None):
        super().__init__(parent)
        self.measure_function = measure_function
        self.histogram_range = histogram_range
        
        # Setup plot widget with dark theme matching ODMR GUI
        self.plot_widget = pg.PlotWidget(title="Live Signal")
        self.plot_widget.setBackground('#262930')
        self.plot_widget.setLabel('left', 'Signal (counts/s)', color='white', size='12pt')
        self.plot_widget.setLabel('bottom', 'Time (s)', color='white', size='12pt')
        self.plot_widget.showGrid(True, alpha=0.3)
        
        # Style the plot to match ODMR GUI dark theme
        self.plot_widget.getAxis('left').setPen('white')
        self.plot_widget.getAxis('bottom').setPen('white')
        self.plot_widget.getAxis('left').setTextPen('white')
        self.plot_widget.getAxis('bottom').setTextPen('white')
        
        # Data storage
        self.x_data = []
        self.y_data = []
        self.t0 = time.time()
        
        # Plot curve with ODMR GUI green color
        self.curve = self.plot_widget.plot(pen=pg.mkPen('#00ff88', width=2))
        
        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.plot_widget)
        self.setLayout(layout)
        
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
    
    def closeEvent(self, event):
        """Clean up timer when widget is closed"""
        if hasattr(self, 'timer'):
            self.timer.stop()
        super().closeEvent(event)


class ScanThread(QThread):
    """Background thread for scanning operations"""
    
    update_image = pyqtSignal(np.ndarray)
    update_position = pyqtSignal(int, int, int, int)  # y_idx, x_idx, total_y, total_x
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
            image = np.zeros((height, width), dtype=np.float32)
            
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
                    
                    # Emit position update
                    self.update_position.emit(y_idx, x_idx, height, width)
                    
                    # Emit image update every 10 pixels
                    if (y_idx * width + x_idx) % 10 == 0:
                        self.update_image.emit(image.copy())
            
            if not self.stop_requested:
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
        """Initialize the user interface"""
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
        # Main layout: Top area + Bottom controls
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(5, 5, 5, 5)
        central_widget.setLayout(main_layout)
        
        # Top area: Left params + Center image + Right plots
        top_layout = QHBoxLayout()
        top_layout.setSpacing(10)
        
        # LEFT PANEL: Scan Parameters Only
        left_panel = QWidget()
        left_panel.setFixedWidth(300)
        left_layout = QVBoxLayout()
        left_layout.setSpacing(10)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_panel.setLayout(left_layout)
        
        # Scan parameters widget
        params_group = QGroupBox("Scan Parameters")
        params_layout = QVBoxLayout()
        self.scan_params_widget = ScanParametersWidget(self.scan_params_manager)
        params_layout.addWidget(self.scan_params_widget)
        params_group.setLayout(params_layout)
        left_layout.addWidget(params_group)
        left_layout.addStretch()
        
        top_layout.addWidget(left_panel)
        
        # CENTER PANEL: Main Image Display
        center_panel = QWidget()
        center_layout = QVBoxLayout()
        center_layout.setSpacing(5)
        center_layout.setContentsMargins(5, 5, 5, 5)
        center_panel.setLayout(center_layout)
        
        # Image controls (zoom and colormap) - compact horizontal layout
        image_controls_layout = QHBoxLayout()
        image_controls_layout.setSpacing(10)
        
        # Zoom controls
        self.zoom_toggle_btn = QPushButton("🔍 Enable Zoom")
        self.zoom_toggle_btn.clicked.connect(self.toggle_zoom_mode)
        self.zoom_toggle_btn.setFixedSize(120, 35)
        
        self.apply_zoom_btn = QPushButton("⚡ Apply Zoom")
        self.apply_zoom_btn.clicked.connect(self.apply_zoom)
        self.apply_zoom_btn.setEnabled(False)
        self.apply_zoom_btn.setFixedSize(120, 35)
        
        image_controls_layout.addWidget(self.zoom_toggle_btn)
        image_controls_layout.addWidget(self.apply_zoom_btn)
        
        # Colormap selection
        image_controls_layout.addWidget(QLabel("Colormap:"))
        self.colormap_combo = QComboBox()
        self.colormap_combo.setFixedWidth(150)
        image_controls_layout.addWidget(self.colormap_combo)
        
        image_controls_layout.addStretch()  # Push controls to left
        
        center_layout.addLayout(image_controls_layout)
        
        # Main image view
        self.image_view = pg.ImageView()
        self.image_view.ui.roiBtn.hide()  # Hide ROI button initially
        self.image_view.ui.menuBtn.hide()  # Hide menu button
        
        # Apply dark theme to image view
        view_widget = self.image_view.getView()
        view_widget.setBackgroundColor('#262930')
        
        # Set the ImageView widget background color to match theme
        self.image_view.setStyleSheet("background-color: #262930; border: none;")
        
        # Style the histogram widget if it exists
        if hasattr(self.image_view, 'ui') and hasattr(self.image_view.ui, 'histogram'):
            self.image_view.ui.histogram.setBackground('#262930')
        
        # Enable proper axes for the ImageView
        self.setup_image_axes()
        
        # Connect mouse events
        self.image_view.getImageItem().mouseClickEvent = self.on_image_click
        
        # Set up ROI for zoom selection
        self.zoom_roi = pg.RectROI([10, 10], [30, 30], pen='r')
        self.zoom_roi.sigRegionChanged.connect(self.on_roi_changed)
        self.image_view.getView().addItem(self.zoom_roi)
        self.zoom_roi.hide()  # Initially hidden
        
        # Add scale bar
        self.scale_bar = self.create_scale_bar()
        self.image_view.getView().addItem(self.scale_bar)
        
        center_layout.addWidget(self.image_view)
        
        top_layout.addWidget(center_panel, 1)  # Give center panel stretch factor
        
        # RIGHT PANEL: Plots Only
        right_panel = QWidget()
        right_panel.setFixedWidth(350)
        right_layout = QVBoxLayout()
        right_layout.setSpacing(10)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_panel.setLayout(right_layout)
        
        # Plots in tabs
        plots_group = QGroupBox("Analysis & Plots")
        plots_layout = QVBoxLayout()
        
        plot_tabs = QTabWidget()
        
        # Live plot tab
        self.live_plot = LivePlotWidget(
            measure_function=lambda: self.counter.getData()[0][0] / (self.binwidth / 1e12),
            histogram_range=100,
            update_interval=200
        )
        plot_tabs.addTab(self.live_plot, "Live Signal")
        
        # Single axis scan tab
        self.single_axis_widget = create_single_axis_scan_widget(
            self.scan_params_manager, self.output_task, self.counter, self.binwidth
        )
        plot_tabs.addTab(self.single_axis_widget, "Single Axis")
        
        # Auto focus tab
        self.auto_focus_widget = create_auto_focus_widget(self.counter, self.binwidth)
        plot_tabs.addTab(self.auto_focus_widget, "Auto Focus")
        
        plots_layout.addWidget(plot_tabs)
        plots_group.setLayout(plots_layout)
        right_layout.addWidget(plots_group)
        
        top_layout.addWidget(right_panel)
        
        # Add top layout to main layout
        main_layout.addLayout(top_layout, 1)  # Give top area stretch factor
        
        # BOTTOM PANEL: Scan Controls
        bottom_panel = QWidget()
        bottom_panel.setFixedHeight(120)
        bottom_layout = QVBoxLayout()
        bottom_layout.setSpacing(5)
        bottom_layout.setContentsMargins(10, 10, 10, 10)
        bottom_panel.setLayout(bottom_layout)
        
        # Scan controls in a horizontal layout
        controls_group = QGroupBox("Scan Controls")
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(15)
        
        # Create individual control buttons (replace ScanControlWidget)
        self.new_scan_btn = QPushButton("🔬 New Scan")
        self.new_scan_btn.clicked.connect(self.start_new_scan)
        self.new_scan_btn.setFixedSize(120, 50)
        
        self.stop_scan_btn = QPushButton("🛑 Stop Scan")
        self.stop_scan_btn.clicked.connect(self.stop_scan)
        self.stop_scan_btn.setFixedSize(120, 50)
        
        self.save_image_btn = QPushButton("📷 Save Image")
        self.save_image_btn.clicked.connect(self.save_image)
        self.save_image_btn.setFixedSize(120, 50)
        
        self.reset_zoom_btn = QPushButton("🔄 Reset Zoom")
        self.reset_zoom_btn.clicked.connect(self.reset_zoom)
        self.reset_zoom_btn.setFixedSize(120, 50)
        
        self.close_scanner_btn = QPushButton("🎯 Set to Zero")
        self.close_scanner_btn.clicked.connect(self.close_scanner)
        self.close_scanner_btn.setFixedSize(120, 50)
        
        self.load_scan_btn = QPushButton("📁 Load Scan")
        self.load_scan_btn.clicked.connect(self.load_scan)
        self.load_scan_btn.setFixedSize(120, 50)
        
        # Add buttons to layout
        controls_layout.addWidget(self.new_scan_btn)
        controls_layout.addWidget(self.stop_scan_btn)
        controls_layout.addWidget(self.save_image_btn)
        controls_layout.addWidget(self.reset_zoom_btn)
        controls_layout.addWidget(self.close_scanner_btn)
        controls_layout.addWidget(self.load_scan_btn)
        controls_layout.addStretch()
        
        controls_group.setLayout(controls_layout)
        bottom_layout.addWidget(controls_group)
        
        main_layout.addWidget(bottom_panel)
        
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
        self.image_view.setImage(self.current_image, 
                                autoLevels=True,
                                scale=(scale_x, scale_y),
                                pos=(x_start_um, y_start_um))
        
        # Update scan parameters manager
        self.scan_params_manager.set_widget_instance(self.scan_params_widget)
        self.scan_points_manager._update_points_from_params()
        
        # Update scale bar and coordinate labels for initial display
        self.update_scale_bar()
        self.update_coordinate_labels()
    
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
    
    def setup_image_axes(self):
        """Set up proper X and Y axes for the ImageView"""
        try:
            # Access the ImageView's internal structure to enable axes
            # ImageView contains a PlotItem that we can access
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
            # Get the position in the image view coordinates (now in micrometers)
            pos = self.image_view.getView().mapToView(event.pos())
            x_um = pos.x()
            y_um = pos.y()
            
            # Convert from micrometers back to voltage
            from utils import MICRONS_PER_VOLT
            x_voltage = x_um / MICRONS_PER_VOLT
            y_voltage = y_um / MICRONS_PER_VOLT
            
            try:
                if self.output_task:
                    self.output_task.write([x_voltage, y_voltage])
                    self.show_message(f"Moved scanner to: X={x_voltage:.3f}V ({x_um:.1f}μm), Y={y_voltage:.3f}V ({y_um:.1f}μm)")
                    
                    # Update single axis scan widget position tracking
                    if hasattr(self, 'single_axis_widget'):
                        self.single_axis_widget.update_current_position(x_voltage, y_voltage)
                else:
                    self.show_message("❌ DAQ not initialized - cannot move scanner")
                
            except Exception as e:
                self.show_message(f"Error moving scanner: {str(e)}")
    
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
        
        # Get ROI bounds
        roi_pos = self.zoom_roi.pos()
        roi_size = self.zoom_roi.size()
        
        # Convert to image coordinates
        min_x = int(roi_pos[0])
        min_y = int(roi_pos[1])
        max_x = int(roi_pos[0] + roi_size[0])
        max_y = int(roi_pos[1] + roi_size[1])
        
        # Ensure bounds are within image
        if self.current_image is not None:
            height, width = self.current_image.shape
            min_x = max(0, min(min_x, width-1))
            max_x = max(min_x+1, min(max_x, width))
            min_y = max(0, min(min_y, height-1))
            max_y = max(min_y+1, min(max_y, height))
        
        # Save current state for zoom history
        current_x_points, current_y_points = self.scan_points_manager.get_points()
        self.scan_history.append((current_x_points.copy(), current_y_points.copy()))
        
        # Calculate new scan region
        current_params = self.scan_params_manager.get_params()
        current_x_res = current_params['resolution']['x']
        current_y_res = current_params['resolution']['y']
        
        # Map pixel coordinates to voltage coordinates
        x_range = current_params['scan_range']['x']
        y_range = current_params['scan_range']['y']
        
        new_x_min = np.interp(min_x, [0, current_x_res-1], x_range)
        new_x_max = np.interp(max_x-1, [0, current_x_res-1], x_range)
        new_y_min = np.interp(min_y, [0, current_y_res-1], y_range)
        new_y_max = np.interp(max_y-1, [0, current_y_res-1], y_range)
        
        # Update parameters
        self.scan_params_manager.update_scan_parameters(
            x_range=[new_x_min, new_x_max],
            y_range=[new_y_min, new_y_max]
        )
        
        # Update widget display
        self.scan_params_widget.update_values(
            [new_x_min, new_x_max], [new_y_min, new_y_max],
            current_x_res, current_y_res,
            current_params['dwell_time']
        )
        
        # Update scan points
        self.scan_points_manager._update_points_from_params()
        
        # Update zoom level
        self.zoom_manager.set_zoom_level(self.zoom_manager.get_zoom_level() + 1)
        
        # Hide ROI
        self.zoom_roi.hide()
        self.zoom_toggle_btn.setText("🔍 Enable Zoom")
        self.apply_zoom_btn.setEnabled(False)
        
        self.show_message(f"🔍 Zoomed to region: X={new_x_min:.3f}-{new_x_max:.3f}V, Y={new_y_min:.3f}-{new_y_max:.3f}V")
        
        # Update scale bar and coordinate labels for new zoom level
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
        self.scan_thread.scan_complete.connect(self.on_scan_complete)
        self.scan_thread.error_occurred.connect(self.on_scan_error)
        
        self.scan_thread.start()
        self.show_message("🔬 New scan started")
    
    def stop_scan(self):
        """Stop the current scan"""
        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.stop()
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
                self.image_view.setImage(image, autoLevels=True)
                
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
        self.image_view.setImage(image, 
                                autoLevels=True,
                                scale=(scale_x, scale_y),
                                pos=(x_start_um, y_start_um))
        
        # Reapply current colormap to ensure it's maintained
        if hasattr(self, 'current_colormap'):
            self.apply_colormap(self.current_colormap)
        
        # Update scale bar and coordinate labels
        self.update_scale_bar()
        self.update_coordinate_labels()
    
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
        self.image_view.setImage(image, 
                                autoLevels=True,
                                scale=(scale_x, scale_y),
                                pos=(x_start_um, y_start_um))
        
        # Reapply current colormap to ensure it's maintained
        if hasattr(self, 'current_colormap'):
            self.apply_colormap(self.current_colormap)
        
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
        
        self.show_message("✅ Scan completed and data saved")
    
    def on_scan_error(self, error_msg):
        """Handle scan errors"""
        self.show_message(f"❌ Scan error: {error_msg}")
    
    def show_message(self, message):
        """Display a message to the user"""
        print(message)  # Also print to console for debugging
        if hasattr(self, 'status_bar'):
            self.status_bar.showMessage(message, 3000)  # Show for 3 seconds
    
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