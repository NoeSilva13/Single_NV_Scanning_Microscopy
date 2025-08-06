"""
Galvo Position Tracker Widget for the Napari Scanning SPD application.

Contains the GalvoPositionTrackerWidget class for tracking and displaying
the current position of the galvo scanner.
"""

import numpy as np
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QPalette, QColor


class GalvoPositionTrackerWidget(QWidget):
    """Widget for tracking and displaying the current galvo scanner position"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Track current scanner position internally
        self.current_x_voltage = 0.0
        self.current_y_voltage = 0.0
        
        # Flag to track if we're in a main scan (to avoid updates during scanning)
        self.scan_in_progress = False
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Setup the user interface"""
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(10, 10, 10, 10)
        self.setLayout(main_layout)
        
        # Title
        title_label = QLabel("Galvo Scanner Position")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(10)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # Separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator)
        
        # Position display container
        position_container = QFrame()
        position_container.setFrameStyle(QFrame.Box)
        position_container.setLineWidth(1)
        position_layout = QVBoxLayout()
        position_container.setLayout(position_layout)
        
        # X position display
        x_layout = QHBoxLayout()
        x_label = QLabel("X:")
        x_label.setMinimumWidth(20)
        x_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        self.x_value_label = QLabel("0.000 V")
        self.x_value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.x_value_label.setMinimumWidth(80)
        
        # Style the value label
        value_font = QFont()
        value_font.setFamily("Courier")
        value_font.setPointSize(9)
        self.x_value_label.setFont(value_font)
        
        x_layout.addWidget(x_label)
        x_layout.addWidget(self.x_value_label)
        x_layout.addStretch()
        position_layout.addLayout(x_layout)
        
        # Y position display
        y_layout = QHBoxLayout()
        y_label = QLabel("Y:")
        y_label.setMinimumWidth(20)
        y_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        self.y_value_label = QLabel("0.000 V")
        self.y_value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.y_value_label.setMinimumWidth(80)
        self.y_value_label.setFont(value_font)
        
        y_layout.addWidget(y_label)
        y_layout.addWidget(self.y_value_label)
        y_layout.addStretch()
        position_layout.addLayout(y_layout)
        
        main_layout.addWidget(position_container)
        
        # Set fixed size for compact appearance
        self.setFixedWidth(150)
        self.setFixedHeight(120)
        
    def update_position(self, x_voltage, y_voltage):
        """Update the displayed position values"""
        # Only update if not in a main scan to avoid performance issues
        if not self.scan_in_progress:
            self.current_x_voltage = x_voltage
            self.current_y_voltage = y_voltage
            
            # Update display labels
            self.x_value_label.setText(f"{x_voltage:.3f} V")
            self.y_value_label.setText(f"{y_voltage:.3f} V")
    
    def set_scan_in_progress(self, in_progress):
        """Set the scan in progress flag to control updates"""
        self.scan_in_progress = in_progress
    
    def get_current_position(self):
        """Get the current tracked position"""
        return self.current_x_voltage, self.current_y_voltage
    
    def reset_position(self):
        """Reset position display to zero"""
        self.update_position(0.0, 0.0) 