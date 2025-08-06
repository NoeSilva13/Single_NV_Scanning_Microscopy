"""
Galvo Position Tracker Widget for the Napari Scanning SPD application.

Contains the GalvoPositionTrackerWidget class for tracking and displaying
the current position of the galvo scanner.
"""

import numpy as np
from PyQt5.QtWidgets import QWidget, QGridLayout, QLabel
from PyQt5.QtCore import Qt
from utils import MICRONS_PER_VOLT


class GalvoPositionTrackerWidget(QWidget):
    """Widget for tracking and displaying the current galvo scanner position"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Track current scanner position internally
        self.current_x_voltage = 0.0
        self.current_y_voltage = 0.0
        
        # Flag to track if we're in a main scan (to avoid updates during scanning)
        self.scan_in_progress = False
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the user interface using the same approach as ScanParametersWidget"""
        # Create the main layout
        layout = QGridLayout()
        
        # Headers
        layout.addWidget(QLabel("Axis"), 0, 0)
        layout.addWidget(QLabel("Voltage (V)"), 0, 1)
        layout.addWidget(QLabel("Distance (µm)"), 0, 2)
        
        # X position display
        layout.addWidget(QLabel("X:"), 1, 0)
        self.x_value_label = QLabel("0.000")
        self.x_value_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.x_value_label, 1, 1)
        
        self.x_distance_label = QLabel("0.0")
        self.x_distance_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.x_distance_label, 1, 2)
        
        # Y position display
        layout.addWidget(QLabel("Y:"), 2, 0)
        self.y_value_label = QLabel("0.000")
        self.y_value_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.y_value_label, 2, 1)
        
        self.y_distance_label = QLabel("0.0")
        self.y_distance_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.y_distance_label, 2, 2)
        
        self.setLayout(layout)
        
    def update_position(self, x_voltage, y_voltage):
        """Update the displayed position values"""
        # Only update if not in a main scan to avoid performance issues
        if not self.scan_in_progress:
            self.current_x_voltage = x_voltage
            self.current_y_voltage = y_voltage
            
            # Update display labels with voltage values
            self.x_value_label.setText(f"{x_voltage:.3f}")
            self.y_value_label.setText(f"{y_voltage:.3f}")
            
            # Update distance labels (convert voltage to microns)
            x_distance = x_voltage * MICRONS_PER_VOLT
            y_distance = y_voltage * MICRONS_PER_VOLT
            
            self.x_distance_label.setText(f"{x_distance:.1f}")
            self.y_distance_label.setText(f"{y_distance:.1f}")
    
    def set_scan_in_progress(self, in_progress):
        """Set the scan in progress flag to control updates"""
        self.scan_in_progress = in_progress
    
    def get_current_position(self):
        """Get the current tracked position"""
        return self.current_x_voltage, self.current_y_voltage
    
    def reset_position(self):
        """Reset position display to zero"""
        self.update_position(0.0, 0.0) 