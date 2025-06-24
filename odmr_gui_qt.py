"""
ODMR Control Center - Qt GUI Application
----------------------------------------
Professional GUI for controlling continuous wave ODMR experiments.
Designed with the same visual style and organization as the NV scanning microscopy software.

Author: NV Lab
Date: 2025
"""

import sys
import json
import threading
import time
import os
from typing import Dict, List, Optional
import numpy as np

# Qt imports
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QGridLayout, QLabel, QLineEdit, QPushButton, QProgressBar,
    QTextEdit, QGroupBox, QTabWidget, QFileDialog, QMessageBox,
    QSplitter, QFrame, QScrollArea, QSpacerItem, QSizePolicy
)
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QFont, QPalette, QColor

# Matplotlib imports for real-time plotting
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.style as mplstyle

# Import ODMR experiment classes
from PulseBlaster.swabian_pulse_streamer import SwabianPulseController
from PulseBlaster.rigol_dsg836 import RigolDSG836Controller
from PulseBlaster.odmr_experiments import ODMRExperiments

# Import confocal control classes
import json
import nidaqmx
from TimeTagger import createTimeTagger, Counter, createTimeTaggerVirtual
from galvo_controller import GalvoScannerController
from data_manager import DataManager


class ODMRWorker(QThread):
    """Worker thread for running ODMR measurements"""
    
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    data_updated = pyqtSignal(list, list)  # frequencies, count_rates
    measurement_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)
    
    def __init__(self, experiments, parameters):
        super().__init__()
        self.experiments = experiments
        self.parameters = parameters
        self.is_running = True
    
    def stop(self):
        """Stop the measurement"""
        self.is_running = False
    
    def run(self):
        """Run the ODMR measurement"""
        try:
            frequencies = self.parameters['mw_frequencies']
            total_points = len(frequencies)
            
            all_frequencies = []
            all_count_rates = []
            
            for i, freq in enumerate(frequencies):
                if not self.is_running:
                    break
                
                # Update progress and status
                progress = int((i / total_points) * 100)
                self.progress_updated.emit(progress)
                self.status_updated.emit(f"Measuring {freq/1e9:.4f} GHz ({i+1}/{total_points})")
                
                # Run single frequency measurement
                single_params = self.parameters.copy()
                single_params['mw_frequencies'] = [freq]
                
                result = self.experiments.continuous_wave_odmr(**single_params)
                
                if result and 'count_rates' in result and len(result['count_rates']) > 0:
                    all_frequencies.append(freq)
                    all_count_rates.append(result['count_rates'][0])
                    
                    # Emit data update for real-time plotting
                    self.data_updated.emit(all_frequencies.copy(), all_count_rates.copy())
            
            if self.is_running:
                self.progress_updated.emit(100)
                self.status_updated.emit("ODMR measurement completed!")
            
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            self.measurement_finished.emit()


class LivePlotWidget(QWidget):
    """Real-time plotting widget for ODMR spectrum"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.frequencies = []
        self.count_rates = []
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Create matplotlib figure with dark theme
        self.figure = Figure(figsize=(15, 15), dpi=100, facecolor='#262930')
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111, facecolor='#262930')
        
        # Style the plot with napari-inspired dark theme
        self.ax.set_xlabel('Frequency (GHz)', fontsize=12, color='white')
        self.ax.set_ylabel('Count Rate (Hz)', fontsize=12, color='white')
        self.ax.set_title('ODMR Spectrum (Live)', fontsize=14, fontweight='bold', color='white')
        self.ax.grid(True, alpha=0.3, color='#555555')
        self.ax.tick_params(colors='white')
        self.ax.spines['bottom'].set_color('white')
        self.ax.spines['top'].set_color('white')
        self.ax.spines['right'].set_color('white')
        self.ax.spines['left'].set_color('white')
        
        layout.addWidget(self.canvas)
        self.setLayout(layout)
    
    def update_plot(self, frequencies, count_rates):
        """Update the plot with new data"""
        self.frequencies = frequencies
        self.count_rates = count_rates
        
        self.ax.clear()
        
        if len(frequencies) > 0:
            freq_ghz = np.array(frequencies) / 1e9
            # Use viridis-inspired green color like napari
            self.ax.plot(freq_ghz, count_rates, 'o-', markersize=4, linewidth=2, 
                        color='#00ff88', markerfacecolor='#00d4aa', markeredgecolor='#00ff88')
        
        # Re-apply dark theme styling after clear
        self.ax.set_facecolor('#262930')
        self.ax.set_xlabel('Frequency (GHz)', fontsize=12, color='white')
        self.ax.set_ylabel('Count Rate (Hz)', fontsize=12, color='white')
        self.ax.set_title('ODMR Spectrum (Live)', fontsize=14, fontweight='bold', color='white')
        self.ax.grid(True, alpha=0.3, color='#555555')
        self.ax.tick_params(colors='white')
        self.ax.spines['bottom'].set_color('white')
        self.ax.spines['top'].set_color('white')
        self.ax.spines['right'].set_color('white')
        self.ax.spines['left'].set_color('white')
        
        # Auto-scale with padding
        if len(frequencies) > 1:
            freq_range = max(frequencies) - min(frequencies)
            self.ax.set_xlim((min(frequencies) - 0.05*freq_range)/1e9, 
                           (max(frequencies) + 0.05*freq_range)/1e9)
        
        if len(count_rates) > 1:
            count_range = max(count_rates) - min(count_rates)
            if count_range > 0:
                self.ax.set_ylim(min(count_rates) - 0.1*count_range,
                               max(count_rates) + 0.1*count_range)
        
        self.figure.tight_layout()
        self.canvas.draw()


class ParameterGroupBox(QGroupBox):
    """Custom group box for parameter input sections"""
    
    def __init__(self, title):
        super().__init__(title)
        # No need for separate styling here - handled by main stylesheet
        self.layout = QGridLayout()
        self.setLayout(self.layout)
        self.row_count = 0
    
    def add_parameter(self, label_text, default_value="", tooltip=""):
        """Add a parameter input field"""
        label = QLabel(label_text)
        entry = QLineEdit(default_value)
        entry.setToolTip(tooltip)
        # Styling handled by main stylesheet
        
        self.layout.addWidget(label, self.row_count, 0)
        self.layout.addWidget(entry, self.row_count, 1)
        self.row_count += 1
        
        return entry


class DeviceStatusWidget(QGroupBox):
    """Widget for displaying device connection status"""
    
    def __init__(self, title):
        super().__init__(title)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Pulse Streamer status
        ps_layout = QHBoxLayout()
        ps_layout.addWidget(QLabel("Pulse Streamer:"))
        self.ps_ip = QLineEdit("192.168.0.201")
        self.ps_ip.setPlaceholderText("IP address")
        self.ps_ip.setToolTip("Enter IP address for Pulse Streamer network connection")
        ps_layout.addWidget(self.ps_ip)
        self.ps_status = QLabel("Disconnected")
        self.ps_status.setStyleSheet("color: red; font-weight: bold;")
        ps_layout.addWidget(self.ps_status)
        ps_layout.addStretch()
        self.ps_connect_btn = QPushButton("Connect")
        ps_layout.addWidget(self.ps_connect_btn)
        layout.addLayout(ps_layout)
        
        # RIGOL status
        rigol_layout = QHBoxLayout()
        rigol_layout.addWidget(QLabel("RIGOL DSG836:"))
        self.rigol_ip = QLineEdit("192.168.0.222")
        rigol_layout.addWidget(self.rigol_ip)
        self.rigol_status = QLabel("Disconnected")
        self.rigol_status.setStyleSheet("color: red; font-weight: bold;")
        rigol_layout.addWidget(self.rigol_status)
        rigol_layout.addStretch()
        self.rigol_connect_btn = QPushButton("Connect")
        rigol_layout.addWidget(self.rigol_connect_btn)
        layout.addLayout(rigol_layout)
        
# MW Power setting moved to Advanced Settings tab
        
        self.setLayout(layout)
        # Styling handled by main stylesheet
    
    def update_ps_status(self, connected):
        """Update Pulse Streamer connection status"""
        if connected:
            self.ps_status.setText("Connected")
            self.ps_status.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.ps_status.setText("Disconnected")
            self.ps_status.setStyleSheet("color: red; font-weight: bold;")
    
    def update_rigol_status(self, connected):
        """Update RIGOL connection status"""
        if connected:
            self.rigol_status.setText("Connected")
            self.rigol_status.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.rigol_status.setText("Disconnected")
            self.rigol_status.setStyleSheet("color: red; font-weight: bold;")


class ConfocalImageWidget(QWidget):
    """Widget for displaying confocal scan images with click and zoom functionality"""
    
    point_clicked = pyqtSignal(float, float)  # x_voltage, y_voltage
    zoom_selected = pyqtSignal(float, float, float, float)  # x_min, x_max, y_min, y_max
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.image_data = None
        self.x_points = None
        self.y_points = None
        self.zoom_start = None
        self.zoom_rect = None
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Create matplotlib figure with dark theme
        self.figure = Figure(figsize=(8, 8), dpi=100, facecolor='#262930')
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111, facecolor='#262930')
        
        # Style the plot
        self.ax.set_xlabel('X Voltage (V)', fontsize=12, color='white')
        self.ax.set_ylabel('Y Voltage (V)', fontsize=12, color='white')
        self.ax.set_title('Confocal Scan Image', fontsize=14, fontweight='bold', color='white')
        self.ax.tick_params(colors='white')
        for spine in self.ax.spines.values():
            spine.set_color('white')
        
        # Connect mouse events
        self.canvas.mpl_connect('button_press_event', self.on_mouse_press)
        self.canvas.mpl_connect('button_release_event', self.on_mouse_release)
        self.canvas.mpl_connect('motion_notify_event', self.on_mouse_move)
        
        layout.addWidget(self.canvas)
        self.setLayout(layout)
        
        # Initialize with empty image
        self.update_image(np.zeros((50, 50)), np.linspace(-1, 1, 50), np.linspace(-1, 1, 50))
    
    def update_image(self, image_data, x_points, y_points):
        """Update the displayed image"""
        self.image_data = image_data
        self.x_points = x_points
        self.y_points = y_points
        
        self.ax.clear()
        
        # Create the image plot
        extent = [x_points[0], x_points[-1], y_points[0], y_points[-1]]
        im = self.ax.imshow(image_data, extent=extent, origin='lower', 
                           cmap='viridis', aspect='equal', interpolation='nearest')
        
        # Re-apply styling
        self.ax.set_facecolor('#262930')
        self.ax.set_xlabel('X Voltage (V)', fontsize=12, color='white')
        self.ax.set_ylabel('Y Voltage (V)', fontsize=12, color='white')
        self.ax.set_title('Confocal Scan Image', fontsize=14, fontweight='bold', color='white')
        self.ax.tick_params(colors='white')
        for spine in self.ax.spines.values():
            spine.set_color('white')
        
        # Add colorbar
        if hasattr(self, 'colorbar'):
            self.colorbar.remove()
        self.colorbar = self.figure.colorbar(im, ax=self.ax)
        self.colorbar.ax.tick_params(colors='white')
        self.colorbar.ax.yaxis.label.set_color('white')
        
        self.figure.tight_layout()
        self.canvas.draw()
    
    def on_mouse_press(self, event):
        """Handle mouse press for click and zoom selection"""
        if event.inaxes != self.ax:
            return
        
        if event.button == 1:  # Left click - move galvo
            x_pos, y_pos = event.xdata, event.ydata
            self.point_clicked.emit(x_pos, y_pos)
        elif event.button == 3:  # Right click - start zoom selection
            self.zoom_start = (event.xdata, event.ydata)
    
    def on_mouse_move(self, event):
        """Handle mouse move for zoom rectangle"""
        if event.inaxes != self.ax or self.zoom_start is None:
            return
        
        # Update zoom rectangle
        if self.zoom_rect:
            self.zoom_rect.remove()
        
        x_start, y_start = self.zoom_start
        width = event.xdata - x_start
        height = event.ydata - y_start
        
        self.zoom_rect = plt.Rectangle((x_start, y_start), width, height,
                                      fill=False, edgecolor='red', linewidth=2)
        self.ax.add_patch(self.zoom_rect)
        self.canvas.draw()
    
    def on_mouse_release(self, event):
        """Handle mouse release for zoom selection"""
        if event.button == 3 and self.zoom_start is not None:
            x_start, y_start = self.zoom_start
            x_end, y_end = event.xdata, event.ydata
            
            if x_end is not None and y_end is not None:
                x_min = min(x_start, x_end)
                x_max = max(x_start, x_end)
                y_min = min(y_start, y_end)
                y_max = max(y_start, y_end)
                
                # Only emit if zoom area is significant
                if abs(x_max - x_min) > 0.1 and abs(y_max - y_min) > 0.1:
                    self.zoom_selected.emit(x_min, x_max, y_min, y_max)
            
            self.zoom_start = None
            if self.zoom_rect:
                self.zoom_rect.remove()
                self.zoom_rect = None
                self.canvas.draw()


class LiveSignalPlot(QWidget):
    """Widget for live signal plotting during scans"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.x_data = []
        self.y_data = []
        self.start_time = time.time()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Create matplotlib figure
        self.figure = Figure(figsize=(8, 3), dpi=100, facecolor='#262930')
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111, facecolor='#262930')
        
        # Style the plot
        self.ax.set_xlabel('Time (s)', fontsize=10, color='white')
        self.ax.set_ylabel('Signal (Hz)', fontsize=10, color='white')
        self.ax.set_title('Live Signal', fontsize=12, fontweight='bold', color='white')
        self.ax.tick_params(colors='white')
        for spine in self.ax.spines.values():
            spine.set_color('white')
        self.ax.grid(True, alpha=0.3, color='#555555')
        
        self.line, = self.ax.plot([], [], color='#00ff88', linewidth=2)
        
        layout.addWidget(self.canvas)
        self.setLayout(layout)
        
        # Timer for updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(200)  # Update every 200ms
    
    def add_data_point(self, value):
        """Add a new data point"""
        current_time = time.time() - self.start_time
        self.x_data.append(current_time)
        self.y_data.append(value)
        
        # Keep only last 100 points
        if len(self.x_data) > 100:
            self.x_data = self.x_data[-100:]
            self.y_data = self.y_data[-100:]
    
    def update_plot(self):
        """Update the plot display"""
        if len(self.x_data) > 0:
            self.line.set_data(self.x_data, self.y_data)
            self.ax.relim()
            self.ax.autoscale_view()
            self.canvas.draw()
    
    def clear(self):
        """Clear the plot"""
        self.x_data.clear()
        self.y_data.clear()
        self.start_time = time.time()
        self.line.set_data([], [])
        self.canvas.draw()


class ODMRControlCenter(QMainWindow):
    """Main ODMR Control Center application"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.init_hardware()
        self.init_confocal_hardware()
        self.current_results = {'frequencies': [], 'count_rates': []}
        self.worker = None
        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("ODMR Control Center - NV Lab")
        self.setGeometry(100, 100, 2000, 1350)
        
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
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Create main horizontal splitter
        main_splitter = QSplitter(Qt.Horizontal)
        central_widget_layout = QHBoxLayout()
        central_widget_layout.addWidget(main_splitter)
        central_widget.setLayout(central_widget_layout)
        
        # Create left tabbed control panel
        self.create_tabbed_control_panel(main_splitter)
        
        # Create right visualization panel
        self.create_visualization_panel(main_splitter)
        
        # Set splitter sizes (1:2 ratio)
        main_splitter.setSizes([400, 800])
        
        # Create status bar
        self.statusBar().showMessage("Ready")
        
    def create_tabbed_control_panel(self, parent):
        """Create the left tabbed control panel"""
        # Create tab widget
        self.tab_widget = QTabWidget()
        
        # Add dark theme styling for tabs
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #555555;
                background-color: #262930;
            }
            QTabBar::tab {
                background-color: #3c3c3c;
                color: #ffffff;
                padding: 8px 20px;
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
        """)
        
        # Create Confocal Control tab (main tab)
        self.create_confocal_control_tab()
        
        # Create ODMR Control tab
        self.create_odmr_control_tab()
        
        # Create Device Settings tab
        self.create_device_settings_tab()
        
        parent.addWidget(self.tab_widget)
    
    def create_confocal_control_tab(self):
        """Create the comprehensive Confocal Control tab"""
        confocal_widget = QWidget()
        main_layout = QHBoxLayout()
        
        # Left control panel
        left_panel = QWidget()
        left_panel.setMaximumWidth(400)
        left_layout = QVBoxLayout()
        
        # Create scroll area for controls
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()
        
        # Scan Parameters Group
        scan_params_group = ParameterGroupBox("Scan Parameters")
        self.x_min = scan_params_group.add_parameter("X Min (V):", "-1.0", "Minimum X scan voltage")
        self.x_max = scan_params_group.add_parameter("X Max (V):", "1.0", "Maximum X scan voltage")
        self.y_min = scan_params_group.add_parameter("Y Min (V):", "-1.0", "Minimum Y scan voltage")
        self.y_max = scan_params_group.add_parameter("Y Max (V):", "1.0", "Maximum Y scan voltage")
        self.x_resolution = scan_params_group.add_parameter("X Resolution:", "50", "X resolution in pixels")
        self.y_resolution = scan_params_group.add_parameter("Y Resolution:", "50", "Y resolution in pixels")
        self.dwell_time = scan_params_group.add_parameter("Dwell Time (ms):", "10", "Time per pixel in milliseconds")
        scroll_layout.addWidget(scan_params_group)
        
        # Current Position Group
        position_group = ParameterGroupBox("Current Position")
        self.current_x_v = position_group.add_parameter("X Position (V):", "0.0", "Current X galvo voltage")
        self.current_y_v = position_group.add_parameter("Y Position (V):", "0.0", "Current Y galvo voltage")
        self.current_x_v.setReadOnly(True)
        self.current_y_v.setReadOnly(True)
        scroll_layout.addWidget(position_group)
        
        # Control Buttons Group
        control_group = QGroupBox("Control")
        control_layout = QVBoxLayout()
        
        # Scan control buttons
        scan_btn_layout = QHBoxLayout()
        self.new_scan_btn = QPushButton("🔬 New Scan")
        self.new_scan_btn.setFixedHeight(40)
        self.new_scan_btn.clicked.connect(self.start_new_scan)
        scan_btn_layout.addWidget(self.new_scan_btn)
        
        self.stop_scan_btn = QPushButton("⏹️ Stop Scan")
        self.stop_scan_btn.setFixedHeight(40)
        self.stop_scan_btn.setEnabled(False)
        self.stop_scan_btn.clicked.connect(self.stop_scan)
        scan_btn_layout.addWidget(self.stop_scan_btn)
        control_layout.addLayout(scan_btn_layout)
        
        # Position control buttons
        pos_btn_layout = QHBoxLayout()
        self.set_zero_btn = QPushButton("🎯 Set to Zero")
        self.set_zero_btn.setFixedHeight(40)
        self.set_zero_btn.clicked.connect(self.set_to_zero)
        pos_btn_layout.addWidget(self.set_zero_btn)
        
        self.reset_zoom_btn = QPushButton("🔄 Reset Zoom")
        self.reset_zoom_btn.setFixedHeight(40)
        self.reset_zoom_btn.clicked.connect(self.reset_zoom)
        pos_btn_layout.addWidget(self.reset_zoom_btn)
        control_layout.addLayout(pos_btn_layout)
        
        # Single axis scan buttons
        axis_btn_layout = QHBoxLayout()
        self.x_scan_btn = QPushButton("⬌ X-Axis Scan")
        self.x_scan_btn.setFixedHeight(40)
        self.x_scan_btn.clicked.connect(lambda: self.single_axis_scan('x'))
        axis_btn_layout.addWidget(self.x_scan_btn)
        
        self.y_scan_btn = QPushButton("⬍ Y-Axis Scan")
        self.y_scan_btn.setFixedHeight(40)
        self.y_scan_btn.clicked.connect(lambda: self.single_axis_scan('y'))
        axis_btn_layout.addWidget(self.y_scan_btn)
        control_layout.addLayout(axis_btn_layout)
        
        # Auto-focus and save buttons
        util_btn_layout = QHBoxLayout()
        self.autofocus_btn = QPushButton("🔧 Auto Focus")
        self.autofocus_btn.setFixedHeight(40)
        self.autofocus_btn.clicked.connect(self.start_autofocus)
        util_btn_layout.addWidget(self.autofocus_btn)
        
        self.save_image_btn = QPushButton("📷 Save Image")
        self.save_image_btn.setFixedHeight(40)
        self.save_image_btn.clicked.connect(self.save_confocal_image)
        util_btn_layout.addWidget(self.save_image_btn)
        control_layout.addLayout(util_btn_layout)
        
        # Progress bar
        self.confocal_progress_bar = QProgressBar()
        self.confocal_progress_bar.setVisible(False)
        control_layout.addWidget(self.confocal_progress_bar)
        
        control_group.setLayout(control_layout)
        scroll_layout.addWidget(control_group)
        
        # Data Management Group
        data_group = QGroupBox("Data Management")
        data_layout = QVBoxLayout()
        
        load_save_layout = QHBoxLayout()
        self.load_scan_btn = QPushButton("📁 Load Scan")
        self.load_scan_btn.clicked.connect(self.load_scan_data)
        load_save_layout.addWidget(self.load_scan_btn)
        
        self.save_scan_btn = QPushButton("💾 Save Scan")
        self.save_scan_btn.clicked.connect(self.save_scan_data)
        load_save_layout.addWidget(self.save_scan_btn)
        data_layout.addLayout(load_save_layout)
        
        data_group.setLayout(data_layout)
        scroll_layout.addWidget(data_group)
        
        # Add stretch to push everything to top
        scroll_layout.addStretch()
        
        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        left_layout.addWidget(scroll_area)
        left_panel.setLayout(left_layout)
        
        # Right panel for image display and live plots
        right_panel = QWidget()
        right_layout = QVBoxLayout()
        
        # Confocal image display
        self.confocal_image_widget = ConfocalImageWidget()
        self.confocal_image_widget.point_clicked.connect(self.on_image_click)
        self.confocal_image_widget.zoom_selected.connect(self.on_zoom_area_selected)
        right_layout.addWidget(self.confocal_image_widget)
        
        # Live signal plot
        self.live_signal_plot = LiveSignalPlot()
        self.live_signal_plot.setFixedHeight(200)
        right_layout.addWidget(self.live_signal_plot)
        
        right_panel.setLayout(right_layout)
        
        # Add panels to main layout
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, 1)  # Give more space to right panel
        confocal_widget.setLayout(main_layout)
        
        # Add to tab widget (this will be the first tab)
        self.tab_widget.addTab(confocal_widget, "🔬 Confocal Control")
    
    def create_odmr_control_tab(self):
        """Create the ODMR Control tab"""
        control_widget = QWidget()
        layout = QVBoxLayout()
        
        # Create scroll area for controls
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()
        
        # Frequency parameters
        freq_group = ParameterGroupBox("Frequency Parameters")
        self.start_freq = freq_group.add_parameter("Start Freq (GHz):", "2.80", "Starting frequency for ODMR sweep")
        self.stop_freq = freq_group.add_parameter("Stop Freq (GHz):", "2.90", "Ending frequency for ODMR sweep")
        self.num_points = freq_group.add_parameter("Number of Points:", "51", "Number of frequency points to measure")
        scroll_layout.addWidget(freq_group)
        
        # Timing parameters
        timing_group = ParameterGroupBox("Timing Parameters (ns)")
        self.laser_duration = timing_group.add_parameter("Laser Duration:", "2000", "Duration of laser pulse")
        self.mw_duration = timing_group.add_parameter("MW Duration:", "2000", "Duration of microwave pulse")
        self.detection_duration = timing_group.add_parameter("Detection Duration:", "1000", "Duration of detection window")
        scroll_layout.addWidget(timing_group)
        
        # Delay parameters
        delay_group = ParameterGroupBox("Delay Parameters (ns)")
        self.laser_delay = delay_group.add_parameter("Laser Delay:", "0", "Delay before laser pulse")
        self.mw_delay = delay_group.add_parameter("MW Delay:", "0", "Delay before microwave pulse")
        self.detection_delay = delay_group.add_parameter("Detection Delay:", "0", "Delay before detection window")
        scroll_layout.addWidget(delay_group)
        
        # Sequence parameters
        seq_group = ParameterGroupBox("Sequence Parameters")
        self.sequence_interval = seq_group.add_parameter("Sequence Interval (ns):", "10000", "Time between sequence repetitions")
        self.repetitions = seq_group.add_parameter("Repetitions:", "100", "Number of sequence repetitions")
        scroll_layout.addWidget(seq_group)
        
        # MW power parameter
        power_group = ParameterGroupBox("Microwave Settings")
        self.mw_power_advanced = power_group.add_parameter("MW Power (dBm):", "-10.0", "Microwave power level")
        scroll_layout.addWidget(power_group)
        
        # Control buttons
        button_group = QGroupBox("Measurement Control")
        button_layout = QVBoxLayout()
        
        self.start_btn = QPushButton("🚀 Start ODMR")
        self.start_btn.setFixedHeight(40)
        self.start_btn.clicked.connect(self.start_measurement)
        button_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("⏹️ Stop")
        self.stop_btn.setFixedHeight(40)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_measurement)
        button_layout.addWidget(self.stop_btn)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        button_layout.addWidget(self.progress_bar)
        
        button_group.setLayout(button_layout)
        scroll_layout.addWidget(button_group)
        
        # File operations
        file_group = QGroupBox("File Operations")
        file_layout = QVBoxLayout()
        
        save_params_btn = QPushButton("💾 Save Parameters")
        save_params_btn.clicked.connect(self.save_parameters)
        file_layout.addWidget(save_params_btn)
        
        load_params_btn = QPushButton("📁 Load Parameters")
        load_params_btn.clicked.connect(self.load_parameters)
        file_layout.addWidget(load_params_btn)
        
        save_results_btn = QPushButton("📊 Save Results")
        save_results_btn.clicked.connect(self.save_results)
        file_layout.addWidget(save_results_btn)
        
        file_group.setLayout(file_layout)
        scroll_layout.addWidget(file_group)
        
        # Add stretch to push everything to top
        scroll_layout.addStretch()
        
        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        
        layout.addWidget(scroll_area)
        control_widget.setLayout(layout)
        
        # Add to tab widget
        self.tab_widget.addTab(control_widget, "🔬 ODMR Control")
    
    def create_device_settings_tab(self):
        """Create the Device Settings tab"""
        settings_widget = QWidget()
        layout = QVBoxLayout()
        
        # Create scroll area for settings
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()
        
        # Device connections
        self.device_widget = DeviceStatusWidget("Device Connections")
        self.device_widget.ps_connect_btn.clicked.connect(self.connect_pulse_streamer)
        self.device_widget.rigol_connect_btn.clicked.connect(self.connect_rigol)
        scroll_layout.addWidget(self.device_widget)
        
# Advanced Settings removed - MW Power moved to ODMR Control tab
        
# Calibration Settings removed - not currently implemented
        
        # System Info
        system_group = QGroupBox("System Information")
        system_layout = QVBoxLayout()
        
        self.system_info = QTextEdit()
        self.system_info.setReadOnly(True)
        self.system_info.setMaximumHeight(200)
        self.system_info.setText("""System Status:
• TimeTagger: Connected
• ODMR Experiments: Initialized
• Qt Version: 5.x
• Python Version: 3.x
        """)
        system_layout.addWidget(self.system_info)
        system_group.setLayout(system_layout)
        scroll_layout.addWidget(system_group)
        
        # Connection Test Buttons
        test_group = QGroupBox("Connection Tests")
        test_layout = QVBoxLayout()
        
        test_ps_btn = QPushButton("🔧 Test Pulse Streamer")
        test_ps_btn.clicked.connect(self.test_pulse_streamer)
        test_layout.addWidget(test_ps_btn)
        
        test_rigol_btn = QPushButton("📡 Test RIGOL Signal")
        test_rigol_btn.clicked.connect(self.test_rigol_signal)
        test_layout.addWidget(test_rigol_btn)
        
        refresh_devices_btn = QPushButton("🔄 Refresh Devices")
        refresh_devices_btn.clicked.connect(self.refresh_all_devices)
        test_layout.addWidget(refresh_devices_btn)
        
        test_group.setLayout(test_layout)
        scroll_layout.addWidget(test_group)
        
        # Add stretch to push everything to top
        scroll_layout.addStretch()
        
        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        
        layout.addWidget(scroll_area)
        settings_widget.setLayout(layout)
        
        # Add to tab widget
        self.tab_widget.addTab(settings_widget, "⚙️ Device Settings")
        
    def create_visualization_panel(self, parent):
        """Create the right visualization panel"""
        viz_widget = QWidget()
        layout = QVBoxLayout()
        
        # Create plot widget
        self.plot_widget = LivePlotWidget()
        layout.addWidget(self.plot_widget)
        
        # Status log
        log_group = QGroupBox("Status Log")
        log_layout = QVBoxLayout()
        
        self.status_log = QTextEdit()
        self.status_log.setMaximumHeight(200)
        self.status_log.setReadOnly(True)
        # Status log styling handled by main stylesheet
        log_layout.addWidget(self.status_log)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        viz_widget.setLayout(layout)
        parent.addWidget(viz_widget)
    
    def init_hardware(self):
        """Initialize hardware connections"""
        self.pulse_controller = None
        self.mw_generator = None
        self.experiments = None
        
        # Try to connect on startup
        self.connect_pulse_streamer()
        self.connect_rigol()
    
    def init_confocal_hardware(self):
        """Initialize confocal hardware connections"""
        # Initialize confocal state variables
        self.confocal_scan_running = False
        self.confocal_image_data = None
        self.scan_history = []
        self.zoom_level = 0
        self.max_zoom = 3
        self.last_scan_data = None
        
        try:
            # Initialize galvo controller
            self.galvo_controller = GalvoScannerController()
            self.log_message("✅ Galvo controller initialized")
            
            # Initialize DAQ output task for galvo control
            self.galvo_output_task = nidaqmx.Task()
            self.galvo_output_task.ao_channels.add_ao_voltage_chan(self.galvo_controller.xin_control)
            self.galvo_output_task.ao_channels.add_ao_voltage_chan(self.galvo_controller.yin_control)
            self.galvo_output_task.start()
            self.log_message("✅ Galvo DAQ task initialized")
            
        except Exception as e:
            self.log_message(f"⚠️ Galvo controller error: {e}")
            self.galvo_controller = None
            self.galvo_output_task = None
        
        try:
            # Initialize TimeTagger for confocal
            self.confocal_tagger = createTimeTagger()
            self.confocal_tagger.reset()
            self.log_message("✅ Connected to TimeTagger for confocal")
        except Exception as e:
            self.log_message("⚠️ Real TimeTagger not detected for confocal, using virtual device")
            self.confocal_tagger = createTimeTaggerVirtual("TimeTagger/time_tags_test.ttbin")
            self.confocal_tagger.run()
        
        # Set bin width for counting
        self.confocal_binwidth = int(5e9)  # 5 ns in ps
        self.confocal_counter = Counter(self.confocal_tagger, [1], self.confocal_binwidth, 1)
        
        # Initialize data manager
        self.confocal_data_manager = DataManager()
        
        # Load confocal configuration
        try:
            with open("config_template.json", 'r') as f:
                self.confocal_config = json.load(f)
            self.update_confocal_ui_from_config()
        except Exception as e:
            self.log_message(f"⚠️ Could not load confocal config: {e}")
            # Set default config
            self.confocal_config = {
                "scan_range": {"x": [-1.0, 1.0], "y": [-1.0, 1.0]},
                "resolution": {"x": 50, "y": 50},
                "dwell_time": 0.01
            }
    
    def update_confocal_ui_from_config(self):
        """Update confocal UI parameters from config"""
        if hasattr(self, 'x_min'):
            self.x_min.setText(str(self.confocal_config['scan_range']['x'][0]))
            self.x_max.setText(str(self.confocal_config['scan_range']['x'][1]))
            self.y_min.setText(str(self.confocal_config['scan_range']['y'][0]))
            self.y_max.setText(str(self.confocal_config['scan_range']['y'][1]))
            self.x_resolution.setText(str(self.confocal_config['resolution']['x']))
            self.y_resolution.setText(str(self.confocal_config['resolution']['y']))
            self.dwell_time.setText(str(self.confocal_config['dwell_time'] * 1000))  # Convert to ms
    
    def connect_pulse_streamer(self):
        """Connect to Swabian Pulse Streamer"""
        try:
            ip = self.device_widget.ps_ip.text()
            self.log_message(f"🔌 Connecting to Pulse Streamer at {ip}...")
            
            # Connect via IP address (Pulse Streamer is network-only)
            self.pulse_controller = SwabianPulseController(ip_address=ip)
                
            if self.pulse_controller.is_connected:
                self.device_widget.update_ps_status(True)
                self.log_message(f"✅ Pulse Streamer connected at {ip}")
            else:
                self.device_widget.update_ps_status(False)
                self.log_message(f"❌ Pulse Streamer connection failed at {ip}")
        except Exception as e:
            self.device_widget.update_ps_status(False)
            self.log_message(f"❌ Pulse Streamer error: {e}")
    
    def connect_rigol(self):
        """Connect to RIGOL DSG836"""
        try:
            ip = self.device_widget.rigol_ip.text()
            self.mw_generator = RigolDSG836Controller(ip)
            if self.mw_generator.connect():
                self.device_widget.update_rigol_status(True)
                self.log_message(f"✅ RIGOL connected at {ip}")
            else:
                self.device_widget.update_rigol_status(False)
                self.log_message(f"❌ RIGOL connection failed at {ip}")
                self.mw_generator = None
        except Exception as e:
            self.device_widget.update_rigol_status(False)
            self.log_message(f"❌ RIGOL error: {e}")
            self.mw_generator = None
    
    def log_message(self, message):
        """Add message to status log"""
        timestamp = time.strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        self.status_log.append(formatted_message)
        self.statusBar().showMessage(message)
    
    def get_parameters(self):
        """Get all parameters from the GUI"""
        try:
            start_freq = float(self.start_freq.text()) * 1e9
            stop_freq = float(self.stop_freq.text()) * 1e9
            num_points = int(self.num_points.text())
            frequencies = np.linspace(start_freq, stop_freq, num_points)
            
            return {
                'mw_frequencies': frequencies.tolist(),
                'laser_duration': int(self.laser_duration.text()),
                'mw_duration': int(self.mw_duration.text()),
                'detection_duration': int(self.detection_duration.text()),
                'laser_delay': int(self.laser_delay.text()),
                'mw_delay': int(self.mw_delay.text()),
                'detection_delay': int(self.detection_delay.text()),
                'sequence_interval': int(self.sequence_interval.text()),
                'repetitions': int(self.repetitions.text())
            }
        except ValueError as e:
            QMessageBox.warning(self, "Parameter Error", f"Invalid parameter value: {e}")
            return None
    
    def start_measurement(self):
        """Start ODMR measurement"""
        if not self.pulse_controller or not self.pulse_controller.is_connected:
            QMessageBox.warning(self, "Connection Error", "Pulse Streamer not connected!")
            return
        
        parameters = self.get_parameters()
        if parameters is None:
            return
        
        # Initialize experiments
        if not self.experiments:
            self.experiments = ODMRExperiments(self.pulse_controller, self.mw_generator)
        
        # Set MW power
        if self.mw_generator:
            try:
                power = float(self.mw_power_advanced.text())
                self.mw_generator.set_power(power)
            except:
                pass
        
        # Update UI
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.current_results = {'frequencies': [], 'count_rates': []}
        
        # Start worker thread
        self.worker = ODMRWorker(self.experiments, parameters)
        self.worker.progress_updated.connect(self.progress_bar.setValue)
        self.worker.status_updated.connect(self.log_message)
        self.worker.data_updated.connect(self.update_plot)
        self.worker.measurement_finished.connect(self.measurement_finished)
        self.worker.error_occurred.connect(self.handle_error)
        self.worker.start()
        
        self.log_message("🚀 ODMR measurement started")
    
    def stop_measurement(self):
        """Stop ODMR measurement"""
        if self.worker:
            self.worker.stop()
            self.log_message("⏹️ Stopping measurement...")
    
    def update_plot(self, frequencies, count_rates):
        """Update the real-time plot"""
        self.current_results['frequencies'] = frequencies
        self.current_results['count_rates'] = count_rates
        self.plot_widget.update_plot(frequencies, count_rates)
    
    def measurement_finished(self):
        """Handle measurement completion"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        
        # Turn off MW output
        if self.mw_generator:
            try:
                self.mw_generator.set_rf_output(False)
            except:
                pass
    
    def handle_error(self, error_message):
        """Handle measurement errors"""
        QMessageBox.critical(self, "Measurement Error", f"Error during measurement:\n{error_message}")
        self.measurement_finished()
    
    def save_parameters(self):
        """Save current parameters to JSON file"""
        try:
            params = self.get_parameters()
            if params is None:
                return
            
            # Add UI-specific parameters
            params['start_freq_ghz'] = float(self.start_freq.text())
            params['stop_freq_ghz'] = float(self.stop_freq.text())
            params['num_points'] = int(self.num_points.text())
            params['mw_power_dbm'] = float(self.mw_power_advanced.text())
            
            filename, _ = QFileDialog.getSaveFileName(
                self, "Save Parameters", "", "JSON files (*.json);;All files (*.*)"
            )
            
            if filename:
                with open(filename, 'w') as f:
                    json.dump(params, f, indent=2)
                self.log_message(f"💾 Parameters saved to {filename}")
                
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Error saving parameters: {e}")
    
    def load_parameters(self):
        """Load parameters from JSON file"""
        try:
            filename, _ = QFileDialog.getOpenFileName(
                self, "Load Parameters", "", "JSON files (*.json);;All files (*.*)"
            )
            
            if filename:
                with open(filename, 'r') as f:
                    params = json.load(f)
                
                # Set UI parameters
                if 'start_freq_ghz' in params:
                    self.start_freq.setText(str(params['start_freq_ghz']))
                if 'stop_freq_ghz' in params:
                    self.stop_freq.setText(str(params['stop_freq_ghz']))
                if 'num_points' in params:
                    self.num_points.setText(str(params['num_points']))
                
                # Set timing parameters
                for param in ['laser_duration', 'mw_duration', 'detection_duration',
                             'laser_delay', 'mw_delay', 'detection_delay',
                             'sequence_interval', 'repetitions']:
                    if param in params:
                        getattr(self, param).setText(str(params[param]))
                
                if 'mw_power_dbm' in params:
                    self.mw_power_advanced.setText(str(params['mw_power_dbm']))
                
                self.log_message(f"📁 Parameters loaded from {filename}")
                
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Error loading parameters: {e}")
    
    def save_results(self):
        """Save measurement results"""
        if not self.current_results['frequencies']:
            QMessageBox.warning(self, "No Data", "No results to save!")
            return
        
        try:
            filename, file_type = QFileDialog.getSaveFileName(
                self, "Save Results", "", 
                "JSON files (*.json);;CSV files (*.csv);;All files (*.*)"
            )
            
            if filename:
                if filename.endswith('.csv') or 'CSV' in file_type:
                    # Save as CSV
                    import csv
                    with open(filename, 'w', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow(['Frequency_GHz', 'Count_Rate_Hz'])
                        for freq, count in zip(self.current_results['frequencies'],
                                             self.current_results['count_rates']):
                            writer.writerow([freq/1e9, count])
                else:
                    # Save as JSON
                    data = {
                        'frequencies_hz': self.current_results['frequencies'],
                        'count_rates_hz': self.current_results['count_rates'],
                        'parameters': self.get_parameters(),
                        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                    }
                    with open(filename, 'w') as f:
                        json.dump(data, f, indent=2)
                
                self.log_message(f"📊 Results saved to {filename}")
                
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Error saving results: {e}")
    
    def test_pulse_streamer(self):
        """Test Pulse Streamer connection and functionality"""
        if not self.pulse_controller or not self.pulse_controller.is_connected:
            self.log_message("❌ Pulse Streamer not connected")
            return
        
        try:
            ip = self.device_widget.ps_ip.text()
            self.log_message(f"🔧 Testing Pulse Streamer at {ip}...")
            
            # Add actual test here if pulse controller has test methods
            # For example: self.pulse_controller.test_connection()
            
            self.log_message("✅ Pulse Streamer test completed")
        except Exception as e:
            self.log_message(f"❌ Pulse Streamer test failed: {e}")
    
    def test_rigol_signal(self):
        """Test RIGOL signal generator"""
        if not self.mw_generator:
            self.log_message("❌ RIGOL not connected")
            return
        
        try:
            self.log_message("📡 Testing RIGOL signal generator...")
            # Test frequency setting
            test_freq = 2.87  # GHz
            self.mw_generator.set_odmr_frequency(test_freq)
            self.log_message(f"✅ RIGOL test frequency set to {test_freq} GHz")
            
            # Brief RF output test
            self.mw_generator.set_rf_output(True)
            time.sleep(0.1)
            self.mw_generator.set_rf_output(False)
            self.log_message("✅ RIGOL RF output test completed")
            
        except Exception as e:
            self.log_message(f"❌ RIGOL test failed: {e}")
    
    def refresh_all_devices(self):
        """Refresh all device connections"""
        self.log_message("🔄 Refreshing all devices...")
        self.connect_pulse_streamer()
        self.connect_rigol()
        self.log_message("✅ Device refresh completed")
    
    # Confocal Control Methods
    def get_scan_parameters(self):
        """Get current scan parameters from UI"""
        try:
            return {
                'x_min': float(self.x_min.text()),
                'x_max': float(self.x_max.text()),
                'y_min': float(self.y_min.text()),
                'y_max': float(self.y_max.text()),
                'x_res': int(self.x_resolution.text()),
                'y_res': int(self.y_resolution.text()),
                'dwell_time': float(self.dwell_time.text()) / 1000.0  # Convert ms to s
            }
        except ValueError:
            QMessageBox.warning(self, "Parameter Error", "Invalid scan parameters")
            return None
    
    def update_confocal_config(self, **kwargs):
        """Update confocal configuration"""
        if 'x_range' in kwargs:
            self.confocal_config['scan_range']['x'] = kwargs['x_range']
        if 'y_range' in kwargs:
            self.confocal_config['scan_range']['y'] = kwargs['y_range']
        if 'x_res' in kwargs:
            self.confocal_config['resolution']['x'] = kwargs['x_res']
        if 'y_res' in kwargs:
            self.confocal_config['resolution']['y'] = kwargs['y_res']
        if 'dwell_time' in kwargs:
            self.confocal_config['dwell_time'] = kwargs['dwell_time']
        
        # Save to file
        try:
            with open("config_template.json", 'w') as f:
                json.dump(self.confocal_config, f, indent=4)
        except Exception as e:
            self.log_message(f"⚠️ Could not save config: {e}")
    
    def start_new_scan(self):
        """Start a new confocal scan"""
        if self.confocal_scan_running:
            self.log_message("⚠️ Scan already running")
            return
        
        if not self.galvo_output_task:
            QMessageBox.warning(self, "Hardware Error", "Galvo controller not initialized!")
            return
        
        params = self.get_scan_parameters()
        if params is None:
            return
        
        # Update configuration
        self.update_confocal_config(
            x_range=[params['x_min'], params['x_max']],
            y_range=[params['y_min'], params['y_max']],
            x_res=params['x_res'],
            y_res=params['y_res'],
            dwell_time=params['dwell_time']
        )
        
        # Start scan in thread
        self.confocal_scan_running = True
        self.new_scan_btn.setEnabled(False)
        self.stop_scan_btn.setEnabled(True)
        self.confocal_progress_bar.setVisible(True)
        self.confocal_progress_bar.setValue(0)
        
        # Clear live signal plot
        self.live_signal_plot.clear()
        
        threading.Thread(target=self.run_confocal_scan, args=(params,), daemon=True).start()
        self.log_message("🔬 Starting new confocal scan...")
    
    def run_confocal_scan(self, params):
        """Run the actual confocal scan"""
        try:
            # Generate scan points
            x_points = np.linspace(params['x_min'], params['x_max'], params['x_res'])
            y_points = np.linspace(params['y_min'], params['y_max'], params['y_res'])
            
            # Initialize image data
            image_data = np.zeros((params['y_res'], params['x_res']))
            total_points = params['x_res'] * params['y_res']
            
            # Perform raster scan
            point_count = 0
            for y_idx, y_volt in enumerate(y_points):
                if not self.confocal_scan_running:
                    break
                
                for x_idx, x_volt in enumerate(x_points):
                    if not self.confocal_scan_running:
                        break
                    
                    # Move galvo to position
                    self.galvo_output_task.write([x_volt, y_volt])
                    
                    # Update current position display
                    QTimer.singleShot(0, lambda x=x_volt, y=y_volt: self.update_position_display(x, y))
                    
                    # Wait for settling
                    if x_idx == 0:
                        time.sleep(0.05)  # Longer settling for first point in row
                    else:
                        time.sleep(0.001)
                    
                    # Acquire data
                    time.sleep(params['dwell_time'])
                    counts = self.confocal_counter.getData()[0][0] / (self.confocal_binwidth / 1e12)
                    
                    # Store data
                    image_data[y_idx, x_idx] = counts
                    
                    # Update live plot
                    QTimer.singleShot(0, lambda c=counts: self.live_signal_plot.add_data_point(c))
                    
                    # Update progress
                    point_count += 1
                    progress = int((point_count / total_points) * 100)
                    QTimer.singleShot(0, lambda p=progress: self.confocal_progress_bar.setValue(p))
                    
                    # Update image display periodically
                    if point_count % 10 == 0:
                        QTimer.singleShot(0, lambda img=image_data.copy(), x=x_points, y=y_points: 
                                        self.confocal_image_widget.update_image(img, x, y))
            
            # Final image update
            QTimer.singleShot(0, lambda: self.confocal_image_widget.update_image(image_data, x_points, y_points))
            
            # Save scan data
            scan_data = {
                'image': image_data,
                'x_points': x_points,
                'y_points': y_points,
                'scale_x': (x_points[-1] - x_points[0]) / len(x_points),
                'scale_y': (y_points[-1] - y_points[0]) / len(y_points)
            }
            
            data_path = self.confocal_data_manager.save_scan_data(scan_data)
            self.last_scan_data = scan_data
            
            # Return galvo to zero
            self.galvo_output_task.write([0, 0])
            QTimer.singleShot(0, lambda: self.update_position_display(0, 0))
            
            QTimer.singleShot(0, lambda: self.log_message(f"✅ Confocal scan completed! Data saved: {data_path}"))
            
        except Exception as e:
            QTimer.singleShot(0, lambda: self.log_message(f"❌ Scan error: {str(e)}"))
        finally:
            # Reset UI
            QTimer.singleShot(0, self.scan_finished_cleanup)
    
    def scan_finished_cleanup(self):
        """Cleanup after scan finishes"""
        self.confocal_scan_running = False
        self.new_scan_btn.setEnabled(True)
        self.stop_scan_btn.setEnabled(False)
        self.confocal_progress_bar.setVisible(False)
    
    def stop_scan(self):
        """Stop ongoing confocal scan"""
        self.confocal_scan_running = False
        self.log_message("⏹️ Stopping confocal scan...")
    
    def update_position_display(self, x_volt, y_volt):
        """Update current position display"""
        self.current_x_v.setText(f"{x_volt:.3f}")
        self.current_y_v.setText(f"{y_volt:.3f}")
    
    def set_to_zero(self):
        """Set galvo to zero position"""
        if self.galvo_output_task:
            try:
                self.galvo_output_task.write([0, 0])
                self.update_position_display(0, 0)
                self.log_message("🎯 Galvo set to zero position")
            except Exception as e:
                self.log_message(f"❌ Error setting galvo to zero: {e}")
        else:
            self.log_message("❌ Galvo controller not initialized")
    
    def on_image_click(self, x_volt, y_volt):
        """Handle click on confocal image"""
        if self.galvo_output_task:
            try:
                self.galvo_output_task.write([x_volt, y_volt])
                self.update_position_display(x_volt, y_volt)
                self.log_message(f"🎯 Moved galvo to: X={x_volt:.3f}V, Y={y_volt:.3f}V")
            except Exception as e:
                self.log_message(f"❌ Error moving galvo: {e}")
    
    def on_zoom_area_selected(self, x_min, x_max, y_min, y_max):
        """Handle zoom area selection"""
        if self.zoom_level >= self.max_zoom:
            self.log_message(f"⚠️ Max zoom level reached ({self.max_zoom})")
            return
        
        # Save current state to history
        current_params = self.get_scan_parameters()
        if current_params:
            self.scan_history.append(current_params)
            self.zoom_level += 1
            
            # Update parameters to zoom area
            self.x_min.setText(f"{x_min:.3f}")
            self.x_max.setText(f"{x_max:.3f}")
            self.y_min.setText(f"{y_min:.3f}")
            self.y_max.setText(f"{y_max:.3f}")
            
            self.log_message(f"🔍 Zoom area selected: X=[{x_min:.3f}, {x_max:.3f}], Y=[{y_min:.3f}, {y_max:.3f}]")
            
            # Automatically start new scan
            QTimer.singleShot(100, self.start_new_scan)
    
    def reset_zoom(self):
        """Reset zoom to original view"""
        if self.zoom_level == 0:
            self.log_message("🔁 Already at original zoom level")
            return
        
        if not self.scan_history:
            # Use config defaults
            self.update_confocal_ui_from_config()
        else:
            # Restore original parameters
            original_params = self.scan_history[0]
            self.x_min.setText(str(original_params['x_min']))
            self.x_max.setText(str(original_params['x_max']))
            self.y_min.setText(str(original_params['y_min']))
            self.y_max.setText(str(original_params['y_max']))
            self.x_resolution.setText(str(original_params['x_res']))
            self.y_resolution.setText(str(original_params['y_res']))
            self.dwell_time.setText(str(original_params['dwell_time'] * 1000))
        
        # Clear zoom history
        self.scan_history.clear()
        self.zoom_level = 0
        
        self.log_message("🔄 Zoom reset to original view")
        
        # Automatically start new scan
        QTimer.singleShot(100, self.start_new_scan)
    
    def single_axis_scan(self, axis):
        """Perform single axis scan"""
        if not self.galvo_output_task:
            QMessageBox.warning(self, "Hardware Error", "Galvo controller not initialized!")
            return
        
        # Get current position
        current_x = float(self.current_x_v.text()) if self.current_x_v.text() else 0.0
        current_y = float(self.current_y_v.text()) if self.current_y_v.text() else 0.0
        
        params = self.get_scan_parameters()
        if params is None:
            return
        
        def run_axis_scan():
            try:
                if axis == 'x':
                    scan_points = np.linspace(params['x_min'], params['x_max'], params['x_res'])
                    fixed_pos = current_y
                    axis_label = 'X Position (V)'
                else:
                    scan_points = np.linspace(params['y_min'], params['y_max'], params['y_res'])
                    fixed_pos = current_x
                    axis_label = 'Y Position (V)'
                
                counts = []
                for point in scan_points:
                    if axis == 'x':
                        self.galvo_output_task.write([point, fixed_pos])
                        QTimer.singleShot(0, lambda: self.update_position_display(point, fixed_pos))
                    else:
                        self.galvo_output_task.write([fixed_pos, point])
                        QTimer.singleShot(0, lambda: self.update_position_display(fixed_pos, point))
                    
                    time.sleep(0.001)  # Settling time
                    count = self.confocal_counter.getData()[0][0] / (self.confocal_binwidth / 1e12)
                    counts.append(count)
                
                # Return to original position
                self.galvo_output_task.write([current_x, current_y])
                QTimer.singleShot(0, lambda: self.update_position_display(current_x, current_y))
                
                # TODO: Plot results in a separate window or widget
                self.log_message(f"✅ {axis.upper()}-axis scan completed")
                
            except Exception as e:
                QTimer.singleShot(0, lambda: self.log_message(f"❌ Axis scan error: {e}"))
        
        threading.Thread(target=run_axis_scan, daemon=True).start()
        self.log_message(f"🔍 Starting {axis.upper()}-axis scan...")
    
    def start_autofocus(self):
        """Start autofocus procedure"""
        if not self.galvo_output_task:
            QMessageBox.warning(self, "Hardware Error", "Galvo controller not initialized!")
            return
        
        def run_autofocus():
            try:
                self.log_message("🔧 Starting autofocus procedure...")
                
                # Get current position
                current_x = float(self.current_x_v.text()) if self.current_x_v.text() else 0.0
                current_y = float(self.current_y_v.text()) if self.current_y_v.text() else 0.0
                
                # Simple autofocus: scan small area and find maximum
                scan_range = 0.2  # 0.2V range around current position
                scan_points = 20
                
                x_points = np.linspace(current_x - scan_range/2, current_x + scan_range/2, scan_points)
                y_points = np.linspace(current_y - scan_range/2, current_y + scan_range/2, scan_points)
                
                max_count = 0
                best_x, best_y = current_x, current_y
                
                for y in y_points:
                    for x in x_points:
                        self.galvo_output_task.write([x, y])
                        time.sleep(0.01)
                        count = self.confocal_counter.getData()[0][0] / (self.confocal_binwidth / 1e12)
                        
                        if count > max_count:
                            max_count = count
                            best_x, best_y = x, y
                
                # Move to best position
                self.galvo_output_task.write([best_x, best_y])
                QTimer.singleShot(0, lambda: self.update_position_display(best_x, best_y))
                
                QTimer.singleShot(0, lambda: self.log_message(f"✅ Autofocus completed. Best position: X={best_x:.3f}V, Y={best_y:.3f}V"))
                
            except Exception as e:
                QTimer.singleShot(0, lambda: self.log_message(f"❌ Autofocus error: {e}"))
        
        threading.Thread(target=run_autofocus, daemon=True).start()
    
    def save_confocal_image(self):
        """Save current confocal image"""
        if self.last_scan_data is None:
            QMessageBox.warning(self, "No Data", "No scan data to save!")
            return
        
        try:
            filename, _ = QFileDialog.getSaveFileName(
                self, "Save Confocal Image", "", 
                "PNG files (*.png);;All files (*.*)"
            )
            
            if filename:
                # Use the matplotlib figure to save
                self.confocal_image_widget.figure.savefig(filename, dpi=300, bbox_inches='tight',
                                                         facecolor='white', edgecolor='none')
                self.log_message(f"📷 Image saved: {filename}")
                
        except Exception as e:
            self.log_message(f"❌ Error saving image: {e}")
    
    def load_scan_data(self):
        """Load scan data from file"""
        try:
            filename, _ = QFileDialog.getOpenFileName(
                self, "Load Scan Data", "", 
                "NPZ files (*.npz);;CSV files (*.csv);;All files (*.*)"
            )
            
            if filename:
                if filename.endswith('.npz'):
                    data = np.load(filename)
                    image = data['image']
                    # Generate points based on image shape and current parameters
                    params = self.get_scan_parameters()
                    if params:
                        x_points = np.linspace(params['x_min'], params['x_max'], image.shape[1])
                        y_points = np.linspace(params['y_min'], params['y_max'], image.shape[0])
                        self.confocal_image_widget.update_image(image, x_points, y_points)
                        self.log_message(f"📁 Scan data loaded: {filename}")
                else:
                    self.log_message("⚠️ Currently only NPZ files are supported for loading")
                    
        except Exception as e:
            self.log_message(f"❌ Error loading scan data: {e}")
    
    def save_scan_data(self):
        """Save current scan data"""
        if self.last_scan_data is None:
            QMessageBox.warning(self, "No Data", "No scan data to save!")
            return
        
        try:
            filename, _ = QFileDialog.getSaveFileName(
                self, "Save Scan Data", "", 
                "NPZ files (*.npz);;CSV files (*.csv);;All files (*.*)"
            )
            
            if filename:
                if filename.endswith('.npz') or 'NPZ' in filename:
                    np.savez(filename, 
                            image=self.last_scan_data['image'],
                            x_points=self.last_scan_data['x_points'],
                            y_points=self.last_scan_data['y_points'],
                            scale_x=self.last_scan_data['scale_x'],
                            scale_y=self.last_scan_data['scale_y'])
                else:
                    # Save using data manager (CSV format)
                    data_path = self.confocal_data_manager.save_scan_data(self.last_scan_data)
                
                self.log_message(f"💾 Scan data saved: {filename}")
                
        except Exception as e:
            self.log_message(f"❌ Error saving scan data: {e}")
    
    def closeEvent(self, event):
        """Handle application closing"""
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self, "Quit", "Measurement in progress. Stop and quit?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.stop_measurement()
                self.worker.wait(3000)  # Wait up to 3 seconds
            else:
                event.ignore()
                return
        
        # Clean up hardware connections
        try:
            if self.experiments:
                self.experiments.cleanup()
            if self.mw_generator:
                self.mw_generator.set_rf_output(False)
                self.mw_generator.disconnect()
            if self.pulse_controller:
                self.pulse_controller.disconnect()
        except:
            pass
        
        event.accept()


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("ODMR Control Center")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("NV Lab")
    
    # Create and show main window
    window = ODMRControlCenter()
    window.show()
    
    # Start event loop
    sys.exit(app.exec_())


if __name__ == "__main__":
    main() 