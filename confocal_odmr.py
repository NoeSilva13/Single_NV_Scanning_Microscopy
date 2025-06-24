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
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QLabel, QPushButton, QSpinBox, 
                           QDoubleSpinBox, QGridLayout, QGroupBox, QTextEdit,
                           QSplitter, QFrame, QScrollArea, QSizePolicy, QComboBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread
from PyQt5.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QFont
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
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
from widgets.file_operations import load_scan as create_load_scan

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

# --------------------- SIGNAL BRIDGE FOR QT ---------------------
class QtSignalBridge(QObject):
    """Signal bridge for Qt-based communication"""
    info_signal = pyqtSignal(str)
    image_updated_signal = pyqtSignal(np.ndarray)
    scanner_position_signal = pyqtSignal(float, float)
    
# --------------------- PROFESSIONAL IMAGE DISPLAY WIDGET ---------------------
class ProfessionalImageWidget(QWidget):
    """Professional scientific image display widget with matplotlib backend"""
    
    clicked = pyqtSignal(float, float)  # x, y coordinates in real units
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(500, 500)
        self.setup_ui()
        
        # Image data
        self.image_data = None
        self.x_points = None
        self.y_points = None
        self.scanner_x = None
        self.scanner_y = None
        
        # Zoom selection
        self.zoom_start = None
        self.zoom_end = None
        self.drawing_zoom = False
        
    def setup_ui(self):
        """Setup the matplotlib-based UI"""
        layout = QVBoxLayout(self)
        
        # Create matplotlib figure with dark theme
        plt.style.use('dark_background')
        self.figure = Figure(figsize=(8, 8), facecolor='#262930')
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setStyleSheet("background-color: #262930;")
        
        # Create the main axes
        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor('#262930')
        
        # Style the axes
        self.ax.tick_params(colors='white', labelsize=10)
        self.ax.spines['bottom'].set_color('white')
        self.ax.spines['top'].set_color('white')
        self.ax.spines['right'].set_color('white')
        self.ax.spines['left'].set_color('white')
        
        # Set labels
        self.ax.set_xlabel('X (µm)', color='white', fontsize=12, fontweight='bold')
        self.ax.set_ylabel('Y (µm)', color='white', fontsize=12, fontweight='bold')
        
        # Initialize empty image
        self.im = None
        self.colorbar = None
        self.crosshair_v = None
        self.crosshair_h = None
        
        # Connect mouse events
        self.canvas.mpl_connect('button_press_event', self.on_click)
        self.canvas.mpl_connect('motion_notify_event', self.on_mouse_move)
        
        layout.addWidget(self.canvas)
        
    def set_image_data(self, image_data, x_points=None, y_points=None):
        """Set image data and coordinate arrays"""
        self.image_data = image_data
        self.x_points = x_points if x_points is not None else np.arange(image_data.shape[1])
        self.y_points = y_points if y_points is not None else np.arange(image_data.shape[0])
        self.update_display()
        
    def update_display(self):
        """Update the image display with professional styling"""
        if self.image_data is None:
            return
            
        self.ax.clear()
        
        # Create extent for proper coordinate mapping
        extent = [self.x_points[0], self.x_points[-1], 
                 self.y_points[0], self.y_points[-1]]
        
        # Display image with professional colormap
        self.current_cmap = getattr(self, 'current_cmap', 'plasma')
        self.im = self.ax.imshow(self.image_data, 
                                aspect='equal',
                                extent=extent,
                                cmap=self.current_cmap,  # Professional scientific colormap
                                origin='lower',
                                interpolation='bilinear')
        
        # Add colorbar if not exists
        if self.colorbar is None:
            self.colorbar = self.figure.colorbar(self.im, ax=self.ax, 
                                               label='APD Counts/s', 
                                               shrink=0.8)
            self.colorbar.ax.yaxis.label.set_color('white')
            self.colorbar.ax.tick_params(colors='white')
        else:
            self.colorbar.update_normal(self.im)
        
        # Style the axes
        self.ax.set_xlabel('X (µm)', color='white', fontsize=12, fontweight='bold')
        self.ax.set_ylabel('Y (µm)', color='white', fontsize=12, fontweight='bold')
        self.ax.tick_params(colors='white', labelsize=10)
        self.ax.grid(True, alpha=0.3, color='gray', linestyle='-', linewidth=0.5)
        
        # Set background
        self.ax.set_facecolor('#262930')
        
        # Add crosshair if scanner position is set
        self.update_crosshair()
        
        # Tight layout
        self.figure.tight_layout()
        self.canvas.draw()
        
    def update_crosshair(self):
        """Update crosshair position"""
        if self.scanner_x is not None and self.scanner_y is not None:
            # Remove old crosshair
            if self.crosshair_v is not None:
                self.crosshair_v.remove()
            if self.crosshair_h is not None:
                self.crosshair_h.remove()
                
            # Add new crosshair
            self.crosshair_v = self.ax.axvline(x=self.scanner_x, color='#00ffcc', 
                                             linewidth=2, alpha=0.8, linestyle='--')
            self.crosshair_h = self.ax.axhline(y=self.scanner_y, color='#00ffcc', 
                                             linewidth=2, alpha=0.8, linestyle='--')
            self.canvas.draw()
    
    def set_scanner_position(self, x_real, y_real):
        """Set scanner position in real coordinates"""
        self.scanner_x = x_real
        self.scanner_y = y_real
        self.update_crosshair()
    
    def on_click(self, event):
        """Handle mouse click events"""
        if event.inaxes != self.ax:
            return
            
        if event.button == 1:  # Left click
            x_real = event.xdata
            y_real = event.ydata
            
            if x_real is not None and y_real is not None:
                # Update scanner position
                self.set_scanner_position(x_real, y_real)
                # Emit signal with real coordinates
                self.clicked.emit(x_real, y_real)
    
    def on_mouse_move(self, event):
        """Handle mouse move for coordinate display"""
        if event.inaxes != self.ax:
            return
            
        if event.xdata is not None and event.ydata is not None:
            # Update cursor position in statusbar or tooltip
            self.setToolTip(f"Position: ({event.xdata:.3f}, {event.ydata:.3f}) µm")
    
    def set_colormap(self, cmap_name):
        """Change the colormap of the image"""
        self.current_cmap = cmap_name
        if self.im is not None:
            self.im.set_cmap(cmap_name)
            self.canvas.draw()

# Keep the old class for backward compatibility but rename it
class ImageDisplayWidget(QLabel):
    """Legacy image display widget - kept for compatibility"""
    
    clicked = pyqtSignal(int, int)  # x, y pixel coordinates
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 400)
        self.setStyleSheet("border: 1px solid #555555; background-color: #262930;")
        self.setAlignment(Qt.AlignCenter)
        self.setScaledContents(True)
        
        # Image data
        self.image_data = None
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.scanner_x = None
        self.scanner_y = None
        
        # Zoom selection
        self.zoom_start = None
        self.zoom_end = None
        self.drawing_zoom = False
        
    def set_image_data(self, image_data, scale_x=1.0, scale_y=1.0):
        """Set the image data and update display"""
        self.image_data = image_data
        self.scale_x = scale_x
        self.scale_y = scale_y
        self.update_display()
        
    def update_display(self):
        """Update the displayed image"""
        if self.image_data is None:
            return
            
        # Normalize image data to 0-255
        img_norm = self.image_data.copy()
        if img_norm.max() > img_norm.min():
            img_norm = (img_norm - img_norm.min()) / (img_norm.max() - img_norm.min()) * 255
        else:
            img_norm = np.zeros_like(img_norm)
        
        # Convert to QImage
        height, width = img_norm.shape
        bytes_per_line = width
        qimage = QImage(img_norm.astype(np.uint8), width, height, bytes_per_line, QImage.Format_Grayscale8)
        
        # Create pixmap and draw overlay
        pixmap = QPixmap.fromImage(qimage)
        painter = QPainter(pixmap)
        
        # Draw scanner position
        if self.scanner_x is not None and self.scanner_y is not None:
            painter.setPen(QPen(QColor(255, 0, 0), 3))
            painter.drawEllipse(int(self.scanner_x - 3), int(self.scanner_y - 3), 6, 6)
        
        # Draw zoom rectangle
        if self.zoom_start and self.zoom_end:
            painter.setPen(QPen(QColor(255, 0, 0), 2))
            x1, y1 = self.zoom_start
            x2, y2 = self.zoom_end
            painter.drawRect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
        
        painter.end()
        self.setPixmap(pixmap)
    
    def set_scanner_position(self, x_pixel, y_pixel):
        """Set scanner position marker"""
        self.scanner_x = x_pixel
        self.scanner_y = y_pixel
        self.update_display()
    
    def mousePressEvent(self, event):
        """Handle mouse press for clicking and zoom selection"""
        if event.button() == Qt.LeftButton:
            # Get click position relative to image
            pos = event.pos()
            if self.pixmap():
                # Scale click position to image coordinates
                pixmap_rect = self.pixmap().rect()
                widget_rect = self.rect()
                
                # Calculate scale factors
                scale_x = pixmap_rect.width() / widget_rect.width()
                scale_y = pixmap_rect.height() / widget_rect.height()
                
                x = int(pos.x() * scale_x)
                y = int(pos.y() * scale_y)
                
                # Check if we're starting zoom selection (Ctrl+click)
                if event.modifiers() & Qt.ControlModifier:
                    self.zoom_start = (x, y)
                    self.drawing_zoom = True
                else:
                    self.clicked.emit(x, y)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for zoom rectangle"""
        if self.drawing_zoom and event.buttons() & Qt.LeftButton:
            pos = event.pos()
            if self.pixmap():
                pixmap_rect = self.pixmap().rect()
                widget_rect = self.rect()
                
                scale_x = pixmap_rect.width() / widget_rect.width()
                scale_y = pixmap_rect.height() / widget_rect.height()
                
                x = int(pos.x() * scale_x)
                y = int(pos.y() * scale_y)
                
                self.zoom_end = (x, y)
                self.update_display()
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release for zoom selection"""
        if event.button() == Qt.LeftButton and self.drawing_zoom:
            self.drawing_zoom = False
            if self.zoom_start and self.zoom_end:
                # Calculate zoom region and emit signal if needed
                x1, y1 = self.zoom_start
                x2, y2 = self.zoom_end
                min_x, max_x = min(x1, x2), max(x1, x2)
                min_y, max_y = min(y1, y2), max(y1, y2)
                
                # Only proceed if zoom area is significant (> 10x10 pixels)
                if (max_x - min_x) > 10 and (max_y - min_y) > 10:
                    # Reset zoom selection
                    self.zoom_start = None
                    self.zoom_end = None
                    self.update_display()
                    
                    # TODO: Implement zoom functionality
                    # For now, just clear the selection
                else:
                    self.zoom_start = None
                    self.zoom_end = None
                    self.update_display()

# --------------------- LIVE PLOT WIDGET ---------------------
class LivePlotWidget(QWidget):
    """Widget for displaying live signal plot"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.data_points = []
        self.max_points = 100
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Create matplotlib figure with dark theme and compact size
        plt.style.use('dark_background')
        self.figure = Figure(figsize=(8, 3), facecolor='#262930')
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setStyleSheet("background-color: #262930;")
        self.ax = self.figure.add_subplot(111)
        
        layout.addWidget(self.canvas)
        
        # Setup plot with dark theme styling
        self.ax.set_facecolor('#262930')
        self.ax.tick_params(colors='white', labelsize=9)
        self.ax.spines['bottom'].set_color('white')
        self.ax.spines['top'].set_color('white')
        self.ax.spines['right'].set_color('white')
        self.ax.spines['left'].set_color('white')
        
        self.ax.set_xlabel('Time Points', color='white', fontsize=10)
        self.ax.set_ylabel('APD Counts/s', color='white', fontsize=10)
        self.ax.grid(True, alpha=0.3, color='gray', linestyle='-', linewidth=0.5)
        
        # Use cyan color for the signal line
        self.line, = self.ax.plot([], [], '#00ffcc', linewidth=2)
        
        # Tight layout
        self.figure.tight_layout()
        
    def update_plot(self, value):
        """Update the live plot with new data point"""
        self.data_points.append(value)
        if len(self.data_points) > self.max_points:
            self.data_points.pop(0)
        
        x_data = list(range(len(self.data_points)))
        self.line.set_data(x_data, self.data_points)
        
        if self.data_points:
            self.ax.set_xlim(0, len(self.data_points))
            self.ax.set_ylim(min(self.data_points) * 0.9, max(self.data_points) * 1.1)
        
        self.canvas.draw()

# --------------------- CONTROL PANEL WIDGET ---------------------
class ControlPanelWidget(QWidget):
    """Widget containing all control buttons and parameters"""
    
    scan_requested = pyqtSignal()
    save_requested = pyqtSignal()
    reset_zoom_requested = pyqtSignal()
    close_scanner_requested = pyqtSignal()
    auto_focus_requested = pyqtSignal()
    load_scan_requested = pyqtSignal()
    parameters_updated = pyqtSignal(dict)
    colormap_changed = pyqtSignal(str)
    
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setup_ui()
        self.update_parameter_display()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Scan Parameters Group
        params_group = QGroupBox("Scan Parameters")
        params_layout = QGridLayout(params_group)
        
        # X Range
        params_layout.addWidget(QLabel("X Range:"), 0, 0)
        self.x_min_spin = QDoubleSpinBox()
        self.x_min_spin.setRange(-10, 10)
        self.x_min_spin.setDecimals(3)
        self.x_min_spin.setSingleStep(0.1)
        params_layout.addWidget(self.x_min_spin, 0, 1)
        
        self.x_max_spin = QDoubleSpinBox()
        self.x_max_spin.setRange(-10, 10)
        self.x_max_spin.setDecimals(3)
        self.x_max_spin.setSingleStep(0.1)
        params_layout.addWidget(self.x_max_spin, 0, 2)
        
        # Y Range
        params_layout.addWidget(QLabel("Y Range:"), 1, 0)
        self.y_min_spin = QDoubleSpinBox()
        self.y_min_spin.setRange(-10, 10)
        self.y_min_spin.setDecimals(3)
        self.y_min_spin.setSingleStep(0.1)
        params_layout.addWidget(self.y_min_spin, 1, 1)
        
        self.y_max_spin = QDoubleSpinBox()
        self.y_max_spin.setRange(-10, 10)
        self.y_max_spin.setDecimals(3)
        self.y_max_spin.setSingleStep(0.1)
        params_layout.addWidget(self.y_max_spin, 1, 2)
        
        # Resolution
        params_layout.addWidget(QLabel("X Resolution:"), 2, 0)
        self.x_res_spin = QSpinBox()
        self.x_res_spin.setRange(5, 500)
        params_layout.addWidget(self.x_res_spin, 2, 1)
        
        params_layout.addWidget(QLabel("Y Resolution:"), 3, 0)
        self.y_res_spin = QSpinBox()
        self.y_res_spin.setRange(5, 500)
        params_layout.addWidget(self.y_res_spin, 3, 1)
        
        # Update button
        update_btn = QPushButton("Update Parameters")
        update_btn.clicked.connect(self.update_parameters)
        params_layout.addWidget(update_btn, 4, 0, 1, 3)
        
        layout.addWidget(params_group)
        
        # Control Buttons Group
        controls_group = QGroupBox("Controls")
        controls_layout = QVBoxLayout(controls_group)
        
        self.scan_btn = QPushButton("New Scan")
        self.scan_btn.clicked.connect(self.scan_requested.emit)
        controls_layout.addWidget(self.scan_btn)
        
        self.save_btn = QPushButton("Save Image")
        self.save_btn.clicked.connect(self.save_requested.emit)
        controls_layout.addWidget(self.save_btn)
        
        self.reset_zoom_btn = QPushButton("Reset Zoom")
        self.reset_zoom_btn.clicked.connect(self.reset_zoom_requested.emit)
        controls_layout.addWidget(self.reset_zoom_btn)
        
        self.auto_focus_btn = QPushButton("Auto Focus")
        self.auto_focus_btn.clicked.connect(self.auto_focus_requested.emit)
        controls_layout.addWidget(self.auto_focus_btn)
        
        self.load_btn = QPushButton("Load Scan")
        self.load_btn.clicked.connect(self.load_scan_requested.emit)
        controls_layout.addWidget(self.load_btn)
        
        self.close_btn = QPushButton("Close Scanner")
        self.close_btn.clicked.connect(self.close_scanner_requested.emit)
        controls_layout.addWidget(self.close_btn)
        
        layout.addWidget(controls_group)
        
        # Display Options Group
        display_group = QGroupBox("Display Options")
        display_layout = QVBoxLayout(display_group)
        
        # Colormap selection
        colormap_layout = QHBoxLayout()
        colormap_layout.addWidget(QLabel("Colormap:"))
        self.colormap_combo = QComboBox()
        self.colormap_combo.addItems(['plasma', 'viridis', 'inferno', 'magma', 'cividis', 'hot', 'cool', 'gray'])
        self.colormap_combo.setCurrentText('plasma')
        self.colormap_combo.currentTextChanged.connect(self.on_colormap_changed)
        colormap_layout.addWidget(self.colormap_combo)
        display_layout.addLayout(colormap_layout)
        
        layout.addWidget(display_group)
        
        # Status/Info Display
        info_group = QGroupBox("Status")
        info_layout = QVBoxLayout(info_group)
        self.info_text = QTextEdit()
        self.info_text.setMaximumHeight(100)
        self.info_text.setReadOnly(True)
        info_layout.addWidget(self.info_text)
        
        layout.addWidget(info_group)
        
    def update_parameter_display(self):
        """Update the parameter display with current config values"""
        config = self.config_manager.get_config()
        
        self.x_min_spin.setValue(config['scan_range']['x'][0])
        self.x_max_spin.setValue(config['scan_range']['x'][1])
        self.y_min_spin.setValue(config['scan_range']['y'][0])
        self.y_max_spin.setValue(config['scan_range']['y'][1])
        self.x_res_spin.setValue(config['resolution']['x'])
        self.y_res_spin.setValue(config['resolution']['y'])
        
    def update_parameters(self):
        """Update parameters and emit signal"""
        params = {
            'x_range': [self.x_min_spin.value(), self.x_max_spin.value()],
            'y_range': [self.y_min_spin.value(), self.y_max_spin.value()],
            'x_res': self.x_res_spin.value(),
            'y_res': self.y_res_spin.value()
        }
        self.parameters_updated.emit(params)
        
    def add_info_message(self, message):
        """Add an info message to the status display"""
        self.info_text.append(message)
        # Auto-scroll to bottom
        cursor = self.info_text.textCursor()
        cursor.movePosition(cursor.End)
        self.info_text.setTextCursor(cursor)
    
    def on_colormap_changed(self, colormap_name):
        """Handle colormap change"""
        self.colormap_changed.emit(colormap_name)

# --------------------- MAIN APPLICATION CLASS ---------------------
class ConfocalMicroscopyApp(QMainWindow):
    """Main application class for the confocal microscopy system"""
    
    def __init__(self):
        super().__init__()
        
        # Initialize global state variables
        self.contrast_limits = (0, 10000)
        self.scan_history = []
        self.image = None
        self.data_path = None
        self.zoom_in_progress = False
        
        # Initialize managers first (needed by UI)
        self.config_manager = ConfigManager()
        self.scan_points_manager = ScanPointsManager(self.config_manager)
        self.zoom_manager = ZoomLevelManager()
        
        # Setup UI (now that managers exist)
        self.setup_ui()
        
        # Setup hardware
        self.setup_hardware()
        
        # Connect signals and start timers
        self.setup_connections()
        self.setup_timer()
        
    def setup_hardware(self):
        """Initialize hardware components"""
        # Initialize hardware controllers
        self.galvo_controller = GalvoScannerController()
        self.data_manager = DataManager()
        
        # Initialize DAQ output task for galvo control
        self.output_task = nidaqmx.Task()
        self.output_task.ao_channels.add_ao_voltage_chan(self.galvo_controller.xin_control)
        self.output_task.ao_channels.add_ao_voltage_chan(self.galvo_controller.yin_control)
        self.output_task.start()
        
        # Initialize TimeTagger
        try:
            self.tagger = createTimeTagger()
            self.tagger.reset()
            self.add_info_message("✅ Connected to real TimeTagger device")
        except Exception as e:
            self.add_info_message("⚠️ Real TimeTagger not detected, using virtual device")
            self.tagger = createTimeTaggerVirtual("TimeTagger/time_tags_test.ttbin")
            self.tagger.run()
        
        # Set bin width to 5 ns
        self.binwidth = int(5e9)
        n_values = 1
        self.counter = Counter(self.tagger, [1], self.binwidth, n_values)
        
        # Signal bridge
        self.signal_bridge = QtSignalBridge()
        self.signal_bridge.info_signal.connect(self.add_info_message)
        
    def setup_ui(self):
        """Setup the user interface"""
        self.setWindowTitle("Confocal Single-NV Microscopy Control")
        self.setGeometry(100, 100, 1200, 800)
        
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
             QComboBox {
                 background-color: #3c3c3c;
                 color: #ffffff;
                 border: 1px solid #555555;
                 border-radius: 4px;
                 padding: 5px;
                 font-size: 10pt;
                 min-width: 100px;
             }
             QComboBox:focus {
                 border: 2px solid #00d4aa;
             }
             QComboBox::drop-down {
                 border: none;
                 width: 20px;
             }
             QComboBox::down-arrow {
                 image: none;
                 border: 2px solid #555555;
                 width: 3px;
                 height: 3px;
                 background: #00d4aa;
             }
        """)
        
        # Central widget with splitter
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_splitter = QSplitter(Qt.Horizontal)
        
        # Left panel - Controls
        self.control_panel = ControlPanelWidget(self.config_manager)
        main_splitter.addWidget(self.control_panel)
        
        # Center-Right panel - Image and Live plot in vertical arrangement
        center_right_container = QWidget()
        center_right_layout = QVBoxLayout(center_right_container)
        center_right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create vertical splitter for image and live plot
        vertical_splitter = QSplitter(Qt.Vertical)
        
        # Image panel (top)
        image_container = QWidget()
        image_layout = QVBoxLayout(image_container)
        
        # Title with styling
        title_label = QLabel("Scan Image")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 14pt;
                font-weight: bold;
                color: #00d4aa;
                padding: 5px;
                border-bottom: 2px solid #555555;
                margin-bottom: 10px;
            }
        """)
        image_layout.addWidget(title_label)
        
        self.image_display = ProfessionalImageWidget()
        image_layout.addWidget(self.image_display)
        
        vertical_splitter.addWidget(image_container)
        
        # Live plot panel (bottom)
        plot_container = QWidget()
        plot_layout = QVBoxLayout(plot_container)
        
        # Live plot title with styling
        plot_title_label = QLabel("Live Signal")
        plot_title_label.setStyleSheet("""
            QLabel {
                font-size: 12pt;
                font-weight: bold;
                color: #00d4aa;
                padding: 5px;
                border-bottom: 2px solid #555555;
                margin-bottom: 5px;
            }
        """)
        plot_layout.addWidget(plot_title_label)
        
        self.live_plot = LivePlotWidget()
        plot_layout.addWidget(self.live_plot)
        
        vertical_splitter.addWidget(plot_container)
        
        # Set vertical splitter proportions (image takes more space)
        vertical_splitter.setSizes([400, 200])
        
        center_right_layout.addWidget(vertical_splitter)
        main_splitter.addWidget(center_right_container)
        
        # Set horizontal splitter proportions
        main_splitter.setSizes([300, 700])
        main_layout.addWidget(main_splitter)
        
        # Initialize image with zeros and proper coordinates
        config = self.config_manager.get_config()
        x_res = config['resolution']['x']
        y_res = config['resolution']['y']
        x_range = config['scan_range']['x']
        y_range = config['scan_range']['y']
        
        self.image = np.zeros((y_res, x_res), dtype=np.float32)
        
        # Create initial coordinate arrays
        x_points = np.linspace(x_range[0], x_range[1], x_res)
        y_points = np.linspace(y_range[0], y_range[1], y_res)
        x_points_um = x_points * MICRONS_PER_VOLT
        y_points_um = y_points * MICRONS_PER_VOLT
        
        self.image_display.set_image_data(self.image, x_points_um, y_points_um)
        
    def setup_connections(self):
        """Setup signal connections"""
        # Control panel connections
        self.control_panel.scan_requested.connect(self.start_scan)
        self.control_panel.save_requested.connect(self.save_image)
        self.control_panel.reset_zoom_requested.connect(self.reset_zoom)
        self.control_panel.close_scanner_requested.connect(self.close_scanner)
        self.control_panel.auto_focus_requested.connect(self.auto_focus)
        self.control_panel.load_scan_requested.connect(self.load_scan)
        self.control_panel.parameters_updated.connect(self.update_scan_parameters)
        self.control_panel.colormap_changed.connect(self.on_colormap_changed)
        
        # Image display connections
        self.image_display.clicked.connect(self.on_image_click)
        
    def setup_timer(self):
        """Setup timer for live plot updates"""
        self.plot_timer = QTimer()
        self.plot_timer.timeout.connect(self.update_live_plot)
        self.plot_timer.start(200)  # Update every 200ms
        
    def update_live_plot(self):
        """Update the live plot with current counter data"""
        try:
            counts = self.counter.getData()[0][0]/(self.binwidth/1e12)
            self.live_plot.update_plot(counts)
        except Exception as e:
            pass  # Silently handle errors
            
    def add_info_message(self, message):
        """Add info message to control panel"""
        self.control_panel.add_info_message(message)
        
    def on_image_click(self, x_real, y_real):
        """Handle image click to move scanner (receives micron coordinates from widget)"""
        if self.image is None:
            return
        
        try:
            # Convert from micron coordinates back to voltage
            x_voltage = x_real / MICRONS_PER_VOLT
            y_voltage = y_real / MICRONS_PER_VOLT
            
            self.output_task.write([x_voltage, y_voltage])
            self.add_info_message(f"🎯 Moved scanner to: X={x_voltage:.3f}V, Y={y_voltage:.3f}V ({x_real:.1f}, {y_real:.1f} µm)")
            
            # Update the crosshair position (in micron coordinates for display)
            self.image_display.set_scanner_position(x_real, y_real)
            
        except Exception as e:
            self.add_info_message(f"❌ Error moving scanner: {str(e)}")
            
    def start_scan(self):
        """Start a new scan"""
        x_points, y_points = self.scan_points_manager.get_points()
        
        def run_scan():
            self.scan_pattern(x_points, y_points)
            
        scan_thread = threading.Thread(target=run_scan, daemon=True)
        scan_thread.start()
        
    def scan_pattern(self, x_points, y_points):
        """Perform a raster scan pattern using the galvo mirrors and collect APD counts."""
        height, width = len(y_points), len(x_points)
        self.image = np.zeros((height, width), dtype=np.float32)
        
        self.add_info_message(f"🔍 Starting scan: {width}x{height} points")
        
        try:
            for y_idx, y in enumerate(y_points):
                for x_idx, x in enumerate(x_points):
                    self.output_task.write([x, y])
                    if x_idx == 0:
                        time.sleep(0.05)
                    else:
                        time.sleep(0.001)
                        
                    counts = self.counter.getData()[0][0]/(self.binwidth/1e12)
                    self.image[y_idx, x_idx] = counts
                    
                    # Update display every 10 points to keep UI responsive
                    if (y_idx * width + x_idx) % 10 == 0:
                        # Convert coordinates for display update
                        x_points_um = np.array(x_points) * MICRONS_PER_VOLT
                        y_points_um = np.array(y_points) * MICRONS_PER_VOLT
                        self.image_display.set_image_data(self.image, x_points_um, y_points_um)
                        QApplication.processEvents()
            
            self.add_info_message("✅ Scan completed successfully")
            
        except Exception as e:
            self.add_info_message(f"❌ Error during scan: {str(e)}")
            return
        
        # Update professional image display with real coordinates
        scale_um_per_px_x = calculate_scale(x_points[0], x_points[-1], width)
        scale_um_per_px_y = calculate_scale(y_points[0], y_points[-1], height)
        
        # Convert voltage points to micron coordinates for display
        x_points_um = np.array(x_points) * MICRONS_PER_VOLT
        y_points_um = np.array(y_points) * MICRONS_PER_VOLT
        
        self.image_display.set_image_data(self.image, x_points_um, y_points_um)
        
        # Create a dictionary with image and scan positions
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
        self.add_info_message("🎯 Scanner returned to zero position")
        
    def save_image(self):
        """Save current image"""
        if self.image is not None and self.data_path is not None:
            self.add_info_message(f"Image saved to: {self.data_path}")
        else:
            self.add_info_message("No image to save")
            
    def reset_zoom(self):
        """Reset zoom to original view"""
        if self.scan_history:
            x_points, y_points = self.scan_history[0]
            self.config_manager.update_scan_parameters(
                x_range=[x_points[0], x_points[-1]],
                y_range=[y_points[0], y_points[-1]]
            )
            self.scan_points_manager._update_points_from_config()
            self.control_panel.update_parameter_display()
            self.zoom_manager.set_zoom_level(0)
            self.scan_history.clear()
            self.add_info_message("🔄 Zoom reset to original view")
        
    def close_scanner(self):
        """Close scanner and set to zero position"""
        try:
            self.output_task.write([0, 0])
            self.add_info_message("🎯 Scanner set to zero position")
        except Exception as e:
            self.add_info_message(f"❌ Error setting scanner to zero: {str(e)}")
            
    def auto_focus(self):
        """Perform auto focus (placeholder)"""
        self.add_info_message("Auto focus not yet implemented in Qt version")
        
    def load_scan(self):
        """Load a previous scan (placeholder)"""
        self.add_info_message("Load scan not yet implemented in Qt version")
        
    def update_scan_parameters(self, params):
        """Update scan parameters"""
        self.config_manager.update_scan_parameters(**params)
        self.scan_points_manager._update_points_from_config()
        self.add_info_message("📐 Scan parameters updated")
    
    def on_colormap_changed(self, colormap_name):
        """Handle colormap change"""
        self.image_display.set_colormap(colormap_name)
        self.add_info_message(f"🎨 Colormap changed to: {colormap_name}")
        
    def closeEvent(self, event):
        """Handle application close"""
        try:
            # Set scanner to zero position before closing
            self.output_task.write([0, 0])
            self.add_info_message("🎯 Scanner set to zero position")
            
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
            self.add_info_message("✨ Config reset to default values")
        except Exception as e:
            self.add_info_message(f"❌ Error during app closure: {str(e)}")
        
        event.accept()

def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    
    window = ConfocalMicroscopyApp()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 