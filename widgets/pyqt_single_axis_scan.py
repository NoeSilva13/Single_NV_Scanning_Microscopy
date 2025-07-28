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
        """Initialize the simplified UI with only X and Y scan buttons"""
        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Simplified scan controls - just two buttons
        scan_buttons_layout = QHBoxLayout()
        scan_buttons_layout.setSpacing(8)
        
        # X Scan button
        self.x_scan_button = QPushButton("📊 X Scan")
        self.x_scan_button.setFixedHeight(40)
        self.x_scan_button.clicked.connect(lambda: self.start_axis_scan('X'))
        scan_buttons_layout.addWidget(self.x_scan_button)
        
        # Y Scan button  
        self.y_scan_button = QPushButton("📈 Y Scan")
        self.y_scan_button.setFixedHeight(40)
        self.y_scan_button.clicked.connect(lambda: self.start_axis_scan('Y'))
        scan_buttons_layout.addWidget(self.y_scan_button)
        
        layout.addLayout(scan_buttons_layout)
        
        # Scan plot with dark theme matching ODMR GUI
        self.plot_widget = pg.PlotWidget(title="Single Axis Scan")
        self.plot_widget.setBackground('#262930')
        self.plot_widget.setLabel('left', 'Counts/s', color='white', size='11pt')
        self.plot_widget.setLabel('bottom', 'Position (V)', color='white', size='11pt')
        self.plot_widget.showGrid(True, alpha=0.3)
        
        # Set size policy to expand and use available space
        from PyQt5.QtWidgets import QSizePolicy
        self.plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
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
        """Update the current position (for internal tracking only - display moved to left panel)"""
        self.current_position = [x, y]
        # Note: Position labels removed - display is now in the left panel
    
    def start_axis_scan(self, axis):
        """Start single axis scan for specified axis (X or Y)"""
        # Determine which button was pressed and handle stop functionality
        if axis == 'X':
            button = self.x_scan_button
            other_button = self.y_scan_button
        else:
            button = self.y_scan_button
            other_button = self.x_scan_button
        
        # Check if scan is currently running
        if self.scan_thread and self.scan_thread.isRunning():
            # Stop current scan
            self.scan_thread.stop()
            self.x_scan_button.setText("📊 X Scan")
            self.y_scan_button.setText("📈 Y Scan")
            self.x_scan_button.setEnabled(True)
            self.y_scan_button.setEnabled(True)
            return
        
        # Start new scan
        button.setText(f"⏹ Stop {axis}")
        other_button.setEnabled(False)  # Disable other button during scan
        
        # Clear plot
        self.scan_curve.setData([], [])
        
        # Use default parameters (can be made configurable later if needed)
        start_pos = -1.0  # Default scan range from -1V to +1V
        end_pos = 1.0
        n_steps = 21      # Default 21 steps
        dwell_time = 0.01 # Default 10ms dwell time
        
        # Start scan thread
        self.scan_thread = SingleAxisScanThread(
            start_pos, end_pos, n_steps, axis, self.current_position.copy(),
            self.counter, self.binwidth, self.output_task, dwell_time
        )
        
        self.scan_thread.position_update.connect(self.update_plot)
        self.scan_thread.scan_complete.connect(lambda pos, counts, msg: self.on_scan_complete(pos, counts, msg, axis))
        self.scan_thread.error_occurred.connect(lambda error: self.on_scan_error(error, axis))
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
    
    def on_scan_complete(self, positions, counts, message, axis):
        """Handle scan completion"""
        # Reset both buttons to their default states
        self.x_scan_button.setText("📊 X Scan")
        self.y_scan_button.setText("📈 Y Scan")
        self.x_scan_button.setEnabled(True)
        self.y_scan_button.setEnabled(True)
        
        # Update plot with final data
        self.scan_curve.setData(positions, counts)
        
        # Update plot title to show which axis was scanned
        self.plot_widget.setTitle(f"Single Axis Scan - {axis} Axis")
        print(f"{axis} axis scan completed: {message}")
    
    def on_scan_error(self, error_msg, axis):
        """Handle scan error"""
        # Reset both buttons to their default states
        self.x_scan_button.setText("📊 X Scan")
        self.y_scan_button.setText("📈 Y Scan")
        self.x_scan_button.setEnabled(True)
        self.y_scan_button.setEnabled(True)
        
        print(f"{axis} axis scan error: {error_msg}")


def create_single_axis_scan_widget(scan_params_manager, output_task, counter, binwidth):
    """Factory function to create single axis scan widget"""
    return SingleAxisScanWidget(scan_params_manager, output_task, counter, binwidth) 