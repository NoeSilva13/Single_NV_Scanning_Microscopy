"""
Pure PyQt auto focus widget for the microscopy control software.
"""

import threading
import numpy as np
import time
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QProgressBar, QLabel
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
import pyqtgraph as pg


class AutoFocusThread(QThread):
    """Background thread for auto-focus operation"""
    
    progress_update = pyqtSignal(int)  # percentage
    position_update = pyqtSignal(float, float)  # position, count
    focus_complete = pyqtSignal(float, list, list, str)  # best_position, positions, counts, message
    error_occurred = pyqtSignal(str)
    
    def __init__(self, counter, binwidth, z_range=(-0.5, 0.5), n_steps=21):
        super().__init__()
        self.counter = counter
        self.binwidth = binwidth
        self.z_range = z_range
        self.n_steps = n_steps
        self.stop_requested = False
    
    def run(self):
        """Perform auto-focus scan"""
        try:
            positions = np.linspace(self.z_range[0], self.z_range[1], self.n_steps)
            counts = []
            
            for i, z_pos in enumerate(positions):
                if self.stop_requested:
                    break
                
                # Here you would move the Z actuator to z_pos
                # For now, we'll simulate with a sleep
                time.sleep(0.1)
                
                # Get count measurement
                count = self.counter.getData()[0][0] / (self.binwidth / 1e12)
                counts.append(count)
                
                # Emit updates
                progress = int((i + 1) / len(positions) * 100)
                self.progress_update.emit(progress)
                self.position_update.emit(z_pos, count)
            
            if not self.stop_requested and counts:
                # Find best focus position
                best_idx = np.argmax(counts)
                best_position = positions[best_idx]
                
                self.focus_complete.emit(
                    best_position, positions.tolist(), counts,
                    f"Auto-focus complete. Best position: {best_position:.3f}V"
                )
            
        except Exception as e:
            self.error_occurred.emit(str(e))
    
    def stop(self):
        """Request stop"""
        self.stop_requested = True


class AutoFocusWidget(QWidget):
    """Pure PyQt auto focus widget"""
    
    def __init__(self, counter, binwidth, parent=None):
        super().__init__(parent)
        self.counter = counter
        self.binwidth = binwidth
        self.focus_thread = None
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout()
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Status label (initially empty)
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)
        
        # Focus plot with dark theme matching ODMR GUI
        self.plot_widget = pg.PlotWidget(title="Focus Curve")
        self.plot_widget.setBackground('#262930')
        self.plot_widget.setLabel('left', 'Counts/s', color='white', size='12pt')
        self.plot_widget.setLabel('bottom', 'Z Position (V)', color='white', size='12pt')
        self.plot_widget.showGrid(True, alpha=0.3)
        self.plot_widget.setFixedHeight(200)
        
        # Style the axes
        self.plot_widget.getAxis('left').setPen('white')
        self.plot_widget.getAxis('bottom').setPen('white')
        self.plot_widget.getAxis('left').setTextPen('white')
        self.plot_widget.getAxis('bottom').setTextPen('white')
        
        self.focus_curve = self.plot_widget.plot(pen=pg.mkPen('#00ff88', width=2), 
                                                symbol='o', symbolBrush='#00d4aa', 
                                                symbolPen='#00ff88', symbolSize=6)
        layout.addWidget(self.plot_widget)
        
        self.setLayout(layout)
    
    def start_auto_focus(self):
        """Start auto-focus operation"""
        if self.focus_thread and self.focus_thread.isRunning():
            # Stop current focus
            self.focus_thread.stop()
            return
        
        # Start new focus - button control is now handled by scan controls
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Auto-focus in progress...")
        
        # Clear plot
        self.focus_curve.setData([], [])
        
        # Start focus thread
        self.focus_thread = AutoFocusThread(self.counter, self.binwidth)
        self.focus_thread.progress_update.connect(self.progress_bar.setValue)
        self.focus_thread.position_update.connect(self.update_plot)
        self.focus_thread.focus_complete.connect(self.on_focus_complete)
        self.focus_thread.error_occurred.connect(self.on_focus_error)
        self.focus_thread.start()
    
    def update_plot(self, position, count):
        """Update the focus plot with new data point"""
        # Get current data
        current_x, current_y = self.focus_curve.getData()
        
        # Convert to lists if they're arrays
        if current_x is None:
            current_x, current_y = [], []
        else:
            current_x, current_y = list(current_x), list(current_y)
        
        # Add new point
        current_x.append(position)
        current_y.append(count)
        
        # Update plot
        self.focus_curve.setData(current_x, current_y)
    
    def on_focus_complete(self, best_position, positions, counts, message):
        """Handle focus completion"""
        self.progress_bar.setVisible(False)
        self.status_label.setText(message)
        
        # Update plot with final data
        self.focus_curve.setData(positions, counts)
        
        # Highlight best position with accent color
        best_count = counts[positions.index(best_position)]
        self.plot_widget.plot([best_position], [best_count], 
                            pen=None, symbol='o', symbolBrush='#00d4aa', 
                            symbolPen='#00ffcc', symbolSize=12)
    
    def on_focus_error(self, error_msg):
        """Handle focus error"""
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Error: {error_msg}")


def create_auto_focus_widget(counter, binwidth):
    """Factory function to create auto focus widget"""
    return AutoFocusWidget(counter, binwidth) 