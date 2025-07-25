"""
Pure PyQt single axis scan widget for the microscopy control software.
"""

import threading
import numpy as np
import time
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, 
    QPushButton, QLabel, QComboBox, QGroupBox
)
from PyQt5.QtCore import QThread, pyqtSignal
import pyqtgraph as pg


class SingleAxisScanThread(QThread):
    """Background thread for single axis scanning"""
    
    progress_update = pyqtSignal(int)  # percentage
    position_update = pyqtSignal(float, float)  # position, count
    scan_complete = pyqtSignal(list, list, str)  # positions, counts, message
    error_occurred = pyqtSignal(str)
    
    def __init__(self, start_pos, end_pos, n_steps, axis, current_pos, 
                 counter, binwidth, output_task, dwell_time=0.01):
        super().__init__()
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.n_steps = n_steps
        self.axis = axis  # 'X' or 'Y'
        self.current_pos = current_pos  # [x, y] current position
        self.counter = counter
        self.binwidth = binwidth
        self.output_task = output_task
        self.dwell_time = dwell_time
        self.stop_requested = False
    
    def run(self):
        """Perform single axis scan"""
        try:
            positions = np.linspace(self.start_pos, self.end_pos, self.n_steps)
            counts = []
            
            for i, pos in enumerate(positions):
                if self.stop_requested:
                    break
                
                # Move scanner
                if self.axis == 'X':
                    scan_pos = [pos, self.current_pos[1]]
                else:  # Y axis
                    scan_pos = [self.current_pos[0], pos]
                
                self.output_task.write(scan_pos)
                time.sleep(self.dwell_time)
                
                # Get measurement
                count = self.counter.getData()[0][0] / (self.binwidth / 1e12)
                counts.append(count)
                
                # Emit updates
                progress = int((i + 1) / len(positions) * 100)
                self.progress_update.emit(progress)
                self.position_update.emit(pos, count)
            
            if not self.stop_requested:
                self.scan_complete.emit(
                    positions.tolist(), counts,
                    f"{self.axis}-axis scan complete"
                )
            
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            # Return to original position
            try:
                self.output_task.write(self.current_pos)
            except:
                pass
    
    def stop(self):
        """Request stop"""
        self.stop_requested = True


class SingleAxisScanWidget(QWidget):
    """Pure PyQt single axis scan widget"""
    
    def __init__(self, scan_params_manager, output_task, counter, binwidth, parent=None):
        super().__init__(parent)
        self.scan_params_manager = scan_params_manager
        self.output_task = output_task
        self.counter = counter
        self.binwidth = binwidth
        self.scan_thread = None
        
        # Current position tracking
        self.current_position = [0.0, 0.0]  # [x, y]
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout()
        
        # Position display group
        pos_group = QGroupBox("Current Position")
        pos_layout = QGridLayout()
        
        pos_layout.addWidget(QLabel("X Position:"), 0, 0)
        self.x_pos_label = QLabel("0.000 V")
        pos_layout.addWidget(self.x_pos_label, 0, 1)
        
        pos_layout.addWidget(QLabel("Y Position:"), 1, 0)
        self.y_pos_label = QLabel("0.000 V")
        pos_layout.addWidget(self.y_pos_label, 1, 1)
        
        pos_group.setLayout(pos_layout)
        layout.addWidget(pos_group)
        
        # Scan controls group
        scan_group = QGroupBox("Single Axis Scan")
        scan_layout = QVBoxLayout()
        
        # Axis selection
        axis_layout = QHBoxLayout()
        axis_layout.addWidget(QLabel("Axis:"))
        self.axis_combo = QComboBox()
        self.axis_combo.addItems(["X", "Y"])
        axis_layout.addWidget(self.axis_combo)
        scan_layout.addLayout(axis_layout)
        
        # Scan parameters
        param_layout = QGridLayout()
        
        param_layout.addWidget(QLabel("Start:"), 0, 0)
        self.start_spin = pg.SpinBox(value=-1.0, bounds=(-10, 10), decimals=3, step=0.1)
        param_layout.addWidget(self.start_spin, 0, 1)
        
        param_layout.addWidget(QLabel("End:"), 1, 0)
        self.end_spin = pg.SpinBox(value=1.0, bounds=(-10, 10), decimals=3, step=0.1)
        param_layout.addWidget(self.end_spin, 1, 1)
        
        param_layout.addWidget(QLabel("Steps:"), 2, 0)
        self.steps_spin = pg.SpinBox(value=21, bounds=(3, 1000), int=True)
        param_layout.addWidget(self.steps_spin, 2, 1)
        
        param_layout.addWidget(QLabel("Dwell (s):"), 3, 0)
        self.dwell_spin = pg.SpinBox(value=0.01, bounds=(0.001, 1), decimals=4, step=0.001)
        param_layout.addWidget(self.dwell_spin, 3, 1)
        
        scan_layout.addLayout(param_layout)
        
        # Scan button
        self.scan_button = QPushButton("🔍 Start Scan")
        self.scan_button.clicked.connect(self.start_scan)
        scan_layout.addWidget(self.scan_button)
        
        scan_group.setLayout(scan_layout)
        layout.addWidget(scan_group)
        
        # Scan plot with dark theme matching ODMR GUI
        self.plot_widget = pg.PlotWidget(title="Single Axis Scan")
        self.plot_widget.setBackground('#262930')
        self.plot_widget.setLabel('left', 'Counts/s', color='white', size='12pt')
        self.plot_widget.setLabel('bottom', 'Position (V)', color='white', size='12pt')
        self.plot_widget.showGrid(True, alpha=0.3)
        self.plot_widget.setFixedHeight(250)
        
        # Style the axes
        self.plot_widget.getAxis('left').setPen('white')
        self.plot_widget.getAxis('bottom').setPen('white')
        self.plot_widget.getAxis('left').setTextPen('white')
        self.plot_widget.getAxis('bottom').setTextPen('white')
        
        self.scan_curve = self.plot_widget.plot(pen=pg.mkPen('#00ff88', width=2), 
                                               symbol='o', symbolBrush='#00d4aa',
                                               symbolPen='#00ff88', symbolSize=5)
        layout.addWidget(self.plot_widget)
        
        self.setLayout(layout)
    
    def update_current_position(self, x, y):
        """Update the current position display"""
        self.current_position = [x, y]
        self.x_pos_label.setText(f"{x:.3f} V")
        self.y_pos_label.setText(f"{y:.3f} V")
    
    def start_scan(self):
        """Start single axis scan"""
        if self.scan_thread and self.scan_thread.isRunning():
            # Stop current scan
            self.scan_thread.stop()
            self.scan_button.setText("🔍 Start Scan")
            return
        
        # Start new scan
        self.scan_button.setText("⏹ Stop Scan")
        
        # Clear plot
        self.scan_curve.setData([], [])
        
        # Get parameters
        axis = self.axis_combo.currentText()
        start_pos = self.start_spin.value()
        end_pos = self.end_spin.value()
        n_steps = int(self.steps_spin.value())
        dwell_time = self.dwell_spin.value()
        
        # Start scan thread
        self.scan_thread = SingleAxisScanThread(
            start_pos, end_pos, n_steps, axis, self.current_position.copy(),
            self.counter, self.binwidth, self.output_task, dwell_time
        )
        
        self.scan_thread.position_update.connect(self.update_plot)
        self.scan_thread.scan_complete.connect(self.on_scan_complete)
        self.scan_thread.error_occurred.connect(self.on_scan_error)
        self.scan_thread.start()
    
    def update_plot(self, position, count):
        """Update the scan plot with new data point"""
        # Get current data
        current_x, current_y = self.scan_curve.getData()
        
        # Convert to lists if they're arrays
        if current_x is None:
            current_x, current_y = [], []
        else:
            current_x, current_y = list(current_x), list(current_y)
        
        # Add new point
        current_x.append(position)
        current_y.append(count)
        
        # Update plot
        self.scan_curve.setData(current_x, current_y)
    
    def on_scan_complete(self, positions, counts, message):
        """Handle scan completion"""
        self.scan_button.setText("🔍 Start Scan")
        
        # Update plot with final data
        self.scan_curve.setData(positions, counts)
        print(message)
    
    def on_scan_error(self, error_msg):
        """Handle scan error"""
        self.scan_button.setText("🔍 Start Scan")
        print(f"Scan error: {error_msg}")


def create_single_axis_scan_widget(scan_params_manager, output_task, counter, binwidth):
    """Factory function to create single axis scan widget"""
    return SingleAxisScanWidget(scan_params_manager, output_task, counter, binwidth) 