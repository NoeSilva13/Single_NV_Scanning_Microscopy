"""
Galvo Position Tracker Widget for the Napari Scanning SPD application.

Contains the GalvoPositionTrackerWidget class for tracking and displaying
the current position of the galvo scanner.
"""

import numpy as np
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout, QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QPalette, QColor
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
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Setup the user interface"""
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        self.setLayout(main_layout)
        
        # Title
        title_label = QLabel("Galvo Scanner Position")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                background-color: #2b2b2b;
                padding: 8px;
                border-radius: 4px;
                margin-bottom: 5px;
            }
        """)
        main_layout.addWidget(title_label)
        
        # Position display container with improved styling
        position_container = QFrame()
        position_container.setFrameStyle(QFrame.Box)
        position_container.setLineWidth(2)
        position_container.setStyleSheet("""
            QFrame {
                border: 2px solid #555555;
                border-radius: 6px;
                background-color: #262930;
                padding: 10px;
            }
        """)
        position_layout = QGridLayout()
        position_layout.setSpacing(8)
        position_layout.setContentsMargins(10, 10, 10, 10)
        position_container.setLayout(position_layout)
        
        # Headers
        header_font = QFont()
        header_font.setBold(True)
        header_font.setPointSize(9)
        
        axis_header = QLabel("Axis")
        axis_header.setFont(header_font)
        axis_header.setAlignment(Qt.AlignCenter)
        axis_header.setStyleSheet("color: #00d4aa; padding: 5px;")
        
        voltage_header = QLabel("Voltage (V)")
        voltage_header.setFont(header_font)
        voltage_header.setAlignment(Qt.AlignCenter)
        voltage_header.setStyleSheet("color: #00d4aa; padding: 5px;")
        
        distance_header = QLabel("Distance (µm)")
        distance_header.setFont(header_font)
        distance_header.setAlignment(Qt.AlignCenter)
        distance_header.setStyleSheet("color: #00d4aa; padding: 5px;")
        
        position_layout.addWidget(axis_header, 0, 0)
        position_layout.addWidget(voltage_header, 0, 1)
        position_layout.addWidget(distance_header, 0, 2)
        
        # X position display
        x_label = QLabel("X:")
        x_label.setAlignment(Qt.AlignCenter)
        x_label.setStyleSheet("color: #ffffff; padding: 5px; font-weight: bold;")
        
        self.x_value_label = QLabel("0.000")
        self.x_value_label.setAlignment(Qt.AlignCenter)
        self.x_value_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 5px;
                font-family: 'Courier New';
                font-weight: bold;
            }
        """)
        
        self.x_distance_label = QLabel("0.0")
        self.x_distance_label.setAlignment(Qt.AlignCenter)
        self.x_distance_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 5px;
                font-family: 'Courier New';
                font-weight: bold;
            }
        """)
        
        position_layout.addWidget(x_label, 1, 0)
        position_layout.addWidget(self.x_value_label, 1, 1)
        position_layout.addWidget(self.x_distance_label, 1, 2)
        
        # Y position display
        y_label = QLabel("Y:")
        y_label.setAlignment(Qt.AlignCenter)
        y_label.setStyleSheet("color: #ffffff; padding: 5px; font-weight: bold;")
        
        self.y_value_label = QLabel("0.000")
        self.y_value_label.setAlignment(Qt.AlignCenter)
        self.y_value_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 5px;
                font-family: 'Courier New';
                font-weight: bold;
            }
        """)
        
        self.y_distance_label = QLabel("0.0")
        self.y_distance_label.setAlignment(Qt.AlignCenter)
        self.y_distance_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 5px;
                font-family: 'Courier New';
                font-weight: bold;
            }
        """)
        
        position_layout.addWidget(y_label, 2, 0)
        position_layout.addWidget(self.y_value_label, 2, 1)
        position_layout.addWidget(self.y_distance_label, 2, 2)
        
        # Set column stretch for better layout
        position_layout.setColumnStretch(0, 1)  # Axis column
        position_layout.setColumnStretch(1, 2)  # Voltage column
        position_layout.setColumnStretch(2, 2)  # Distance column
        
        main_layout.addWidget(position_container)
        
        # Add some spacing at the bottom
        main_layout.addStretch()
        
        # Set minimum size instead of fixed size for better flexibility
        self.setMinimumWidth(250)
        self.setMinimumHeight(180)
        
        # Set size policy for better resizing behavior
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        
        # Apply global styling to ensure proper display in Napari
        self.setStyleSheet("""
            QWidget {
                background-color: #262930;
                color: #ffffff;
            }
        """)
        
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
    
    def showEvent(self, event):
        """Ensure proper sizing when widget is shown"""
        super().showEvent(event)
        # Force a layout update to ensure proper display
        self.updateGeometry()
        self.adjustSize() 