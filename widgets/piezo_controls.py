"""
Piezo Z-axis control widget for the Napari Scanning SPD application.

This widget provides control over the Z-axis piezo stage, allowing users to:
- View current position
- Set position via spinbox or slider
- Move to specific positions with proper settling time
"""

import threading
import time
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QDoubleSpinBox, QSlider, QPushButton
)
from PyQt5.QtCore import Qt
from napari.utils.notifications import show_info
from piezo_controller import PiezoController

class PiezoControlWidget(QWidget):
    """Widget for controlling the Z-axis piezo stage"""
    
    def __init__(self, piezo_controller=None, parent=None):
        super().__init__(parent)
        self.piezo = piezo_controller if piezo_controller else PiezoController()
        self.setup_ui()
        if piezo_controller and piezo_controller._is_connected:
            # If we got an already connected controller, update the UI
            self._update_ui_with_current_position()
        else:
            # Otherwise try to connect
            self._connect_piezo()
        
    def setup_ui(self):
        """Set up the user interface"""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Add title
        title = QLabel("Z-Axis Control (µm)")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Create position display and controls in a horizontal layout
        controls_layout = QHBoxLayout()
        
        # Position label and spinbox in a sub-layout
        spinbox_layout = QHBoxLayout()
        pos_label = QLabel("Position:")
        spinbox_layout.addWidget(pos_label)
        
        # Position spinbox (1 nm resolution = 0.001 µm)
        self.pos_spinbox = QDoubleSpinBox()
        self.pos_spinbox.setRange(0, 450)  # 0-450 µm range
        self.pos_spinbox.setDecimals(3)    # Show nm precision
        self.pos_spinbox.setSingleStep(0.1) # 100 nm step for fine control
        self.pos_spinbox.setFixedWidth(120)
        self.pos_spinbox.valueChanged.connect(self._on_spinbox_changed)
        spinbox_layout.addWidget(self.pos_spinbox)
        spinbox_layout.addStretch()
        controls_layout.addLayout(spinbox_layout)
        
        # Position slider (0.1 µm resolution for smoother UI)
        self.pos_slider = QSlider(Qt.Horizontal)
        self.pos_slider.setRange(0, 4500)  # Range * 10 for 0.1 µm resolution
        self.pos_slider.valueChanged.connect(self._on_slider_changed)
        self.pos_slider.setMinimumWidth(200)  # Make slider wider
        controls_layout.addWidget(self.pos_slider)
        
        layout.addLayout(controls_layout)
        
        # Add status label
        self.status_label = QLabel("Not Connected")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Set widget size
        self.setFixedSize(400, 80)
        
    def _connect_piezo(self):
        """Connect to the piezo controller in a separate thread"""
        def connect():
            if self.piezo.connect():
                self._update_ui_with_current_position()
            else:
                self.status_label.setText("Connection Failed")
                show_info("❌ Failed to connect to piezo controller")
        
        threading.Thread(target=connect, daemon=True).start()
    
    def _on_spinbox_changed(self, value):
        """Handle spinbox value changes"""
        # Update slider without triggering its callback
        self.pos_slider.blockSignals(True)
        self.pos_slider.setValue(int(value * 10))
        self.pos_slider.blockSignals(False)
        self._move_piezo(value)
    
    def _on_slider_changed(self, value):
        """Handle slider value changes"""
        # Convert slider value to µm (slider value is 10x for 0.1 µm resolution)
        pos_um = value / 10.0
        # Update spinbox without triggering its callback
        self.pos_spinbox.blockSignals(True)
        self.pos_spinbox.setValue(pos_um)
        self.pos_spinbox.blockSignals(False)
        self._move_piezo(pos_um)
    
    def _move_piezo(self, position_um):
        """Move the piezo to the specified position with proper settling time"""
        def move():
            if not self.piezo._is_connected:
                show_info("❌ Piezo not connected")
                return
                
            try:
                # Get current position for calculating step size
                current_pos = float(str(self.piezo.channel.GetPosition()))
                step_size = abs(position_um - current_pos)
                
                # Set position
                if self.piezo.set_position(position_um):
                    # Wait for settling (25ms typical for 1-100µm steps)
                    settling_time = 0.025 if step_size <= 100 else 0.050
                    time.sleep(settling_time)
                    show_info(f"✓ Moved to {position_um:.3f} µm")
                else:
                    show_info("❌ Failed to set position")
            except Exception as e:
                show_info(f"❌ Error: {str(e)}")
        
        threading.Thread(target=move, daemon=True).start()
    
    def _update_ui_with_current_position(self):
        """Update UI elements with current piezo position"""
        try:
            if self.piezo._is_connected:
                self.status_label.setText("Connected")
                current_pos = float(str(self.piezo.channel.GetPosition()))
                # Block signals to prevent triggering movement callbacks
                self.pos_spinbox.blockSignals(True)
                self.pos_slider.blockSignals(True)
                self.pos_spinbox.setValue(current_pos)
                self.pos_slider.setValue(int(current_pos * 10))
                self.pos_spinbox.blockSignals(False)
                self.pos_slider.blockSignals(False)
            else:
                self.status_label.setText("Not Connected")
        except Exception as e:
            self.status_label.setText("Error")
            show_info(f"❌ Error getting piezo position: {str(e)}")
    
    def cleanup(self):
        """Cleanup resources when closing"""
        if self.piezo._is_connected:
            self.piezo.disconnect()
