"""
Piezo Z-axis control widget for the Napari Scanning SPD application.

This widget provides control over the Z-axis piezo stage, allowing users to:
- View current position
- Set position via spinbox
- Move to specific positions with proper settling time
"""

import threading
import time
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QDoubleSpinBox, QPushButton
)
from PyQt5.QtCore import Qt, pyqtSignal
from napari.utils.notifications import show_info
from piezo_controller import PiezoController

class PiezoControlWidget(QWidget):
    """Widget for controlling the Z-axis piezo stage"""
    _update_position_signal = pyqtSignal(float)
    _update_status_signal = pyqtSignal(str)
    _notify_signal = pyqtSignal(str)
    
    def __init__(self, piezo_controller=None, parent=None):
        super().__init__(parent)
        self.piezo = piezo_controller if piezo_controller else PiezoController()
        self.setup_ui()

        self._update_position_signal.connect(self._set_position_ui)
        self._update_status_signal.connect(self._set_status_ui)
        self._notify_signal.connect(self._on_notify)

        if piezo_controller and piezo_controller._is_connected:
            self._update_ui_with_current_position()
        else:
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
        
        pos_label = QLabel("Position:")
        controls_layout.addWidget(pos_label)
        
        # Position spinbox (1 nm resolution = 0.001 µm)
        self.pos_spinbox = QDoubleSpinBox()
        self.pos_spinbox.setRange(0, 450)  # 0-450 µm range
        self.pos_spinbox.setDecimals(2)    # Show nm precision
        self.pos_spinbox.setSingleStep(0.1) # 100 nm step for fine control
        self.pos_spinbox.setFixedWidth(120)
        self.pos_spinbox.valueChanged.connect(self._on_spinbox_changed)
        
        controls_layout.addWidget(self.pos_spinbox)
        controls_layout.addStretch()
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
                try:
                    time.sleep(0.5)
                    current_pos = float(str(self.piezo.channel.GetPosition()))
                    print(f"Current position: {current_pos:.2f} µm")
                    self._update_status_signal.emit("Connected")
                    self._update_position_signal.emit(current_pos)
                except Exception as e:
                    self._update_status_signal.emit("Error")
                    self._notify_signal.emit(f"❌ Error getting piezo position: {str(e)}")
            else:
                self._update_status_signal.emit("Connection Failed")
                self._notify_signal.emit("❌ Failed to connect to piezo controller")
        
        threading.Thread(target=connect, daemon=True).start()
    
    def _on_spinbox_changed(self, value):
        """Handle spinbox value changes"""
        self._move_piezo(value)
    
    def _move_piezo(self, position_um: float, settling_time: float = 0.1):
        """Move the piezo to the specified position with fixed settling time
        
        Args:
            position_um (float): Target position in micrometers
            settling_time (float): Time to wait for the piezo to settle after movement, in seconds
        """
        def move():
            if not self.piezo._is_connected:
                self._notify_signal.emit("❌ Piezo not connected")
                return
                
            try:
                if self.piezo.set_position(position_um):
                    time.sleep(settling_time)
                    self._notify_signal.emit(f"✓ Moved to {position_um:.2f} µm")
                else:
                    self._notify_signal.emit("❌ Failed to set position")
            except Exception as e:
                self._notify_signal.emit(f"❌ Error: {str(e)}")
        
        threading.Thread(target=move, daemon=True).start()
    
    def _update_ui_with_current_position(self):
        """Query position in background and update UI via signals. Safe to call from any thread."""
        def query():
            try:
                if self.piezo._is_connected:
                    time.sleep(0.5)
                    current_pos = float(str(self.piezo.channel.GetPosition()))
                    print(f"Current position: {current_pos:.2f} µm")
                    self._update_status_signal.emit("Connected")
                    self._update_position_signal.emit(current_pos)
                else:
                    self._update_status_signal.emit("Not Connected")
            except Exception as e:
                self._update_status_signal.emit("Error")
                self._notify_signal.emit(f"❌ Error getting piezo position: {str(e)}")
        threading.Thread(target=query, daemon=True).start()

    def _set_position_ui(self, position):
        """Update position widgets on the main thread"""
        self.pos_spinbox.blockSignals(True)
        self.pos_spinbox.setValue(position)
        self.pos_spinbox.blockSignals(False)

    def _set_status_ui(self, status):
        """Update status label on the main thread"""
        self.status_label.setText(status)

    def _on_notify(self, msg):
        """Show notification on the main thread"""
        show_info(msg)
    
    def cleanup(self):
        """Cleanup resources when closing"""
        if self.piezo._is_connected:
            self.piezo.disconnect()
