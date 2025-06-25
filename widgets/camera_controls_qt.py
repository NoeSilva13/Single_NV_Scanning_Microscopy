"""
Camera control widgets for the Qt-based Scanning SPD application.

Contains:
- Camera live view widget
- Single shot capture widget  
- Camera control widget with exposure and gain sliders
- Camera update thread for live view
"""

import time
import numpy as np
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QLabel, QSlider, 
                             QGridLayout, QComboBox, QHBoxLayout, QGroupBox)
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot, Qt
from Camera import POACameraController, ZWOCameraController


class CameraUpdateThread(QThread):
    """Thread for updating camera feed"""
    frame_ready = pyqtSignal(np.ndarray)  # Signal to emit when new frame is ready
    
    def __init__(self, camera):
        super().__init__()
        self.camera = camera
        self.running = True
    
    def run(self):
        while self.running:
            frame = self.camera.get_frame()
            if frame is not None:
                self.frame_ready.emit(frame)
            self.msleep(33)  # ~30 fps
    
    def stop(self):
        self.running = False
        self.wait()


class CameraLiveWidget(QPushButton):
    """Camera live view widget"""
    
    def __init__(self, get_camera_type_func=None, status_callback=None):
        super().__init__("🎥 Camera Live")
        self.get_camera_type_func = get_camera_type_func
        self.status_callback = status_callback
        
        # Initialize camera-related attributes
        self.camera = None
        self.is_running = False
        self.update_thread = None
        self.camera_type = None
        
        # Setup button styling
        self.setStyleSheet("""
            QPushButton {
                background-color: #00d4aa;
                color: #262930;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #00ffcc;
            }
            QPushButton:pressed {
                background-color: #009980;
            }
        """)
        
        self.clicked.connect(self._toggle_camera)
    
    def _toggle_camera(self):
        """Start/stop live camera feed"""
        # Initialize camera controller if not already done or if camera is None
        if self.camera is None:
            # Get camera type from callback function
            camera_type = "POA"  # Default
            if self.get_camera_type_func:
                camera_type = self.get_camera_type_func()
            
            if camera_type == "ZWO":
                self.camera = ZWOCameraController()
            else:
                self.camera = POACameraController()
            
            self.camera_type = camera_type
        
        if not self.is_running:
            # Start camera feed
            # Connect to camera
            if not self.camera.connect(camera_index=0, width=1024, height=1024):  # Set desired resolution
                if self.status_callback:
                    self.status_callback("❌ Failed to connect to camera")
                return
            
            # Get actual image dimensions from camera
            width, height = self.camera.get_image_dimensions()
            print(f"Camera dimensions: {width}x{height}")
            
            self.camera.set_exposure(50000)  # 50ms initial exposure
            self.camera.set_gain(300)        # Initial gain
            
            # Start the stream
            if not self.camera.start_stream():
                if self.status_callback:
                    self.status_callback("❌ Failed to start camera stream")
                self.camera.disconnect()
                return
            
            # Start update thread
            self.is_running = True
            self.update_thread = CameraUpdateThread(self.camera)
            self.update_thread.start()
            
            if self.status_callback:
                self.status_callback("🎥 Camera live view started")
            self.setText("🛑 Stop Camera")
        else:
            # Stop camera feed
            self.is_running = False
            
            # Stop and disconnect the update thread first
            if self.update_thread:
                self.update_thread.stop()
                self.update_thread = None
            
            # Stop camera stream and disconnect
            self.camera.stop_stream()
            self.camera.disconnect()
            
            if self.status_callback:
                self.status_callback("🛑 Camera live view stopped")
            self.setText("🎥 Camera Live")


class CameraShotWidget(QPushButton):
    """Single shot capture widget"""
    
    def __init__(self, settings_callback=None, get_camera_type_func=None, status_callback=None):
        super().__init__("📸 Single Shot")
        self.settings_callback = settings_callback
        self.get_camera_type_func = get_camera_type_func
        self.status_callback = status_callback
        
        # Initialize camera-related attributes
        self.camera = None
        self.camera_type = None
        
        # Setup button styling
        self.setStyleSheet("""
            QPushButton {
                background-color: #00d4aa;
                color: #262930;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #00ffcc;
            }
            QPushButton:pressed {
                background-color: #009980;
            }
        """)
        
        self.clicked.connect(self._capture_shot)
    
    def _capture_shot(self):
        """Take a single image from the camera"""
        # Initialize camera if needed or if camera is None
        if self.camera is None:
            # Get camera type from callback function
            camera_type = "POA"  # Default
            if self.get_camera_type_func:
                camera_type = self.get_camera_type_func()
            
            if camera_type == "ZWO":
                self.camera = ZWOCameraController()
            else:
                self.camera = POACameraController()
            
            self.camera_type = camera_type
        
        try:
            # Get current settings from callback
            if self.settings_callback is not None:
                settings = self.settings_callback()
                exposure_ms = settings['exposure_ms']
                gain = settings['gain']
            else:
                # Fallback to hardcoded values if no callback available
                exposure_ms = 50
                gain = 300
            
            # Connect to camera if not already connected
            if not self.camera.is_connected:
                if not self.camera.connect(camera_index=0, width=1024, height=1024):
                    if self.status_callback:
                        self.status_callback("❌ Failed to connect to camera")
                    return
                
                # Set camera settings
                self.camera.set_exposure(exposure_ms * 1000)  # Convert ms to µs
                self.camera.set_gain(gain)
            else:
                # Update camera settings even if already connected
                self.camera.set_exposure(exposure_ms * 1000)  # Convert ms to µs
                self.camera.set_gain(gain)
            
            # Start stream temporarily
            if not self.camera.start_stream():
                if self.status_callback:
                    self.status_callback("❌ Failed to start camera stream")
                self.camera.disconnect()
                return
            
            # Wait a bit for the camera to settle
            time.sleep(0.1)
            
            # Try to get a frame for up to 1 second
            start_time = time.time()
            frame = None
            while time.time() - start_time < 1.0:
                frame = self.camera.get_frame()
                if frame is not None:
                    break
                time.sleep(0.05)
            
            # Stop stream
            self.camera.stop_stream()
            
            if frame is not None:
                # Handle different frame formats
                if frame.ndim == 3 and frame.shape[2] == 1:
                    # Single channel 3D array - convert to 2D grayscale
                    frame = frame.squeeze()
                elif frame.ndim == 3 and frame.shape[2] == 3:
                    # RGB color image - keep as is
                    pass
                
                # Generate unique timestamp for the layer name
                timestamp = time.strftime("%H-%M-%S")
                
                # Store the frame for potential display (this could be extended to show in a separate window)
                self.last_frame = frame
                
                if self.status_callback:
                    self.status_callback(f"📸 Single shot captured at {timestamp}")
            else:
                if self.status_callback:
                    self.status_callback("❌ Failed to capture frame")
            
        except Exception as e:
            if self.status_callback:
                self.status_callback(f"❌ Error capturing image: {str(e)}")


class CameraControlWidget(QWidget):
    """Camera control widget with exposure and gain sliders"""
    
    def __init__(self, camera_live_widget, capture_shot_widget, status_callback=None, parent=None):
        super().__init__(parent)
        self.camera_live_widget = camera_live_widget
        self.capture_shot_widget = capture_shot_widget
        self.status_callback = status_callback
        
        # Initialize UI
        self.init_ui()
        
        # Initialize settings
        self.exposure_ms = 50
        self.gain = 300
        self.camera_type = "POA"
    
    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Camera type selection
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Camera Type:"))
        
        self.camera_type_combo = QComboBox()
        self.camera_type_combo.addItems(["POA Camera", "ZWO Camera"])
        self.camera_type_combo.currentTextChanged.connect(self.on_camera_type_changed)
        type_layout.addWidget(self.camera_type_combo)
        
        layout.addLayout(type_layout)
        
        # Camera control buttons
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.camera_live_widget)
        button_layout.addWidget(self.capture_shot_widget)
        layout.addWidget(QLabel("Camera Controls:"))
        layout.addLayout(button_layout)
        
        # Exposure control
        exposure_group = QGroupBox("Exposure Control")
        exposure_layout = QVBoxLayout()
        
        self.exposure_label = QLabel("Exposure: 50 ms")
        exposure_layout.addWidget(self.exposure_label)
        
        self.exposure_slider = QSlider(Qt.Horizontal)
        self.exposure_slider.setRange(1, 1000)  # 1-1000 ms
        self.exposure_slider.setValue(50)
        self.exposure_slider.valueChanged.connect(self.update_exposure)
        exposure_layout.addWidget(self.exposure_slider)
        
        exposure_group.setLayout(exposure_layout)
        layout.addWidget(exposure_group)
        
        # Gain control
        gain_group = QGroupBox("Gain Control")
        gain_layout = QVBoxLayout()
        
        self.gain_label = QLabel("Gain: 300")
        gain_layout.addWidget(self.gain_label)
        
        self.gain_slider = QSlider(Qt.Horizontal)
        self.gain_slider.setRange(1, 1000)  # Typical gain range
        self.gain_slider.setValue(300)
        self.gain_slider.valueChanged.connect(self.update_gain)
        gain_layout.addWidget(self.gain_slider)
        
        gain_group.setLayout(gain_layout)
        layout.addWidget(gain_group)
        
        # Apply styling
        self.setStyleSheet("""
            QComboBox {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px;
                font-size: 10pt;
            }
            QComboBox:focus {
                border: 2px solid #00d4aa;
            }
            QSlider::groove:horizontal {
                border: 1px solid #999999;
                height: 8px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #B1B1B1, stop:1 #c4c4c4);
                margin: 2px 0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #00d4aa;
                border: 1px solid #5c5c5c;
                width: 18px;
                margin: -2px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #00ffcc;
            }
        """)
    
    def get_camera_type(self):
        """Get current camera type"""
        combo_text = self.camera_type_combo.currentText()
        return "ZWO" if "ZWO" in combo_text else "POA"
    
    @pyqtSlot(str)
    def on_camera_type_changed(self, camera_type_text):
        """Handle camera type change"""
        if "ZWO" in camera_type_text:
            self.camera_type = "ZWO"
            # ZWO cameras typically have different exposure ranges
            self.exposure_slider.setRange(1, 15000)  # ZWO can go higher
            if self.status_callback:
                self.status_callback("📷 Switched to ZWO camera")
        else:
            self.camera_type = "POA"
            # POA cameras have more limited range
            self.exposure_slider.setRange(1, 1000)
            if self.status_callback:
                self.status_callback("📷 Switched to POA camera")
        
        # Reset both widgets' cameras so they'll be re-initialized with new type
        self.camera_live_widget.camera = None
        self.capture_shot_widget.camera = None
    
    @pyqtSlot(int)
    def update_exposure(self, value):
        """Update exposure setting"""
        self.exposure_ms = value
        self.exposure_label.setText(f"Exposure: {value} ms")
    
    @pyqtSlot(int)
    def update_gain(self, value):
        """Update gain setting"""
        self.gain = value
        self.gain_label.setText(f"Gain: {value}")
    
    def get_settings(self):
        """Get current camera settings"""
        return {
            'exposure_ms': self.exposure_ms,
            'gain': self.gain,
            'camera_type': self.camera_type
        }


def create_camera_control_widget(main_window):
    """Create a camera control widget with all dependencies"""
    
    def get_camera_type():
        """Get camera type from the control widget"""
        return control_widget.get_camera_type()
    
    def get_settings():
        """Get current camera settings"""
        return control_widget.get_settings()
    
    def status_callback(message):
        """Status callback for showing messages"""
        if hasattr(main_window, 'show_status'):
            main_window.show_status(message)
        else:
            print(message)
    
    # Create individual widgets
    camera_live_widget = CameraLiveWidget(get_camera_type, status_callback)
    capture_shot_widget = CameraShotWidget(get_settings, get_camera_type, status_callback)
    
    # Create the control widget
    control_widget = CameraControlWidget(camera_live_widget, capture_shot_widget, status_callback)
    
    return control_widget 