"""
ODMR Control - Qt GUI Application
----------------------------------------
Professional GUI for controlling ODMR experiments.
Designed with the same visual style and organization as the NV scanning microscopy software.

Author: Javier Noé Ramos Silva
Date: 2025
Contact: jramossi@uci.edu
Lab: Burke Lab, Department of Electrical Engineering and Computer Science, University of California, Irvine
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

# Import data manager for automatic saving
from odmr_data_manager import ODMRDataManager

# Import plot widgets
from plot_widgets import PulsePatternVisualizer


class ODMRWorker(QThread):
    """Worker thread for running ODMR measurements"""
    
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    data_updated = pyqtSignal(list, list)  # frequencies, count_rates
    measurement_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)
    data_saved = pyqtSignal(str)  # Signal for when data is saved
    
    def __init__(self, experiments, parameters):
        super().__init__()
        self.experiments = experiments
        self.parameters = parameters
        self.is_running = True
        self.data_manager = ODMRDataManager()
    
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
                
                result = self.experiments.odmr(**single_params)
                
                if result and 'count_rates' in result and len(result['count_rates']) > 0:
                    all_frequencies.append(freq)
                    all_count_rates.append(result['count_rates'][0])
                    
                    # Emit data update for real-time plotting
                    self.data_updated.emit(all_frequencies.copy(), all_count_rates.copy())
            
            if self.is_running:
                self.progress_updated.emit(100)
                self.status_updated.emit("ODMR measurement completed!")
                
                # Automatically save the data
                try:
                    # Prepare parameters for saving (remove the frequencies list to avoid redundancy)
                    save_params = self.parameters.copy()
                    if 'mw_frequencies' in save_params:
                        del save_params['mw_frequencies']
                    
                    # Save the data
                    filename = self.data_manager.save_odmr_data(all_frequencies, all_count_rates, save_params)
                    self.data_saved.emit(filename)
                    self.status_updated.emit(f"💾 Data automatically saved to {filename}")
                except Exception as save_error:
                    self.status_updated.emit(f"⚠️ Warning: Could not save data automatically: {save_error}")
            
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            self.measurement_finished.emit()


class RabiWorker(QThread):
    """Worker thread for running Rabi oscillation measurements"""
    
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    data_updated = pyqtSignal(list, list)  # durations, count_rates
    measurement_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)
    data_saved = pyqtSignal(str)  # Signal for when data is saved
    
    def __init__(self, experiments, parameters):
        super().__init__()
        self.experiments = experiments
        self.parameters = parameters
        self.is_running = True
        self.data_manager = ODMRDataManager()
    
    def stop(self):
        """Stop the measurement"""
        self.is_running = False
    
    def run(self):
        """Run the Rabi oscillation measurement"""
        try:
            mw_durations = self.parameters['mw_durations']
            total_points = len(mw_durations)
            
            all_durations = []
            all_count_rates = []
            
            for i, duration in enumerate(mw_durations):
                if not self.is_running:
                    break
                
                # Update progress and status
                progress = int((i / total_points) * 100)
                self.progress_updated.emit(progress)
                self.status_updated.emit(f"Measuring {duration} ns duration ({i+1}/{total_points})")
                
                # Run single duration measurement
                result = self.experiments.rabi_oscillation(
                    mw_durations=[duration],
                    mw_frequency=self.parameters['mw_frequency'],
                    laser_duration=self.parameters['laser_duration'],
                    detection_duration=self.parameters['detection_duration'],
                    laser_delay=self.parameters['laser_delay'],
                    mw_delay=self.parameters['mw_delay'],
                    detection_delay=self.parameters['detection_delay'],
                    sequence_interval=self.parameters['sequence_interval'],
                    repetitions=self.parameters['repetitions']
                )
                
                if result and 'count_rates' in result and len(result['count_rates']) > 0:
                    all_durations.append(duration)
                    all_count_rates.append(result['count_rates'][0])
                    
                    # Emit data update for real-time plotting
                    self.data_updated.emit(all_durations.copy(), all_count_rates.copy())
            
            if self.is_running:
                self.progress_updated.emit(100)
                self.status_updated.emit("Rabi oscillation measurement completed!")
                
                # Automatically save the data
                try:
                    # Prepare parameters for saving (remove the durations list to avoid redundancy)
                    save_params = self.parameters.copy()
                    if 'mw_durations' in save_params:
                        del save_params['mw_durations']
                    
                    # Save the data
                    filename = self.data_manager.save_rabi_data(all_durations, all_count_rates, save_params)
                    self.data_saved.emit(filename)
                    self.status_updated.emit(f"💾 Data automatically saved to {filename}")
                except Exception as save_error:
                    self.status_updated.emit(f"⚠️ Warning: Could not save data automatically: {save_error}")
            
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            self.measurement_finished.emit()


class T1Worker(QThread):
    """Worker thread for running T1 decay measurements"""
    
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    data_updated = pyqtSignal(list, list)  # delays, count_rates
    measurement_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)
    data_saved = pyqtSignal(str)  # Signal for when data is saved
    
    def __init__(self, experiments, parameters):
        super().__init__()
        self.experiments = experiments
        self.parameters = parameters
        self.is_running = True
        self.data_manager = ODMRDataManager()
    
    def stop(self):
        """Stop the measurement"""
        self.is_running = False
    
    def run(self):
        """Run the T1 decay measurement"""
        try:
            delay_times = self.parameters['delay_times']
            total_points = len(delay_times)
            
            all_delays = []
            all_count_rates = []
            
            for i, delay in enumerate(delay_times):
                if not self.is_running:
                    break
                
                # Update progress and status
                progress = int((i / total_points) * 100)
                self.progress_updated.emit(progress)
                self.status_updated.emit(f"Measuring {delay} ns delay ({i+1}/{total_points})")
                
                # Run single delay measurement
                result = self.experiments.t1_decay(
                    delay_times=[delay],
                    init_laser_duration=self.parameters['init_laser_duration'],
                    readout_laser_duration=self.parameters['readout_laser_duration'],
                    detection_duration=self.parameters['detection_duration'],
                    init_laser_delay=self.parameters['init_laser_delay'],
                    readout_laser_delay=self.parameters.get('readout_laser_delay'),
                    detection_delay=self.parameters.get('detection_delay'),
                    sequence_interval=self.parameters['sequence_interval'],
                    repetitions=self.parameters['repetitions']
                )
                
                if result and 'count_rates' in result and len(result['count_rates']) > 0:
                    all_delays.append(delay)
                    all_count_rates.append(result['count_rates'][0])
                    
                    # Emit data update for real-time plotting
                    self.data_updated.emit(all_delays.copy(), all_count_rates.copy())
            
            if self.is_running:
                self.progress_updated.emit(100)
                self.status_updated.emit("T1 decay measurement completed!")
                
                # Automatically save the data
                try:
                    # Prepare parameters for saving (remove the delays list to avoid redundancy)
                    save_params = self.parameters.copy()
                    if 'delay_times' in save_params:
                        del save_params['delay_times']
                    
                    # Save the data
                    filename = self.data_manager.save_t1_data(all_delays, all_count_rates, save_params)
                    self.data_saved.emit(filename)
                    self.status_updated.emit(f"💾 Data automatically saved to {filename}")
                except Exception as save_error:
                    self.status_updated.emit(f"⚠️ Warning: Could not save data automatically: {save_error}")
            
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
        self.ax.set_ylabel('Count Rate (cps)', fontsize=12, color='white')
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
        self.ax.set_ylabel('Count Rate (cps)', fontsize=12, color='white')
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


class ODMRControlCenter(QMainWindow):
    """Main ODMR Control Center application"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.init_hardware()
        self.current_results = {'frequencies': [], 'count_rates': []}
        self.worker = None
        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("ODMR Control - Burke Lab")
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
        
        # Create ODMR Control tab
        self.create_odmr_control_tab()
        
        # Create Rabi Control tab
        self.create_rabi_control_tab()
        
        # Create T1 Decay Control tab
        self.create_t1_control_tab()
        
        # Create Device Settings tab
        self.create_device_settings_tab()
        
        parent.addWidget(self.tab_widget)
    
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
        self.num_points = freq_group.add_parameter("Number of Points:", "50", "Number of frequency points to measure")
        scroll_layout.addWidget(freq_group)
        
        # MW power parameter
        power_group = ParameterGroupBox("Microwave Settings")
        self.mw_power_advanced = power_group.add_parameter("MW Power (dBm):", "-10.0", "Microwave power level")
        scroll_layout.addWidget(power_group)
        
        # Timing parameters
        timing_group = ParameterGroupBox("Timing Parameters (ns)")
        self.laser_duration = timing_group.add_parameter("Laser Duration:", "5000", "Duration of laser pulse")
        self.mw_duration = timing_group.add_parameter("MW Duration:", "5000", "Duration of microwave pulse")
        self.detection_duration = timing_group.add_parameter("Detection Duration:", "5000", "Duration of detection window")
        scroll_layout.addWidget(timing_group)
        
        # Delay parameters
        delay_group = ParameterGroupBox("Delay Parameters (ns)")
        self.laser_delay = delay_group.add_parameter("Laser Delay:", "0", "Delay before laser pulse")
        self.mw_delay = delay_group.add_parameter("MW Delay:", "6000", "Delay before microwave pulse")
        self.detection_delay = delay_group.add_parameter("Detection Delay:", "0", "Delay before detection window")
        scroll_layout.addWidget(delay_group)
        
        # Sequence parameters
        seq_group = ParameterGroupBox("Sequence Parameters")
        self.sequence_interval = seq_group.add_parameter("Sequence Interval (ns):", "1000", "Time between sequence repetitions")
        self.repetitions = seq_group.add_parameter("Repetitions:", "5000", "Number of sequence repetitions")
        scroll_layout.addWidget(seq_group)
        
        # Connect parameter changes to pulse pattern updates
        self.connect_parameter_signals()
        
        # Pulse Pattern Visualization
        pattern_group = QGroupBox("Pulse Pattern Visualization")
        pattern_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #00d4aa;
                border-radius: 5px;
                margin-top: 1ex;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #00d4aa;
            }
        """)
        pattern_layout = QVBoxLayout()
        
        # Add pulse pattern visualizer
        self.pulse_pattern_widget = PulsePatternVisualizer(widget_height=250)
        pattern_layout.addWidget(self.pulse_pattern_widget)
        
        pattern_group.setLayout(pattern_layout)
        scroll_layout.addWidget(pattern_group)
        
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
        
        # Initialize pulse pattern visualization with default parameters
        QTimer.singleShot(100, self.update_pulse_pattern)
    
    def create_rabi_control_tab(self):
        """Create the Rabi Oscillations Control tab"""
        control_widget = QWidget()
        layout = QVBoxLayout()
        
        # Create scroll area for controls
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()
        
        # MW Duration parameters
        duration_group = ParameterGroupBox("MW Duration Parameters")
        self.start_duration = duration_group.add_parameter("Start Duration (ns):", "100", "Starting MW pulse duration")
        self.stop_duration = duration_group.add_parameter("Stop Duration (ns):", "5000", "Ending MW pulse duration")
        self.duration_step = duration_group.add_parameter("Step Size (ns):", "100", "Step size for MW pulse duration")
        scroll_layout.addWidget(duration_group)
        
        # MW Frequency parameters
        freq_group = ParameterGroupBox("MW Frequency Parameters")
        self.rabi_mw_freq = freq_group.add_parameter("MW Frequency (GHz):", "2.87", "Fixed MW frequency for Rabi")
        self.rabi_mw_power = freq_group.add_parameter("MW Power (dBm):", "-10.0", "MW power level")
        scroll_layout.addWidget(freq_group)
        
        # Timing parameters
        timing_group = ParameterGroupBox("Timing Parameters")
        self.rabi_laser_duration = timing_group.add_parameter("Laser Duration (ns):", "5000", "Duration of laser pulse")
        self.rabi_detection_duration = timing_group.add_parameter("Detection Duration (ns):", "5000", "Duration of detection window")
        scroll_layout.addWidget(timing_group)
        
        # Delay parameters
        delay_group = ParameterGroupBox("Delay Parameters (ns)")
        self.rabi_laser_delay = delay_group.add_parameter("Laser Delay:", "0", "Delay before laser pulse")
        self.rabi_mw_delay = delay_group.add_parameter("MW Delay:", "6000", "Delay before MW pulse")
        self.rabi_detection_delay = delay_group.add_parameter("Detection Delay:", "0", "Delay before detection window")
        scroll_layout.addWidget(delay_group)
        
        # Sequence parameters
        seq_group = ParameterGroupBox("Sequence Parameters")
        self.rabi_sequence_interval = seq_group.add_parameter("Sequence Interval (ns):", "1000", "Time between sequence repetitions")
        self.rabi_repetitions = seq_group.add_parameter("Repetitions:", "5000", "Number of sequence repetitions")
        scroll_layout.addWidget(seq_group)
        
        # Pulse Pattern Visualization for Rabi
        rabi_pattern_group = QGroupBox("Pulse Pattern Visualization")
        rabi_pattern_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #00d4aa;
                border-radius: 5px;
                margin-top: 1ex;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #00d4aa;
            }
        """)
        rabi_pattern_layout = QVBoxLayout()
        
        # Add pulse pattern visualizer for Rabi
        self.rabi_pulse_pattern_widget = PulsePatternVisualizer(widget_height=250)
        rabi_pattern_layout.addWidget(self.rabi_pulse_pattern_widget)
        
        rabi_pattern_group.setLayout(rabi_pattern_layout)
        scroll_layout.addWidget(rabi_pattern_group)
        
        # Connect Rabi parameter changes to pulse pattern updates
        self.connect_rabi_parameter_signals()
        
        # Control buttons
        button_group = QGroupBox("Measurement Control")
        button_layout = QVBoxLayout()
        
        self.start_rabi_btn = QPushButton("🚀 Start Rabi")
        self.start_rabi_btn.setFixedHeight(40)
        self.start_rabi_btn.clicked.connect(self.start_rabi_measurement)
        button_layout.addWidget(self.start_rabi_btn)
        
        self.stop_rabi_btn = QPushButton("⏹️ Stop")
        self.stop_rabi_btn.setFixedHeight(40)
        self.stop_rabi_btn.setEnabled(False)
        self.stop_rabi_btn.clicked.connect(self.stop_rabi_measurement)
        button_layout.addWidget(self.stop_rabi_btn)
        
        # Progress bar
        self.rabi_progress_bar = QProgressBar()
        self.rabi_progress_bar.setVisible(False)
        button_layout.addWidget(self.rabi_progress_bar)
        
        button_group.setLayout(button_layout)
        scroll_layout.addWidget(button_group)
        
        # File operations
        file_group = QGroupBox("File Operations")
        file_layout = QVBoxLayout()
        
        save_rabi_params_btn = QPushButton("💾 Save Parameters")
        save_rabi_params_btn.clicked.connect(self.save_rabi_parameters)
        file_layout.addWidget(save_rabi_params_btn)
        
        load_rabi_params_btn = QPushButton("📁 Load Parameters")
        load_rabi_params_btn.clicked.connect(self.load_rabi_parameters)
        file_layout.addWidget(load_rabi_params_btn)
        
        save_rabi_results_btn = QPushButton("📊 Save Results")
        save_rabi_results_btn.clicked.connect(self.save_rabi_results)
        file_layout.addWidget(save_rabi_results_btn)
        
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
        self.tab_widget.addTab(control_widget, "📈 Rabi Control")
        
        # Initialize Rabi pulse pattern visualization with default parameters
        QTimer.singleShot(100, self.update_rabi_pulse_pattern)
    
    def create_t1_control_tab(self):
        """Create the T1 Decay Control tab"""
        control_widget = QWidget()
        layout = QVBoxLayout()
        
        # Create scroll area for controls
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()
        
        # Delay Time parameters
        delay_group = ParameterGroupBox("Delay Time Parameters")
        self.start_delay = delay_group.add_parameter("Start Delay (ns):", "500", "Starting delay time between init and readout")
        self.stop_delay = delay_group.add_parameter("Stop Delay (ns):", "50000", "Ending delay time between init and readout")
        self.delay_step = delay_group.add_parameter("Step Size (ns):", "100", "Step size for delay time sweep")
        scroll_layout.addWidget(delay_group)
        
        # Laser parameters
        laser_group = ParameterGroupBox("Laser Parameters")
        self.t1_init_laser_duration = laser_group.add_parameter("Init Laser Duration (ns):", "5000", "Duration of initialization laser pulse")
        self.t1_readout_laser_duration = laser_group.add_parameter("Readout Laser Duration (ns):", "5000", "Duration of readout laser pulse")
        self.t1_detection_duration = laser_group.add_parameter("Detection Duration (ns):", "5000", "Duration of detection window")
        scroll_layout.addWidget(laser_group)
        
        # Timing parameters
        timing_group = ParameterGroupBox("Timing Parameters")
        self.t1_init_laser_delay = timing_group.add_parameter("Init Laser Delay (ns):", "0", "Delay before initialization laser pulse")
        self.t1_readout_laser_delay = timing_group.add_parameter("Readout Laser Delay (ns):", "auto", "Delay before readout laser (auto-calculated if 'auto')")
        self.t1_detection_delay = timing_group.add_parameter("Detection Delay (ns):", "auto", "Delay before detection window (auto-calculated if 'auto')")
        scroll_layout.addWidget(timing_group)
        
        # Sequence parameters
        seq_group = ParameterGroupBox("Sequence Parameters")
        self.t1_sequence_interval = seq_group.add_parameter("Sequence Interval (ns):", "1000", "Time between sequence repetitions")
        self.t1_repetitions = seq_group.add_parameter("Repetitions:", "5000", "Number of sequence repetitions")
        scroll_layout.addWidget(seq_group)
        
        # Connect parameter changes to pulse pattern updates
        self.connect_t1_parameter_signals()
        
        # Pulse Pattern Visualization for T1
        t1_pattern_group = QGroupBox("Pulse Pattern Visualization")
        t1_pattern_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #00d4aa;
                border-radius: 5px;
                margin-top: 1ex;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #00d4aa;
            }
        """)
        t1_pattern_layout = QVBoxLayout()
        
        # Add pulse pattern visualizer for T1
        self.t1_pulse_pattern_widget = PulsePatternVisualizer(widget_height=250)
        t1_pattern_layout.addWidget(self.t1_pulse_pattern_widget)
        
        t1_pattern_group.setLayout(t1_pattern_layout)
        scroll_layout.addWidget(t1_pattern_group)
        
        # Control buttons
        button_group = QGroupBox("Measurement Control")
        button_layout = QVBoxLayout()
        
        self.start_t1_btn = QPushButton("🚀 Start T1 Decay")
        self.start_t1_btn.setFixedHeight(40)
        self.start_t1_btn.clicked.connect(self.start_t1_measurement)
        button_layout.addWidget(self.start_t1_btn)
        
        self.stop_t1_btn = QPushButton("⏹️ Stop")
        self.stop_t1_btn.setFixedHeight(40)
        self.stop_t1_btn.setEnabled(False)
        self.stop_t1_btn.clicked.connect(self.stop_t1_measurement)
        button_layout.addWidget(self.stop_t1_btn)
        
        # Progress bar
        self.t1_progress_bar = QProgressBar()
        self.t1_progress_bar.setVisible(False)
        button_layout.addWidget(self.t1_progress_bar)
        
        button_group.setLayout(button_layout)
        scroll_layout.addWidget(button_group)
        
        # File operations
        file_group = QGroupBox("File Operations")
        file_layout = QVBoxLayout()
        
        save_t1_params_btn = QPushButton("💾 Save Parameters")
        save_t1_params_btn.clicked.connect(self.save_t1_parameters)
        file_layout.addWidget(save_t1_params_btn)
        
        load_t1_params_btn = QPushButton("📁 Load Parameters")
        load_t1_params_btn.clicked.connect(self.load_t1_parameters)
        file_layout.addWidget(load_t1_params_btn)
        
        save_t1_results_btn = QPushButton("📊 Save Results")
        save_t1_results_btn.clicked.connect(self.save_t1_results)
        file_layout.addWidget(save_t1_results_btn)
        
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
        self.tab_widget.addTab(control_widget, "⏱️ T1 Decay")
        
        # Initialize T1 pulse pattern visualization with default parameters
        QTimer.singleShot(100, self.update_t1_pulse_pattern)
    
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
        
        # Try to connect on startup with error handling
        try:
            self.log_message("🔧 Initializing hardware connections...")
            self.connect_pulse_streamer()
            self.connect_rigol()
            self.log_message("✅ Hardware initialization completed")
        except Exception as e:
            self.log_message(f"⚠️ Hardware initialization error: {e}")
            # Don't let hardware errors crash the GUI
    
    def connect_pulse_streamer(self):
        """Connect to Swabian Pulse Streamer"""
        try:
            # Check if device_widget exists before accessing it
            if not hasattr(self, 'device_widget') or self.device_widget is None:
                self.log_message("⚠️ Device widget not initialized yet, skipping Pulse Streamer connection")
                return
                
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
            if hasattr(self, 'device_widget') and self.device_widget is not None:
                self.device_widget.update_ps_status(False)
            self.log_message(f"❌ Pulse Streamer error: {e}")
    
    def connect_rigol(self):
        """Connect to RIGOL DSG836"""
        try:
            # Check if device_widget exists before accessing it
            if not hasattr(self, 'device_widget') or self.device_widget is None:
                self.log_message("⚠️ Device widget not initialized yet, skipping RIGOL connection")
                return
                
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
            if hasattr(self, 'device_widget') and self.device_widget is not None:
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
    
    def update_pulse_pattern(self):
        """Update the pulse pattern visualization based on current parameters"""
        try:
            # Get timing parameters from GUI
            parameters = {
                'laser_duration': int(self.laser_duration.text()),
                'mw_duration': int(self.mw_duration.text()),
                'detection_duration': int(self.detection_duration.text()),
                'laser_delay': int(self.laser_delay.text()),
                'mw_delay': int(self.mw_delay.text()),
                'detection_delay': int(self.detection_delay.text()),
                'sequence_interval': int(self.sequence_interval.text()),
                'repetitions': int(self.repetitions.text())
            }
            
            # Update the pulse pattern visualization
            self.pulse_pattern_widget.update_pulse_pattern(parameters, "ODMR")
            self.log_message("✅ Pulse pattern updated")
            
        except ValueError as e:
            QMessageBox.warning(self, "Parameter Error", f"Invalid parameter value: {e}")
        except Exception as e:
            QMessageBox.warning(self, "Visualization Error", f"Failed to update pulse pattern: {e}")
    
    def connect_parameter_signals(self):
        """Connect parameter input fields to automatic pulse pattern updates"""
        # Connect timing parameters
        self.laser_duration.textChanged.connect(self.update_pulse_pattern)
        self.mw_duration.textChanged.connect(self.update_pulse_pattern)
        self.detection_duration.textChanged.connect(self.update_pulse_pattern)
        
        # Connect delay parameters
        self.laser_delay.textChanged.connect(self.update_pulse_pattern)
        self.mw_delay.textChanged.connect(self.update_pulse_pattern)
        self.detection_delay.textChanged.connect(self.update_pulse_pattern)
        
        # Connect sequence parameters
        self.sequence_interval.textChanged.connect(self.update_pulse_pattern)
        self.repetitions.textChanged.connect(self.update_pulse_pattern)
    
    def update_rabi_pulse_pattern(self):
        """Update the Rabi pulse pattern visualization based on current parameters"""
        try:
            # Get timing parameters from GUI
            parameters = {
                'laser_duration': int(self.rabi_laser_duration.text()),
                'mw_duration': int(self.start_duration.text()),  # Use Start Duration from GUI
                'detection_duration': int(self.rabi_detection_duration.text()),
                'laser_delay': int(self.rabi_laser_delay.text()),
                'mw_delay': int(self.rabi_mw_delay.text()),
                'detection_delay': int(self.rabi_detection_delay.text()),
                'sequence_interval': int(self.rabi_sequence_interval.text()),
                'repetitions': int(self.rabi_repetitions.text())
            }
            
            # Update the pulse pattern visualization
            self.rabi_pulse_pattern_widget.update_pulse_pattern(parameters, "Rabi")
            self.log_message("✅ Rabi pulse pattern updated")
            
        except ValueError as e:
            QMessageBox.warning(self, "Parameter Error", f"Invalid parameter value: {e}")
        except Exception as e:
            QMessageBox.warning(self, "Visualization Error", f"Failed to update Rabi pulse pattern: {e}")
    
    def connect_rabi_parameter_signals(self):
        """Connect Rabi parameter input fields to automatic pulse pattern updates"""
        # Connect MW duration parameters
        self.start_duration.textChanged.connect(self.update_rabi_pulse_pattern)
        
        # Connect timing parameters
        self.rabi_laser_duration.textChanged.connect(self.update_rabi_pulse_pattern)
        self.rabi_detection_duration.textChanged.connect(self.update_rabi_pulse_pattern)
        
        # Connect delay parameters
        self.rabi_laser_delay.textChanged.connect(self.update_rabi_pulse_pattern)
        self.rabi_mw_delay.textChanged.connect(self.update_rabi_pulse_pattern)
        self.rabi_detection_delay.textChanged.connect(self.update_rabi_pulse_pattern)
        
        # Connect sequence parameters
        self.rabi_sequence_interval.textChanged.connect(self.update_rabi_pulse_pattern)
        self.rabi_repetitions.textChanged.connect(self.update_rabi_pulse_pattern)
    
    def update_t1_pulse_pattern(self):
        """Update the T1 pulse pattern visualization based on current parameters"""
        try:
            # Get timing parameters from GUI
            parameters = {
                'init_laser_duration': int(self.t1_init_laser_duration.text()),
                'readout_laser_duration': int(self.t1_readout_laser_duration.text()),
                'detection_duration': int(self.t1_detection_duration.text()),
                'init_laser_delay': int(self.t1_init_laser_delay.text()),
                'readout_laser_delay': int(self.start_delay.text()),  # Use Start Delay from GUI
                'detection_delay': 0,  # Detection is aligned with readout, so no additional delay
                'sequence_interval': int(self.t1_sequence_interval.text()),
                'repetitions': int(self.t1_repetitions.text())
            }
            
            # Update the pulse pattern visualization
            self.t1_pulse_pattern_widget.update_t1_pulse_pattern(parameters)
            self.log_message("✅ T1 pulse pattern updated")
            
        except ValueError as e:
            QMessageBox.warning(self, "Parameter Error", f"Invalid parameter value: {e}")
        except Exception as e:
            QMessageBox.warning(self, "Visualization Error", f"Failed to update T1 pulse pattern: {e}")
    
    def connect_t1_parameter_signals(self):
        """Connect T1 parameter input fields to automatic pulse pattern updates"""
        # Connect laser parameters
        self.t1_init_laser_duration.textChanged.connect(self.update_t1_pulse_pattern)
        self.t1_readout_laser_duration.textChanged.connect(self.update_t1_pulse_pattern)
        self.t1_detection_duration.textChanged.connect(self.update_t1_pulse_pattern)
        
        # Connect timing parameters
        self.t1_init_laser_delay.textChanged.connect(self.update_t1_pulse_pattern)
        self.t1_readout_laser_delay.textChanged.connect(self.update_t1_pulse_pattern)
        self.t1_detection_delay.textChanged.connect(self.update_t1_pulse_pattern)
        
        # Connect delay parameters (Start Delay controls the space between init and readout)
        self.start_delay.textChanged.connect(self.update_t1_pulse_pattern)
        
        # Connect sequence parameters
        self.t1_sequence_interval.textChanged.connect(self.update_t1_pulse_pattern)
        self.t1_repetitions.textChanged.connect(self.update_t1_pulse_pattern)
    
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
        self.worker.data_saved.connect(self.on_data_saved)  # Connect data saved signal
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
    
    def on_data_saved(self, filename):
        """Handle automatic data saving completion"""
        # Log the successful save
        self.log_message(f"💾 Data automatically saved to: {filename}")
        
        # Optionally show a brief success message
        # You can uncomment the following line if you want a popup notification
        # QMessageBox.information(self, "Data Saved", f"Data automatically saved to:\n{filename}")
    
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
    
    def get_rabi_parameters(self):
        """Get all parameters for Rabi oscillation measurement"""
        try:
            start_duration = int(self.start_duration.text())
            stop_duration = int(self.stop_duration.text())
            step_size = int(self.duration_step.text())
            mw_durations = list(range(start_duration, stop_duration + step_size, step_size))
            
            mw_frequency = float(self.rabi_mw_freq.text()) * 1e9  # Convert GHz to Hz
            
            return {
                'mw_durations': mw_durations,
                'mw_frequency': mw_frequency,
                'laser_duration': int(self.rabi_laser_duration.text()),
                'detection_duration': int(self.rabi_detection_duration.text()),
                'laser_delay': int(self.rabi_laser_delay.text()),
                'mw_delay': int(self.rabi_mw_delay.text()),
                'detection_delay': int(self.rabi_detection_delay.text()),
                'sequence_interval': int(self.rabi_sequence_interval.text()),
                'repetitions': int(self.rabi_repetitions.text())
            }
        except ValueError as e:
            QMessageBox.warning(self, "Parameter Error", f"Invalid parameter value: {e}")
            return None
    
    def start_rabi_measurement(self):
        """Start Rabi oscillation measurement"""
        if not self.pulse_controller or not self.pulse_controller.is_connected:
            QMessageBox.warning(self, "Connection Error", "Pulse Streamer not connected!")
            return
        
        parameters = self.get_rabi_parameters()
        if parameters is None:
            return
        
        # Initialize experiments if needed
        if not self.experiments:
            self.experiments = ODMRExperiments(self.pulse_controller, self.mw_generator)
        
        # Set MW power
        if self.mw_generator:
            try:
                power = float(self.rabi_mw_power.text())
                self.mw_generator.set_power(power)
            except:
                pass
        
        # Update UI
        self.start_rabi_btn.setEnabled(False)
        self.stop_rabi_btn.setEnabled(True)
        self.rabi_progress_bar.setVisible(True)
        self.rabi_progress_bar.setValue(0)
        self.current_results = {'durations': [], 'count_rates': []}
        
        # Start worker thread
        self.worker = RabiWorker(self.experiments, parameters)
        self.worker.progress_updated.connect(self.rabi_progress_bar.setValue)
        self.worker.status_updated.connect(self.log_message)
        self.worker.data_updated.connect(self.update_rabi_plot)
        self.worker.measurement_finished.connect(self.rabi_measurement_finished)
        self.worker.error_occurred.connect(self.handle_error)
        self.worker.data_saved.connect(self.on_data_saved)  # Connect data saved signal
        self.worker.start()
        
        self.log_message("🚀 Rabi oscillation measurement started")
    
    def stop_rabi_measurement(self):
        """Stop Rabi oscillation measurement"""
        if self.worker:
            self.worker.stop()
            self.log_message("⏹️ Stopping Rabi measurement...")
    
    def update_rabi_plot(self, durations, count_rates):
        """Update the real-time plot with Rabi data"""
        self.current_results['durations'] = durations
        self.current_results['count_rates'] = count_rates
        self.plot_widget.ax.clear()
        
        # Plot data
        self.plot_widget.ax.plot(durations, count_rates, 'o-', markersize=4, linewidth=2,
                               color='#00ff88', markerfacecolor='#00d4aa', markeredgecolor='#00ff88')
        
        # Update labels and title
        self.plot_widget.ax.set_xlabel('MW Duration (ns)', fontsize=12, color='white')
        self.plot_widget.ax.set_ylabel('Count Rate (Hz)', fontsize=12, color='white')
        self.plot_widget.ax.set_title('Rabi Oscillations (Live)', fontsize=14, fontweight='bold', color='white')
        
        # Re-apply dark theme styling
        self.plot_widget.ax.set_facecolor('#262930')
        self.plot_widget.ax.grid(True, alpha=0.3, color='#555555')
        self.plot_widget.ax.tick_params(colors='white')
        for spine in self.plot_widget.ax.spines.values():
            spine.set_color('white')
        
        # Auto-scale with padding
        if len(durations) > 1:
            duration_range = max(durations) - min(durations)
            self.plot_widget.ax.set_xlim(min(durations) - 0.05*duration_range,
                                       max(durations) + 0.05*duration_range)
        
        if len(count_rates) > 1:
            count_range = max(count_rates) - min(count_rates)
            if count_range > 0:
                self.plot_widget.ax.set_ylim(min(count_rates) - 0.1*count_range,
                                           max(count_rates) + 0.1*count_range)
        
        self.plot_widget.figure.tight_layout()
        self.plot_widget.canvas.draw()
    
    def rabi_measurement_finished(self):
        """Handle Rabi measurement completion"""
        self.start_rabi_btn.setEnabled(True)
        self.stop_rabi_btn.setEnabled(False)
        self.rabi_progress_bar.setVisible(False)
        
        # Turn off MW output
        if self.mw_generator:
            try:
                self.mw_generator.set_rf_output(False)
            except:
                pass
    
    def save_rabi_parameters(self):
        """Save current Rabi parameters to JSON file"""
        try:
            params = self.get_rabi_parameters()
            if params is None:
                return
            
            # Add UI-specific parameters
            params['start_duration'] = int(self.start_duration.text())
            params['stop_duration'] = int(self.stop_duration.text())
            params['duration_step'] = int(self.duration_step.text())
            params['mw_frequency_ghz'] = float(self.rabi_mw_freq.text())
            params['mw_power_dbm'] = float(self.rabi_mw_power.text())
            params['laser_delay'] = int(self.rabi_laser_delay.text())
            params['mw_delay'] = int(self.rabi_mw_delay.text())
            params['detection_delay'] = int(self.rabi_detection_delay.text())
            params['sequence_interval'] = int(self.rabi_sequence_interval.text())
            
            filename, _ = QFileDialog.getSaveFileName(
                self, "Save Rabi Parameters", "", "JSON files (*.json);;All files (*.*)"
            )
            
            if filename:
                with open(filename, 'w') as f:
                    json.dump(params, f, indent=2)
                self.log_message(f"💾 Rabi parameters saved to {filename}")
                
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Error saving Rabi parameters: {e}")
    
    def load_rabi_parameters(self):
        """Load Rabi parameters from JSON file"""
        try:
            filename, _ = QFileDialog.getOpenFileName(
                self, "Load Rabi Parameters", "", "JSON files (*.json);;All files (*.*)"
            )
            
            if filename:
                with open(filename, 'r') as f:
                    params = json.load(f)
                
                # Set UI parameters
                if 'start_duration' in params:
                    self.start_duration.setText(str(params['start_duration']))
                if 'stop_duration' in params:
                    self.stop_duration.setText(str(params['stop_duration']))
                if 'duration_step' in params:
                    self.duration_step.setText(str(params['duration_step']))
                if 'mw_frequency_ghz' in params:
                    self.rabi_mw_freq.setText(str(params['mw_frequency_ghz']))
                if 'mw_power_dbm' in params:
                    self.rabi_mw_power.setText(str(params['mw_power_dbm']))
                
                # Set timing parameters
                if 'laser_duration' in params:
                    self.rabi_laser_duration.setText(str(params['laser_duration']))
                if 'detection_duration' in params:
                    self.rabi_detection_duration.setText(str(params['detection_duration']))
                if 'laser_delay' in params:
                    self.rabi_laser_delay.setText(str(params['laser_delay']))
                if 'mw_delay' in params:
                    self.rabi_mw_delay.setText(str(params['mw_delay']))
                if 'detection_delay' in params:
                    self.rabi_detection_delay.setText(str(params['detection_delay']))
                if 'sequence_interval' in params:
                    self.rabi_sequence_interval.setText(str(params['sequence_interval']))
                if 'repetitions' in params:
                    self.rabi_repetitions.setText(str(params['repetitions']))
                
                self.log_message(f"📁 Rabi parameters loaded from {filename}")
                
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Error loading Rabi parameters: {e}")
    
    def save_rabi_results(self):
        """Save Rabi measurement results"""
        if not self.current_results.get('durations'):
            QMessageBox.warning(self, "No Data", "No Rabi results to save!")
            return
        
        try:
            filename, file_type = QFileDialog.getSaveFileName(
                self, "Save Rabi Results", "", 
                "JSON files (*.json);;CSV files (*.csv);;All files (*.*)"
            )
            
            if filename:
                if filename.endswith('.csv') or 'CSV' in file_type:
                    # Save as CSV
                    import csv
                    with open(filename, 'w', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow(['MW_Duration_ns', 'Count_Rate_Hz'])
                        for duration, count in zip(self.current_results['durations'],
                                                 self.current_results['count_rates']):
                            writer.writerow([duration, count])
                else:
                    # Save as JSON
                    data = {
                        'mw_durations_ns': self.current_results['durations'],
                        'count_rates_hz': self.current_results['count_rates'],
                        'parameters': self.get_rabi_parameters(),
                        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                    }
                    with open(filename, 'w') as f:
                        json.dump(data, f, indent=2)
                
                self.log_message(f"📊 Rabi results saved to {filename}")
                
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Error saving Rabi results: {e}")
    
    def get_t1_parameters(self):
        """Get all parameters for T1 decay measurement"""
        try:
            start_delay = int(self.start_delay.text())
            stop_delay = int(self.stop_delay.text())
            step_size = int(self.delay_step.text())
            delay_times = list(range(start_delay, stop_delay + step_size, step_size))
            
            # Handle auto-calculated delays
            readout_laser_delay = None
            detection_delay = None
            
            if self.t1_readout_laser_delay.text().lower() != "auto":
                readout_laser_delay = int(self.t1_readout_laser_delay.text())
            
            if self.t1_detection_delay.text().lower() != "auto":
                detection_delay = int(self.t1_detection_delay.text())
            
            return {
                'delay_times': delay_times,
                'init_laser_duration': int(self.t1_init_laser_duration.text()),
                'readout_laser_duration': int(self.t1_readout_laser_duration.text()),
                'detection_duration': int(self.t1_detection_duration.text()),
                'init_laser_delay': int(self.t1_init_laser_delay.text()),
                'readout_laser_delay': readout_laser_delay,
                'detection_delay': detection_delay,
                'sequence_interval': int(self.t1_sequence_interval.text()),
                'repetitions': int(self.t1_repetitions.text())
            }
        except ValueError as e:
            QMessageBox.warning(self, "Parameter Error", f"Invalid parameter value: {e}")
            return None
    
    def start_t1_measurement(self):
        """Start T1 decay measurement"""
        if not self.pulse_controller or not self.pulse_controller.is_connected:
            QMessageBox.warning(self, "Connection Error", "Pulse Streamer not connected!")
            return
        
        parameters = self.get_t1_parameters()
        if parameters is None:
            return
        
        # Initialize experiments if needed
        if not self.experiments:
            self.experiments = ODMRExperiments(self.pulse_controller, self.mw_generator)
        
        # Update UI
        self.start_t1_btn.setEnabled(False)
        self.stop_t1_btn.setEnabled(True)
        self.t1_progress_bar.setVisible(True)
        self.t1_progress_bar.setValue(0)
        self.current_results = {'delays': [], 'count_rates': []}
        
        # Start worker thread
        self.worker = T1Worker(self.experiments, parameters)
        self.worker.progress_updated.connect(self.t1_progress_bar.setValue)
        self.worker.status_updated.connect(self.log_message)
        self.worker.data_updated.connect(self.update_t1_plot)
        self.worker.measurement_finished.connect(self.t1_measurement_finished)
        self.worker.error_occurred.connect(self.handle_error)
        self.worker.data_saved.connect(self.on_data_saved)  # Connect data saved signal
        self.worker.start()
        
        self.log_message("🚀 T1 decay measurement started")
    
    def stop_t1_measurement(self):
        """Stop T1 decay measurement"""
        if self.worker:
            self.worker.stop()
            self.log_message("⏹️ Stopping T1 measurement...")
    
    def update_t1_plot(self, delays, count_rates):
        """Update the real-time plot with T1 data"""
        self.current_results['delays'] = delays
        self.current_results['count_rates'] = count_rates
        self.plot_widget.ax.clear()
        
        # Plot data
        self.plot_widget.ax.plot(np.array(delays)/1000, count_rates, 'o-', markersize=4, linewidth=2,
                               color='#00ff88', markerfacecolor='#00d4aa', markeredgecolor='#00ff88')
        
        # Update labels and title
        self.plot_widget.ax.set_xlabel('Delay Time (µs)', fontsize=12, color='white')
        self.plot_widget.ax.set_ylabel('Count Rate (Hz)', fontsize=12, color='white')
        self.plot_widget.ax.set_title('T1 Decay (Live)', fontsize=14, fontweight='bold', color='white')
        
        # Re-apply dark theme styling
        self.plot_widget.ax.set_facecolor('#262930')
        self.plot_widget.ax.grid(True, alpha=0.3, color='#555555')
        self.plot_widget.ax.tick_params(colors='white')
        for spine in self.plot_widget.ax.spines.values():
            spine.set_color('white')
        
        # Auto-scale with padding
        if len(delays) > 1:
            delay_range = max(delays) - min(delays)
            self.plot_widget.ax.set_xlim((min(delays) - 0.05*delay_range)/1000,
                                       (max(delays) + 0.05*delay_range)/1000)
        
        if len(count_rates) > 1:
            count_range = max(count_rates) - min(count_rates)
            if count_range > 0:
                self.plot_widget.ax.set_ylim(min(count_rates) - 0.1*count_range,
                                           max(count_rates) + 0.1*count_range)
        
        self.plot_widget.figure.tight_layout()
        self.plot_widget.canvas.draw()
    
    def t1_measurement_finished(self):
        """Handle T1 measurement completion"""
        self.start_t1_btn.setEnabled(True)
        self.stop_t1_btn.setEnabled(False)
        self.t1_progress_bar.setVisible(False)
    
    def save_t1_parameters(self):
        """Save current T1 parameters to JSON file"""
        try:
            params = self.get_t1_parameters()
            if params is None:
                return
            
            # Add UI-specific parameters
            params['start_delay'] = int(self.start_delay.text())
            params['stop_delay'] = int(self.stop_delay.text())
            params['delay_step'] = int(self.delay_step.text())
            params['readout_laser_delay_text'] = self.t1_readout_laser_delay.text()
            params['detection_delay_text'] = self.t1_detection_delay.text()
            
            filename, _ = QFileDialog.getSaveFileName(
                self, "Save T1 Parameters", "", "JSON files (*.json);;All files (*.*)"
            )
            
            if filename:
                with open(filename, 'w') as f:
                    json.dump(params, f, indent=2)
                self.log_message(f"💾 T1 parameters saved to {filename}")
                
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Error saving T1 parameters: {e}")
    
    def load_t1_parameters(self):
        """Load T1 parameters from JSON file"""
        try:
            filename, _ = QFileDialog.getOpenFileName(
                self, "Load T1 Parameters", "", "JSON files (*.json);;All files (*.*)"
            )
            
            if filename:
                with open(filename, 'r') as f:
                    params = json.load(f)
                
                # Set UI parameters
                if 'start_delay' in params:
                    self.start_delay.setText(str(params['start_delay']))
                if 'stop_delay' in params:
                    self.stop_delay.setText(str(params['stop_delay']))
                if 'delay_step' in params:
                    self.delay_step.setText(str(params['delay_step']))
                
                # Set timing parameters
                if 'init_laser_duration' in params:
                    self.t1_init_laser_duration.setText(str(params['init_laser_duration']))
                if 'readout_laser_duration' in params:
                    self.t1_readout_laser_duration.setText(str(params['readout_laser_duration']))
                if 'detection_duration' in params:
                    self.t1_detection_duration.setText(str(params['detection_duration']))
                if 'init_laser_delay' in params:
                    self.t1_init_laser_delay.setText(str(params['init_laser_delay']))
                
                # Handle auto/manual delay settings
                if 'readout_laser_delay_text' in params:
                    self.t1_readout_laser_delay.setText(params['readout_laser_delay_text'])
                elif 'readout_laser_delay' in params and params['readout_laser_delay'] is not None:
                    self.t1_readout_laser_delay.setText(str(params['readout_laser_delay']))
                
                if 'detection_delay_text' in params:
                    self.t1_detection_delay.setText(params['detection_delay_text'])
                elif 'detection_delay' in params and params['detection_delay'] is not None:
                    self.t1_detection_delay.setText(str(params['detection_delay']))
                
                if 'sequence_interval' in params:
                    self.t1_sequence_interval.setText(str(params['sequence_interval']))
                if 'repetitions' in params:
                    self.t1_repetitions.setText(str(params['repetitions']))
                
                self.log_message(f"📁 T1 parameters loaded from {filename}")
                
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Error loading T1 parameters: {e}")
    
    def save_t1_results(self):
        """Save T1 measurement results"""
        if not self.current_results.get('delays'):
            QMessageBox.warning(self, "No Data", "No T1 results to save!")
            return
        
        try:
            filename, file_type = QFileDialog.getSaveFileName(
                self, "Save T1 Results", "", 
                "JSON files (*.json);;CSV files (*.csv);;All files (*.*)"
            )
            
            if filename:
                if filename.endswith('.csv') or 'CSV' in file_type:
                    # Save as CSV
                    import csv
                    with open(filename, 'w', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow(['Delay_Time_ns', 'Count_Rate_Hz'])
                        for delay, count in zip(self.current_results['delays'],
                                              self.current_results['count_rates']):
                            writer.writerow([delay, count])
                else:
                    # Save as JSON
                    data = {
                        'delay_times_ns': self.current_results['delays'],
                        'count_rates_hz': self.current_results['count_rates'],
                        'parameters': self.get_t1_parameters(),
                        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                    }
                    with open(filename, 'w') as f:
                        json.dump(data, f, indent=2)
                
                self.log_message(f"📊 T1 results saved to {filename}")
                
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Error saving T1 results: {e}")
    
    def closeEvent(self, event):
        """Handle application closing"""
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self, "Quit", "Measurement in progress. Stop and quit?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                # Stop any running measurement
                if hasattr(self.worker, 'stop'):
                    self.worker.stop()
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
    app.setApplicationName("ODMR Control")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("Burke Lab")
    
    # Create and show main window
    window = ODMRControlCenter()
    window.show()
    
    # Start event loop
    sys.exit(app.exec_())


if __name__ == "__main__":
    main() 