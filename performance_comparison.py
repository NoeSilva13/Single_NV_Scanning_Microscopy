"""
Performance Comparison: Matplotlib vs PyQtGraph for Real-time Plotting
========================================================================
This script demonstrates the performance difference between the two implementations
"""

import sys
import time
import numpy as np
from qtpy.QtWidgets import QApplication, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton
from qtpy.QtCore import QTimer

# Import both widget implementations
from plot_widgets.live_plot_napari_widget import LivePlotNapariWidget
from plot_widgets.live_plot_pyqtgraph_widget import LivePlotPyQtGraphWidget, AdvancedLivePlotPyQtGraphWidget

class PerformanceComparisonWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.setup_data_generation()
        
    def setup_ui(self):
        """Setup the comparison UI"""
        self.setWindowTitle("Performance Comparison: Matplotlib vs PyQtGraph")
        self.setGeometry(100, 100, 1200, 800)
        
        # Main layout
        main_layout = QVBoxLayout()
        
        # Control panel
        control_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("Start Comparison")
        self.start_btn.clicked.connect(self.start_comparison)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_comparison)
        self.stop_btn.setEnabled(False)
        
        self.fps_label = QLabel("FPS: Matplotlib: -- | PyQtGraph: -- | Advanced: --")
        
        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.stop_btn)
        control_layout.addWidget(self.fps_label)
        control_layout.addStretch()
        
        # Plot widgets layout
        plots_layout = QHBoxLayout()
        
        # Matplotlib widget
        matplotlib_layout = QVBoxLayout()
        matplotlib_layout.addWidget(QLabel("Matplotlib (Original)"))
        self.matplotlib_widget = LivePlotNapariWidget(
            measure_function=self.generate_matplotlib_data,
            histogram_range=100,
            dt=50,  # 50ms updates
            widget_height=250
        )
        matplotlib_layout.addWidget(self.matplotlib_widget)
        
        # PyQtGraph widget
        pyqtgraph_layout = QVBoxLayout()
        pyqtgraph_layout.addWidget(QLabel("PyQtGraph (Basic)"))
        self.pyqtgraph_widget = LivePlotPyQtGraphWidget(
            measure_function=self.generate_pyqtgraph_data,
            histogram_range=100,
            dt=50,  # 50ms updates
            widget_height=250
        )
        pyqtgraph_layout.addWidget(self.pyqtgraph_widget)
        
        # Advanced PyQtGraph widget
        advanced_layout = QVBoxLayout()
        advanced_layout.addWidget(QLabel("PyQtGraph (Advanced)"))
        self.advanced_widget = AdvancedLivePlotPyQtGraphWidget(
            measure_function=self.generate_advanced_data,
            histogram_range=100,
            dt=50,  # 50ms updates
            widget_height=250
        )
        advanced_layout.addWidget(self.advanced_widget)
        
        plots_layout.addLayout(matplotlib_layout)
        plots_layout.addLayout(pyqtgraph_layout)
        plots_layout.addLayout(advanced_layout)
        
        main_layout.addLayout(control_layout)
        main_layout.addLayout(plots_layout)
        
        self.setLayout(main_layout)
        
    def setup_data_generation(self):
        """Setup data generation for performance measurement"""
        self.data_t = 0
        self.base_frequency = 1.0  # Hz
        self.noise_amplitude = 0.1
        
        # Performance counters
        self.matplotlib_updates = 0
        self.pyqtgraph_updates = 0
        self.advanced_updates = 0
        
        self.matplotlib_last_time = time.time()
        self.pyqtgraph_last_time = time.time()
        self.advanced_last_time = time.time()
        
        # FPS calculation timer
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self.update_fps_display)
        
    def generate_matplotlib_data(self):
        """Generate data for matplotlib widget and count updates"""
        self.matplotlib_updates += 1
        return self.generate_signal_data()
    
    def generate_pyqtgraph_data(self):
        """Generate data for pyqtgraph widget and count updates"""
        self.pyqtgraph_updates += 1
        return self.generate_signal_data()
    
    def generate_advanced_data(self):
        """Generate data for advanced widget and count updates"""
        self.advanced_updates += 1
        return self.generate_signal_data()
    
    def generate_signal_data(self):
        """Generate a realistic signal with multiple frequency components"""
        self.data_t += 0.05  # Increment time
        
        # Generate complex signal with multiple components
        signal = (
            np.sin(2 * np.pi * self.base_frequency * self.data_t) +
            0.5 * np.sin(2 * np.pi * 3 * self.base_frequency * self.data_t) +
            0.3 * np.sin(2 * np.pi * 7 * self.base_frequency * self.data_t) +
            self.noise_amplitude * np.random.randn()
        )
        
        return float(signal)
    
    def start_comparison(self):
        """Start the performance comparison"""
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        
        # Reset counters
        self.matplotlib_updates = 0
        self.pyqtgraph_updates = 0
        self.advanced_updates = 0
        
        self.matplotlib_last_time = time.time()
        self.pyqtgraph_last_time = time.time()
        self.advanced_last_time = time.time()
        
        # Start FPS monitoring
        self.fps_timer.start(1000)  # Update every second
        
    def stop_comparison(self):
        """Stop the performance comparison"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
        # Stop FPS monitoring
        self.fps_timer.stop()
        
    def update_fps_display(self):
        """Update the FPS display"""
        current_time = time.time()
        
        # Calculate FPS for each widget
        matplotlib_fps = self.matplotlib_updates / max(current_time - self.matplotlib_last_time, 0.001)
        pyqtgraph_fps = self.pyqtgraph_updates / max(current_time - self.pyqtgraph_last_time, 0.001)
        advanced_fps = self.advanced_updates / max(current_time - self.advanced_last_time, 0.001)
        
        # Update display
        self.fps_label.setText(
            f"FPS: Matplotlib: {matplotlib_fps:.1f} | "
            f"PyQtGraph: {pyqtgraph_fps:.1f} | "
            f"Advanced: {advanced_fps:.1f}"
        )
        
        # Reset counters for next measurement
        self.matplotlib_updates = 0
        self.pyqtgraph_updates = 0 
        self.advanced_updates = 0
        
        self.matplotlib_last_time = current_time
        self.pyqtgraph_last_time = current_time
        self.advanced_last_time = current_time

def run_performance_comparison():
    """Run the performance comparison application"""
    app = QApplication(sys.argv)
    
    # Create and show the comparison widget
    comparison_widget = PerformanceComparisonWidget()
    comparison_widget.show()
    
    print("Performance Comparison Started")
    print("=" * 50)
    print("Instructions:")
    print("1. Click 'Start Comparison' to begin measuring performance")
    print("2. Watch the FPS counters to see the difference")
    print("3. PyQtGraph should show significantly higher FPS")
    print("4. Click 'Stop' when done")
    print("=" * 50)
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    run_performance_comparison() 