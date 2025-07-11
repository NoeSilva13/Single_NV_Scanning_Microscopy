"""
Single axis scan widget for the Napari Scanning SPD application.

Contains the SingleAxisScanWidget class for performing 1D scans along X or Y axis.
"""

import threading
import time
import numpy as np
from PyQt5.QtWidgets import QWidget, QPushButton, QGridLayout
from napari.utils.notifications import show_info
from plot_widgets.single_axis_plot import SingleAxisPlot


class SingleAxisScanWidget(QWidget):
    """Widget for performing single axis scans at current cursor position"""
    
    def __init__(self, scan_params_manager, layer, output_task, counter, binwidth, parent=None):
        super().__init__(parent)
        self.scan_params_manager = scan_params_manager
        self.layer = layer
        self.output_task = output_task
        self.counter = counter
        self.binwidth = binwidth
        
        # Track current scanner position internally (default to center)
        self.current_x_voltage = 0.0
        self.current_y_voltage = 0.0
        
        layout = QGridLayout()
        layout.setSpacing(5)
        self.setLayout(layout)
        
        # Create buttons for X and Y scans
        self.x_scan_btn = QPushButton("⬌ X-Axis Scan")
        self.y_scan_btn = QPushButton("⬍ Y-Axis Scan")
        
        # Add widgets to layout
        layout.addWidget(self.x_scan_btn, 0, 0)
        layout.addWidget(self.y_scan_btn, 0, 1)
        
        # Connect buttons
        self.x_scan_btn.clicked.connect(lambda: self.start_scan('x'))
        self.y_scan_btn.clicked.connect(lambda: self.start_scan('y'))
        
        # Create plot widget
        self.plot_widget = SingleAxisPlot()
        layout.addWidget(self.plot_widget, 1, 0, 1, 2)
        
        # Initialize plot with zeros
        self._initialize_plot()
        
        # Set fixed height for better appearance
        self.setFixedHeight(300)
    
    def _initialize_plot(self):
        """Initialize the plot with current config values"""
        params = self.scan_params_manager.get_params()
        x_range = params['scan_range']['x']
        x_res = params['resolution']['x']
        
        x_data = np.linspace(x_range[0], x_range[1], x_res)
        y_data = np.zeros(x_res)
        self.plot_widget.plot_data(
            x_data=x_data,
            y_data=y_data,
            x_label='Position (V)',
            y_label='Counts',
            title='Single Axis Scan',
            mark_peak=False
        )
    
    def update_current_position(self, x_voltage, y_voltage):
        """Update the current scanner position"""
        self.current_x_voltage = x_voltage
        self.current_y_voltage = y_voltage
        
    def get_current_position(self):
        """Get the current scanner position from internal tracking"""
        return self.current_x_voltage, self.current_y_voltage
    
    def start_scan(self, axis):
        """Start a single axis scan"""
        x_pos, y_pos = self.get_current_position()
        
        # Get current parameter values
        params = self.scan_params_manager.get_params()
        x_range = params['scan_range']['x']
        y_range = params['scan_range']['y']
        x_res = params['resolution']['x']
        y_res = params['resolution']['y']
        
        # Use resolution and range from parameters
        if axis == 'x':
            scan_points = np.linspace(x_range[0], x_range[1], x_res)
            fixed_pos = y_pos
            axis_label = 'X Position (V)'
        else:  # y-axis
            scan_points = np.linspace(y_range[0], y_range[1], y_res)
            fixed_pos = x_pos
            axis_label = 'Y Position (V)'
        
        # Perform scan in a separate thread
        def run_scan():
            counts = []
            for point in scan_points:
                if axis == 'x':
                    self.output_task.write([point, fixed_pos])
                else:
                    self.output_task.write([fixed_pos, point])
                    
                time.sleep(0.001)  # Small delay for settling
                count = self.counter.getData()[0][0]/(self.binwidth/1e12)
                counts.append(count)
            
            # Plot results
            self.plot_widget.plot_data(
                x_data=scan_points,
                y_data=counts,
                x_label=axis_label,
                y_label='Counts',
                title=f'Single Axis Scan ({axis.upper()})',
                mark_peak=True
            )
            
            # Return to original position
            self.output_task.write([x_pos, y_pos])
        
        threading.Thread(target=run_scan, daemon=True).start()
        show_info(f"🔍 Starting {axis.upper()}-axis scan...") 