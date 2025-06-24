"""
Confocal Single-NV Microscopy Control Software (Qt-based GUI)
-------------------------------------------
This software controls a confocal microscope setup for single NV center imaging using:
- Thorlabs LSKGG4 Galvo-Galvo Scanner
- National Instruments USB-6453 DAQ
- Single Photon Detector SPD

The system provides real-time visualization and control through a Qt-based GUI.
"""

# Standard library imports
import json
import threading
import time
import sys
import os

# Third-party imports
import numpy as np
import nidaqmx
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QGridLayout, QSplitter, QLabel, QStatusBar, QDesktopWidget,
                            QScrollArea, QFrame, QSizePolicy)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread
from PyQt5.QtGui import QPixmap, QImage, QPainter, QPen, QColor
import pyqtgraph as pg
from pyqtgraph import ImageView, PlotWidget, mkPen, mkBrush
from TimeTagger import createTimeTagger, Counter, createTimeTaggerVirtual

# Local imports
from galvo_controller import GalvoScannerController
from data_manager import DataManager
from plot_scan_results import plot_scan_results
from utils import calculate_scale, MICRONS_PER_VOLT

# Import extracted widgets
from widgets.scan_controls import (
    new_scan as create_new_scan,
    close_scanner as create_close_scanner,
    save_image as create_save_image,
    reset_zoom as create_reset_zoom,
    update_scan_parameters as create_update_scan_parameters,
    update_scan_parameters_widget as create_update_scan_parameters_widget
)
from widgets.camera_controls import (
    create_camera_control_widget
)
from widgets.auto_focus import (
    auto_focus as create_auto_focus,
    SignalBridge
)
from widgets.single_axis_scan import SingleAxisScanWidget
from widgets.file_operations import load_scan as create_load_scan, open_odmr_gui as create_odmr_gui

# --------------------- CONFIGURATION MANAGER CLASS ---------------------
class ConfigManager:
    """Manages configuration loading, saving, and updates"""
    
    def __init__(self, config_file="config_template.json"):
        self.config_file = config_file
        self.config = self._load_config()
    
    def _load_config(self):
        with open(self.config_file, 'r') as f:
            return json.load(f)
    
    def get_config(self):
        return self.config
    
    def update_scan_parameters(self, x_range=None, y_range=None, x_res=None, y_res=None):
        if x_range is not None:
            self.config['scan_range']['x'] = x_range
        if y_range is not None:
            self.config['scan_range']['y'] = y_range
        if x_res is not None:
            self.config['resolution']['x'] = x_res
        if y_res is not None:
            self.config['resolution']['y'] = y_res
        
        self._save_config()
    
    def _save_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=4)

# --------------------- SCAN POINTS MANAGER CLASS ---------------------
class ScanPointsManager:
    """Manages scan point generation and updates"""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.original_x_points = None
        self.original_y_points = None
        self._update_points_from_config()
    
    def _update_points_from_config(self):
        config = self.config_manager.get_config()
        x_range = config['scan_range']['x']
        y_range = config['scan_range']['y']
        x_res = config['resolution']['x']
        y_res = config['resolution']['y']
        
        self.original_x_points = np.linspace(x_range[0], x_range[1], x_res)
        self.original_y_points = np.linspace(y_range[0], y_range[1], y_res)
    
    def update_points(self, x_range=None, y_range=None, x_res=None, y_res=None):
        if x_range is not None and x_res is not None:
            self.original_x_points = np.linspace(x_range[0], x_range[1], x_res)
        if y_range is not None and y_res is not None:
            self.original_y_points = np.linspace(y_range[0], y_range[1], y_res)
    
    def get_points(self):
        return self.original_x_points, self.original_y_points

# --------------------- ZOOM LEVEL MANAGER CLASS ---------------------
class ZoomLevelManager:
    """Manages zoom level state"""
    
    def __init__(self, max_zoom=3):
        self.zoom_level = 0
        self.max_zoom = max_zoom
    
    def get_zoom_level(self):
        return self.zoom_level
    
    def set_zoom_level(self, level):
        self.zoom_level = level
    
    def can_zoom_in(self):
        return self.zoom_level < self.max_zoom

# --------------------- QT SIGNAL BRIDGE ---------------------
class QtSignalBridge(QObject):
    """Qt signal bridge for thread-safe GUI updates"""
    status_update = pyqtSignal(str)

# --------------------- PYQTGRAPH IMAGE DISPLAY WIDGET ---------------------
class ImageDisplayWidget(QWidget):
    """PyQtGraph-based widget for displaying the scan image with mouse interaction and colorbar"""
    
    mouse_clicked = pyqtSignal(int, int)
    zoom_region_selected = pyqtSignal(int, int, int, int)
    
    def __init__(self):
        super().__init__()
        self.setMinimumSize(600, 600)
        
        # Set PyQtGraph global options for dark theme
        pg.setConfigOption('background', '#262930')
        pg.setConfigOption('foreground', 'w')
        
        # Create layout
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Add title label
        title_label = QLabel("Live Scan Image")
        title_label.setStyleSheet("color: white; font-size: 14px; font-weight: bold; padding: 5px;")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # Create a horizontal layout for plot and colorbar
        plot_layout = QHBoxLayout()
        plot_widget_container = QWidget()
        plot_widget_container.setLayout(plot_layout)
        layout.addWidget(plot_widget_container)
        
        # Create PlotWidget for the image
        self.plot_widget = PlotWidget()
        self.plot_widget.setBackground('#262930')
        self.plot_widget.setLabel('left', 'Y Position', 'µm')
        self.plot_widget.setLabel('bottom', 'X Position', 'µm')
        self.plot_widget.showGrid(x=False, y=False)
        self.plot_widget.setAspectLocked(True)
        
        # Style the plot
        self.plot_widget.getAxis('left').setPen('w')
        self.plot_widget.getAxis('bottom').setPen('w')
        self.plot_widget.getAxis('left').setTextPen('w')
        self.plot_widget.getAxis('bottom').setTextPen('w')
        
        plot_layout.addWidget(self.plot_widget)
        
        # Create ImageItem for displaying the image
        self.image_item = pg.ImageItem()
        self.plot_widget.addItem(self.image_item)
        
        # Create colorbar (histogram widget)
        self.histogram = pg.HistogramLUTWidget()
        self.histogram.setImageItem(self.image_item)
        
        # Set viridis colormap
        self.histogram.gradient.restoreState({
            'mode': 'rgb',
            'ticks': [(0.0, (68, 1, 84, 255)), (0.25, (59, 82, 139, 255)), 
                     (0.5, (33, 145, 140, 255)), (0.75, (94, 201, 98, 255)), 
                     (1.0, (253, 231, 37, 255))]  # Viridis colormap
        })
        
        plot_layout.addWidget(self.histogram)
        
        # Image data and display objects
        self.image_data = None
        self.scanner_item = None
        self.zoom_rect = None
        
        # Scanner position
        self.scanner_x = None
        self.scanner_y = None
        
        # Zoom selection
        self.zoom_start = None
        self.zoom_end = None
        self.selecting_zoom = False
        
        # Scale information
        self.x_points = None
        self.y_points = None
        self.x_scale = 1.0
        self.y_scale = 1.0
        self.x_offset = 0.0
        self.y_offset = 0.0
        
        # Connect mouse events
        self.plot_widget.scene().sigMouseClicked.connect(self.on_mouse_click)
        
        # Get the view box for additional mouse events
        self.view_box = self.plot_widget.getViewBox()
        self.view_box.setMouseEnabled(x=True, y=True)  # Enable mouse interaction
        
        # Initialize empty image
        self._create_empty_image()
    
    def _create_empty_image(self):
        """Create an empty image for initialization"""
        empty_data = np.zeros((10, 10))
        self.image_item.setImage(empty_data)
    
    def set_image(self, image_data, x_points=None, y_points=None, scale_x=1.0, scale_y=1.0):
        """Update the displayed image"""
        self.image_data = image_data
        
        if image_data is None or image_data.size == 0:
            return
        
        # Store scale information
        if x_points is not None and y_points is not None:
            self.x_points = x_points
            self.y_points = y_points
            
            # Convert voltage to micrometers
            x_um = np.array(x_points) * MICRONS_PER_VOLT
            y_um = np.array(y_points) * MICRONS_PER_VOLT
            
            # Calculate scale and offset for proper positioning
            self.x_scale = (x_um[-1] - x_um[0]) / (len(x_um) - 1) if len(x_um) > 1 else 1.0
            self.y_scale = (y_um[-1] - y_um[0]) / (len(y_um) - 1) if len(y_um) > 1 else 1.0
            self.x_offset = x_um[0]
            self.y_offset = y_um[0]
            
            # Set image with proper scaling
            self.image_item.setImage(image_data)
            
            # Set proper positioning and scaling
            self.image_item.setRect(pg.QtCore.QRectF(x_um[0], y_um[0], x_um[-1] - x_um[0], y_um[-1] - y_um[0]))
            
            # Set axis ranges
            self.view_box.setRange(
                xRange=[x_um[0], x_um[-1]], 
                yRange=[y_um[0], y_um[-1]], 
                padding=0
            )
        else:
            # Fallback to pixel coordinates
            self.x_scale = 1.0
            self.y_scale = 1.0
            self.x_offset = 0.0
            self.y_offset = 0.0
            self.image_item.setImage(image_data)
    
    def set_contrast(self, min_val, max_val):
        """Update contrast limits"""
        if self.image_data is not None:
            self.histogram.setLevels(min_val, max_val)
    
    def set_scanner_position(self, x_idx, y_idx):
        """Update scanner position indicator"""
        self.scanner_x = x_idx
        self.scanner_y = y_idx
        
        if self.image_data is None:
            return
        
        # Convert pixel coordinates to real coordinates
        if self.x_points is not None and self.y_points is not None:
            height, width = self.image_data.shape
            x_idx = max(0, min(x_idx, width - 1))
            y_idx = max(0, min(y_idx, height - 1))
            
            x_um = np.array(self.x_points) * MICRONS_PER_VOLT
            y_um = np.array(self.y_points) * MICRONS_PER_VOLT
            
            x_pos = np.interp(x_idx, [0, width-1], [x_um[0], x_um[-1]])
            y_pos = np.interp(y_idx, [0, height-1], [y_um[0], y_um[-1]])
        else:
            x_pos, y_pos = x_idx, y_idx
        
        # Remove old scanner position marker
        if self.scanner_item is not None:
            self.plot_widget.removeItem(self.scanner_item)
        
        # Add new scanner position marker (crosshair)
        self.scanner_item = pg.ScatterPlotItem(
            pos=[[x_pos, y_pos]], 
            symbol='+', 
            size=20, 
            pen=mkPen('r', width=3),
            brush=mkBrush(None)
        )
        self.plot_widget.addItem(self.scanner_item)
    
    def on_mouse_click(self, event):
        """Handle mouse click events"""
        if event.button() == Qt.LeftButton:
            # Get mouse position in plot coordinates
            pos = self.view_box.mapSceneToView(event.scenePos())
            self._handle_left_click(pos.x(), pos.y())
        elif event.button() == Qt.RightButton:
            # Start zoom selection
            pos = self.view_box.mapSceneToView(event.scenePos())
            self.zoom_start = (pos.x(), pos.y())
            self.selecting_zoom = True
            
    def on_mouse_release(self, event):
        """Handle mouse release events"""
        if event.button() == Qt.RightButton and self.selecting_zoom and self.zoom_start:
            pos = self.view_box.mapSceneToView(event.scenePos())
            self.zoom_end = (pos.x(), pos.y())
            self._handle_zoom_selection()
            
            # Clean up
            if self.zoom_rect is not None:
                self.plot_widget.removeItem(self.zoom_rect)
                self.zoom_rect = None
            self.selecting_zoom = False
            self.zoom_start = None
            self.zoom_end = None
    
    def on_mouse_move(self, event):
        """Handle mouse motion for zoom rectangle visualization"""
        if self.selecting_zoom and self.zoom_start:
            pos = self.view_box.mapSceneToView(event.scenePos())
            
            # Remove old rectangle
            if self.zoom_rect is not None:
                self.plot_widget.removeItem(self.zoom_rect)
            
            # Draw new rectangle
            x1, y1 = self.zoom_start
            x2, y2 = pos.x(), pos.y()
            
            rect = pg.QtCore.QRectF(x1, y1, x2-x1, y2-y1)
            self.zoom_rect = pg.QtGui.QGraphicsRectItem(rect)
            self.zoom_rect.setPen(mkPen('r', width=2))
            self.plot_widget.addItem(self.zoom_rect)
    
    def _handle_left_click(self, x_real, y_real):
        """Handle left mouse click for scanner positioning"""
        if self.image_data is None:
            return
        
        # Convert real coordinates to pixel coordinates
        if self.x_points is not None and self.y_points is not None:
            x_um = np.array(self.x_points) * MICRONS_PER_VOLT
            y_um = np.array(self.y_points) * MICRONS_PER_VOLT
            
            height, width = self.image_data.shape
            x_idx = int(np.interp(x_real, [x_um[0], x_um[-1]], [0, width-1]))
            y_idx = int(np.interp(y_real, [y_um[0], y_um[-1]], [0, height-1]))
        else:
            x_idx, y_idx = int(x_real), int(y_real)
        
        # Ensure coordinates are within bounds
        if self.image_data is not None:
            height, width = self.image_data.shape
            x_idx = max(0, min(x_idx, width-1))
            y_idx = max(0, min(y_idx, height-1))
        
        self.mouse_clicked.emit(x_idx, y_idx)
    
    def _handle_zoom_selection(self):
        """Handle zoom region selection"""
        if not self.zoom_start or not self.zoom_end or self.image_data is None:
            return
        
        x1, y1 = self.zoom_start
        x2, y2 = self.zoom_end
        
        # Convert real coordinates to pixel coordinates
        if self.x_points is not None and self.y_points is not None:
            x_um = np.array(self.x_points) * MICRONS_PER_VOLT
            y_um = np.array(self.y_points) * MICRONS_PER_VOLT
            
            height, width = self.image_data.shape
            x1_idx = int(np.interp(x1, [x_um[0], x_um[-1]], [0, width-1]))
            y1_idx = int(np.interp(y1, [y_um[0], y_um[-1]], [0, height-1]))
            x2_idx = int(np.interp(x2, [x_um[0], x_um[-1]], [0, width-1]))
            y2_idx = int(np.interp(y2, [y_um[0], y_um[-1]], [0, height-1]))
        else:
            x1_idx, y1_idx = int(x1), int(y1)
            x2_idx, y2_idx = int(x2), int(y2)
        
        # Ensure proper ordering and bounds
        min_x = max(0, min(x1_idx, x2_idx))
        max_x = min(self.image_data.shape[1]-1, max(x1_idx, x2_idx))
        min_y = max(0, min(y1_idx, y2_idx))
        max_y = min(self.image_data.shape[0]-1, max(y1_idx, y2_idx))
        
        if abs(max_x - min_x) > 2 and abs(max_y - min_y) > 2:  # Minimum zoom size
            self.zoom_region_selected.emit(min_x, min_y, max_x, max_y)
    


# --------------------- LIVE SIGNAL PLOT WIDGET ---------------------
class LiveSignalPlotWidget(QWidget):
    """PyQtGraph widget for displaying live signal data"""
    
    def __init__(self, measure_function, histogram_range=100, dt=0.2):
        super().__init__()
        self.measure_function = measure_function
        self.histogram_range = histogram_range
        self.dt = dt
        
        # Create layout
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Add title label
        title_label = QLabel("Live Signal")
        title_label.setStyleSheet("color: white; font-size: 14px; font-weight: bold; padding: 5px;")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # Create PlotWidget
        self.plot_widget = PlotWidget()
        self.plot_widget.setBackground('#262930')
        self.plot_widget.setLabel('left', 'Counts/s', color='white')
        self.plot_widget.setLabel('bottom', 'Time', 's', color='white')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        
        # Style the plot
        self.plot_widget.getAxis('left').setPen('w')
        self.plot_widget.getAxis('bottom').setPen('w')
        self.plot_widget.getAxis('left').setTextPen('w')
        self.plot_widget.getAxis('bottom').setTextPen('w')
        
        layout.addWidget(self.plot_widget)
        
        # Create plot line
        self.curve = self.plot_widget.plot(pen=mkPen(color='#00d4aa', width=2))
        
        # Data storage
        self.times = []
        self.values = []
        
        # Timer for updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(int(dt * 1000))  # Convert to milliseconds
        
    def update_plot(self):
        """Update the live plot with new data"""
        try:
            current_time = time.time()
            if not hasattr(self, 'start_time'):
                self.start_time = current_time
            
            relative_time = current_time - self.start_time
            new_value = self.measure_function()
            
            self.times.append(relative_time)
            self.values.append(new_value)
            
            # Keep only recent data
            if len(self.times) > self.histogram_range:
                self.times = self.times[-self.histogram_range:]
                self.values = self.values[-self.histogram_range:]
            
            # Update plot
            self.curve.setData(self.times, self.values)
            
        except Exception as e:
            print(f"Error updating live plot: {e}")

# --------------------- MAIN APPLICATION WINDOW ---------------------
class ConfocalMainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NV Scanning Microscopy")
        
        # Initialize managers and state
        self.init_managers()
        self.init_ui()
        self.init_hardware()
        self.init_widgets()
        
        # Show maximized
        self.showMaximized()
        
    def init_managers(self):
        """Initialize configuration and state managers"""
        self.config_manager = ConfigManager()
        self.scan_points_manager = ScanPointsManager(self.config_manager)
        self.zoom_manager = ZoomLevelManager()
        self.data_manager = DataManager()
        
        # Global state
        self.contrast_limits = (0, 10000)
        self.scan_history = []
        self.data_path = None
        self.zoom_in_progress = False
        
        # Extract scan parameters from config
        config = self.config_manager.get_config()
        self.x_res = config['resolution']['x']
        self.y_res = config['resolution']['y']
        
        # Initialize image
        self.image = np.zeros((self.y_res, self.x_res), dtype=np.float32)
        
        # Current scan points for display
        self.current_x_points = None
        self.current_y_points = None
        
        # Signal bridge
        self.signal_bridge = QtSignalBridge()
        self.signal_bridge.status_update.connect(self.show_status)
    
    def init_hardware(self):
        """Initialize hardware controllers"""
        # Galvo controller
        self.galvo_controller = GalvoScannerController()
        
        # DAQ setup
        self.output_task = nidaqmx.Task("Scanner_Control_Task")
        self.output_task.ao_channels.add_ao_voltage_chan(self.galvo_controller.xin_control)
        self.output_task.ao_channels.add_ao_voltage_chan(self.galvo_controller.yin_control)
        self.output_task.start()
        
        # TimeTagger setup
        try:
            self.tagger = createTimeTagger()
            self.tagger.reset()
            print("✅ Connected to real TimeTagger device")
        except Exception as e:
            print("⚠️ Real TimeTagger not detected, using virtual device")
            self.tagger = createTimeTaggerVirtual("TimeTagger/time_tags_test.ttbin")
            self.tagger.run()
        
        # Set bin width to 5 ns
        self.binwidth = int(5e9)
        n_values = 1
        self.counter = Counter(self.tagger, [1], self.binwidth, n_values)
    
    def init_ui(self):
        """Initialize the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Apply dark theme style (napari-inspired)
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
                font-weight: bold;
                font-size: 10pt;
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
            QSplitter::handle {
                background-color: #555555;
            }
        """)

        # Create main layout
        main_layout = QHBoxLayout(central_widget)
        
        # Create splitter for main areas
        main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(main_splitter)
        
        # Left panel for controls
        left_panel = self.create_left_panel()
        main_splitter.addWidget(left_panel)
        
        # Center panel for image display
        center_panel = self.create_center_panel()
        main_splitter.addWidget(center_panel)
        
        # Right panel for plots and additional controls
        right_panel = self.create_right_panel()
        main_splitter.addWidget(right_panel)
        
        # Set splitter ratios
        main_splitter.setSizes([300, 600, 400])
        
        # Status bar
        self.statusBar().showMessage("Ready")
    
    def create_left_panel(self):
        """Create the left control panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Title
        title = QLabel("Scan Controls")
        title.setStyleSheet("font-size: 14px; font-weight: bold; padding: 5px;")
        layout.addWidget(title)
        
        # Container for control widgets
        self.left_controls_layout = QVBoxLayout()
        layout.addLayout(self.left_controls_layout)
        
        # Stretch to push controls to top
        layout.addStretch()
        
        return panel
    
    def create_center_panel(self):
        """Create the center image display panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Title
        title = QLabel("Live Scan Image")
        title.setStyleSheet("font-size: 14px; font-weight: bold; padding: 5px;")
        layout.addWidget(title)
        
        # Image display
        self.image_display = ImageDisplayWidget()
        self.image_display.mouse_clicked.connect(self.on_mouse_click)
        self.image_display.zoom_region_selected.connect(self.on_zoom_region_selected)
        layout.addWidget(self.image_display)
        
        return panel
    
    def create_right_panel(self):
        """Create the right panel for plots and additional controls"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Live signal plot
        signal_title = QLabel("Live Signal")
        signal_title.setStyleSheet("font-size: 14px; font-weight: bold; padding: 5px;")
        layout.addWidget(signal_title)
        
        self.live_plot = LiveSignalPlotWidget(
            measure_function=lambda: self.counter.getData()[0][0]/(self.binwidth/1e12),
            histogram_range=100,
            dt=0.2
        )
        layout.addWidget(self.live_plot)
        
        # Container for right controls
        controls_title = QLabel("Additional Controls")
        controls_title.setStyleSheet("font-size: 14px; font-weight: bold; padding: 5px;")
        layout.addWidget(controls_title)
        
        self.right_controls_layout = QVBoxLayout()
        layout.addLayout(self.right_controls_layout)
        
        # Stretch
        layout.addStretch()
        
        return panel
    
    def init_widgets(self):
        """Initialize and add all control widgets"""
        # Create scan control widgets
        self.new_scan_widget = create_new_scan(self.scan_pattern, self.scan_points_manager, None)
        self.close_scanner_widget = create_close_scanner(self.output_task, None)
        self.save_image_widget = create_save_image(self, self.get_data_path)
        self.update_scan_parameters_widget = create_update_scan_parameters(self.config_manager, self.scan_points_manager)
        self.update_widget_func = create_update_scan_parameters_widget(self.update_scan_parameters_widget, self.config_manager)
        
        self.reset_zoom_widget = create_reset_zoom(
            self.scan_pattern, self.scan_history, self.config_manager, self.scan_points_manager,
            None, lambda **kwargs: self.config_manager.update_scan_parameters(**kwargs), 
            self.update_widget_func,
            self.zoom_manager
        )
        
        # Create other widgets
        self.camera_control_widget = create_camera_control_widget(self)
        
        # Auto-focus with Qt signal bridge
        qt_signal_bridge = SignalBridge(self)
        self.auto_focus_widget = create_auto_focus(self.counter, self.binwidth, qt_signal_bridge)
        
        self.single_axis_scan_widget = SingleAxisScanWidget(
            self.config_manager, None, None, self.output_task, self.counter, self.binwidth
        )
        
        # File operation widgets
        self.load_scan_widget = create_load_scan(self)
        self.odmr_gui_widget = create_odmr_gui()
        
        # Add widgets to panels
        self.add_widgets_to_panels()
    
    def add_widgets_to_panels(self):
        """Add widgets to their respective panels"""
        # Left panel widgets
        left_widgets = [
            ("New Scan", self.new_scan_widget),
            ("Save Image", self.save_image_widget),
            ("Reset Zoom", self.reset_zoom_widget),
            ("Close Scanner", self.close_scanner_widget),
            ("Auto Focus", self.auto_focus_widget),
            ("Load Scan", self.load_scan_widget),
            ("ODMR GUI", self.odmr_gui_widget),
            ("Scan Parameters", self.update_scan_parameters_widget)
        ]
        
        for name, widget in left_widgets:
            if hasattr(widget, 'native'):
                qt_widget = widget.native
            else:
                qt_widget = widget
            
            # Set fixed size for buttons
            if name != "Scan Parameters":
                qt_widget.setFixedSize(150, 50)
            
            frame = QFrame()
            frame.setFrameStyle(QFrame.Box)
            frame_layout = QVBoxLayout(frame)
            frame_layout.addWidget(QLabel(name))
            frame_layout.addWidget(qt_widget)
            
            self.left_controls_layout.addWidget(frame)
        
        # Right panel widgets
        right_widgets = [
            ("Camera Control", self.camera_control_widget),
            ("Single Axis Scan", self.single_axis_scan_widget)
        ]
        
        for name, widget in right_widgets:
            if hasattr(widget, 'native'):
                qt_widget = widget.native
            else:
                qt_widget = widget
            
            frame = QFrame()
            frame.setFrameStyle(QFrame.Box)
            frame_layout = QVBoxLayout(frame)
            frame_layout.addWidget(QLabel(name))
            frame_layout.addWidget(qt_widget)
            
            self.right_controls_layout.addWidget(frame)
    
    def scan_pattern(self, x_points, y_points):
        """Perform a raster scan pattern using the galvo mirrors and collect APD counts."""
        height, width = len(y_points), len(x_points)
        self.image = np.zeros((height, width), dtype=np.float32)
        
        # Store current scan points for image display
        self.current_x_points = x_points
        self.current_y_points = y_points
        
        # Initialize image display with proper scaling
        self.image_display.set_image(self.image, x_points, y_points)
        
        for y_idx, y in enumerate(y_points):
            for x_idx, x in enumerate(x_points):
                self.output_task.write([x, y])
                if x_idx == 0:
                    time.sleep(0.05)
                else:
                    time.sleep(0.001)
                    
                counts = self.counter.getData()[0][0]/(self.binwidth/1e12)
                print(f"{counts}")
                self.image[x_idx, y_idx] = counts
                
                # Update display with live data and scaling info
                self.image_display.set_image(self.image, x_points, y_points)
        
        # Adjust contrast and save data
        try:
            if self.image.size == 0 or np.all(np.isnan(self.image)):
                self.show_status('⚠️ Image is empty or contains only NaNs. Contrast not updated.')
            else:
                min_val = np.nanmin(self.image)
                max_val = np.nanmax(self.image)
                if np.isclose(min_val, max_val):
                    self.show_status('⚠️ Image min and max are equal. Contrast not updated.')
                else:
                    self.image_display.set_contrast(min_val, max_val)
        except Exception as e:
            self.show_status(f'❌ Error setting contrast limits: {str(e)}')
        
        # Calculate and set scale
        scale_um_per_px_x = calculate_scale(x_points[0], x_points[-1], width)
        scale_um_per_px_y = calculate_scale(y_points[0], y_points[-1], height)
        
        # Create scan data and save
        scan_data = {
            'image': self.image,
            'x_points': x_points,
            'y_points': y_points,
            'scale_x': scale_um_per_px_x,
            'scale_y': scale_um_per_px_y
        }
        self.data_path = self.data_manager.save_scan_data(scan_data)
        plot_scan_results(scan_data, self.data_path)
        
        # Save image with scale information
        np.savez(self.data_path.replace('.csv', '.npz'), 
                 image=self.image,
                 scale_x=scale_um_per_px_x,
                 scale_y=scale_um_per_px_y)
        
        # Return scanner to zero position after scan
        self.output_task.write([0, 0])
        self.show_status("🎯 Scanner returned to zero position")
        return x_points, y_points
    
    def on_mouse_click(self, x_idx, y_idx):
        """Handle mouse click events to move the galvo scanner to the clicked position."""
        # Get current ranges from config manager
        config = self.config_manager.get_config()
        x_range = config['scan_range']['x']
        y_range = config['scan_range']['y']
        x_res = config['resolution']['x']
        y_res = config['resolution']['y']
        
        # Convert from pixel coordinates to voltage values
        x_voltage = np.interp(x_idx, [0, x_res-1], [x_range[0], x_range[1]])
        y_voltage = np.interp(y_idx, [0, y_res-1], [y_range[0], y_range[1]])
        
        try:
            self.output_task.write([x_voltage, y_voltage])
            self.show_status(f"Moved scanner to: X={x_voltage:.3f}V, Y={y_voltage:.3f}V")
            
            # Update scanner position indicator
            self.image_display.set_scanner_position(x_idx, y_idx)
            
        except Exception as e:
            self.show_status(f"Error moving scanner: {str(e)}")
    
    def on_zoom_region_selected(self, min_x, min_y, max_x, max_y):
        """Handle zoom region selection"""
        if self.zoom_in_progress:
            return
        
        if not self.zoom_manager.can_zoom_in():
            self.show_status(f"⚠️ Max zoom reached ({self.zoom_manager.max_zoom} levels).")
            return
        
        # Ensure zoom region stays within image bounds
        height, width = self.image.shape
        min_x = max(0, min_x)
        max_x = min(width, max_x)
        min_y = max(0, min_y)
        max_y = min(height, max_y)
        
        # Save current state for zoom history
        current_x_points, current_y_points = self.scan_points_manager.get_points()
        self.scan_history.append((current_x_points, current_y_points))
        
        # Calculate new scan points maintaining original resolution
        current_config = self.config_manager.get_config()
        current_x_res = current_config['resolution']['x']
        current_y_res = current_config['resolution']['y']
        x_zoom = np.linspace(current_x_points[min_x], current_x_points[max_x - 1], current_x_res)
        y_zoom = np.linspace(current_y_points[min_y], current_y_points[max_y - 1], current_y_res)
        
        def run_zoom():
            self.zoom_in_progress = True
            
            self.config_manager.update_scan_parameters(
                x_range=[x_zoom[0], x_zoom[-1]],
                y_range=[y_zoom[0], y_zoom[-1]],
                x_res=current_x_res,
                y_res=current_y_res
            )
            self.scan_points_manager.update_points(
                x_range=[x_zoom[0], x_zoom[-1]],
                y_range=[y_zoom[0], y_zoom[-1]],
                x_res=current_x_res,
                y_res=current_y_res
            )
            
            self.scan_pattern(x_zoom, y_zoom)
            self.zoom_manager.set_zoom_level(self.zoom_manager.get_zoom_level() + 1)
            self.update_widget_func()
            self.zoom_in_progress = False
        
        threading.Thread(target=run_zoom, daemon=True).start()
    
    def get_data_path(self):
        """Helper function to get current data path"""
        return self.data_path
    
    def show_status(self, message):
        """Show status message"""
        self.statusBar().showMessage(message)
        print(message)  # Also print to console
    

    
    def closeEvent(self, event):
        """Handle application close event"""
        try:
            # Set scanner to zero position before closing
            self.output_task.write([0, 0])
            self.show_status("🎯 Scanner set to zero position")
            
            # Close DAQ task properly
            self.output_task.close()
            
            # Reset config file to default values
            default_config = {
                "scan_range": {
                    "x": [-1.0, 1.0],
                    "y": [-1.0, 1.0]
                },
                "resolution": {
                    "x": 10,
                    "y": 10
                },
                "dwell_time": 0.1
            }
            
            with open("config_template.json", 'w') as f:
                json.dump(default_config, f, indent=4)
            self.show_status("✨ Config reset to default values")
        except Exception as e:
            self.show_status(f"❌ Error during app closure: {str(e)}")
        
        event.accept()

# --------------------- MAIN APPLICATION ENTRY POINT ---------------------
def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName("NV Scanning Microscopy")
    
    # Create and show main window
    window = ConfocalMainWindow()
    window.show()
    
    # Start the Qt event loop
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
