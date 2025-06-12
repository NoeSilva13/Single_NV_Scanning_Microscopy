"""
Camera control widgets for the Napari Scanning SPD application.

Contains:
- Camera live view widget
- Single shot capture widget  
- Camera control widget with exposure and gain sliders
- Camera update thread for live view
"""

import time
import numpy as np
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QSlider, QGridLayout, QComboBox, QHBoxLayout
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot, Qt
from magicgui import magicgui, widgets
from napari.utils.notifications import show_info
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


def camera_live(viewer, get_camera_type_func=None):
    """Factory function to create camera_live widget with dependencies"""
    
    @magicgui(call_button="🎥 Camera Live")
    def _camera_live():
        """Start/stop live camera feed in Napari viewer."""
        # Initialize camera controller if not already done
        if not hasattr(_camera_live, 'camera'):
            # Get camera type from callback function
            camera_type = "POA"  # Default
            if get_camera_type_func:
                camera_type = get_camera_type_func()
            
            if camera_type == "ZWO":
                _camera_live.camera = ZWOCameraController()
            else:
                _camera_live.camera = POACameraController()
            
            _camera_live.is_running = False
            _camera_live.update_thread = None
            _camera_live.camera_layer = None
            _camera_live.camera_type = camera_type
        
        def update_layer(frame):
            """Update the Napari layer with new frame"""
            # Reshape frame to 2D if it's 3D with single channel
            if frame.ndim == 3 and frame.shape[2] == 1:
                frame = frame.squeeze()  # Remove single-dimensional entries
            _camera_live.camera_layer.data = frame
            # Add text overlay with settings
            exp_ms = _camera_live.camera.get_exposure() / 1000
            gain = _camera_live.camera.get_gain()
            _camera_live.camera_layer.name = f"Live (Exp: {exp_ms:.0f}ms, Gain: {gain})"
        
        if not _camera_live.is_running:
            # Start camera feed
            if not hasattr(_camera_live, 'camera_layer') or _camera_live.camera_layer not in viewer.layers:
                # Connect to camera
                if not _camera_live.camera.connect(camera_index=0, width=1024, height=1024):  # Set desired resolution
                    show_info("❌ Failed to connect to camera")
                    return
                
                # Get actual image dimensions from camera
                width, height = _camera_live.camera.get_image_dimensions()
                print(f"Camera dimensions: {width}x{height}")
                
                _camera_live.camera.set_exposure(50000)  # 50ms initial exposure
                _camera_live.camera.set_gain(300)        # Initial gain
                
                # Start the stream
                if not _camera_live.camera.start_stream():
                    show_info("❌ Failed to start camera stream")
                    _camera_live.camera.disconnect()
                    return
                
                # Create initial frame with correct dimensions
                initial_frame = np.zeros((height, width), dtype=np.uint8)
                _camera_live.camera_layer = viewer.add_image(
                    initial_frame,
                    name="Live",
                    colormap="gray",
                    blending="additive",
                    visible=True
                )
            else:
                # Reuse existing layer but reconnect camera
                if not _camera_live.camera.connect(camera_index=0, width=1024, height=1024):
                    show_info("❌ Failed to connect to camera")
                    return
                
                if not _camera_live.camera.start_stream():
                    show_info("❌ Failed to start camera stream")
                    _camera_live.camera.disconnect()
                    return
                
                # Get actual image dimensions from camera
                width, height = _camera_live.camera.get_image_dimensions()
                print(f"Camera dimensions: {width}x{height}")
                
                _camera_live.camera.set_exposure(50000)  # 50ms initial exposure
                _camera_live.camera.set_gain(300)        # Initial gain
            
            # Start update thread
            _camera_live.is_running = True
            _camera_live.update_thread = CameraUpdateThread(_camera_live.camera)
            _camera_live.update_thread.frame_ready.connect(update_layer)
            _camera_live.update_thread.start()
            show_info("🎥 Camera live view started")
            _camera_live.call_button.text = "🛑 Stop Camera"
        else:
            # Stop camera feed
            _camera_live.is_running = False
            if _camera_live.update_thread:
                _camera_live.update_thread.stop()
                _camera_live.update_thread = None
            _camera_live.camera.stop_stream()
            _camera_live.camera.disconnect()
            
            # Keep the layer but clear its data
            if hasattr(_camera_live, 'camera_layer') and _camera_live.camera_layer in viewer.layers:
                width, height = _camera_live.camera_layer.data.shape
                _camera_live.camera_layer.data = np.zeros((height, width), dtype=np.uint8)
            
            show_info("🛑 Camera live view stopped")
            _camera_live.call_button.text = "🎥Camera Live"
    
    return _camera_live


def capture_shot(viewer, settings_callback=None, get_camera_type_func=None):
    """Factory function to create capture_shot widget with dependencies"""
    
    @magicgui(call_button="📸 Single Shot")
    def _capture_shot():
        """Take a single image from the camera and display it in a new layer."""
        # Initialize camera if needed
        if not hasattr(_capture_shot, 'camera'):
            # Get camera type from callback function
            camera_type = "POA"  # Default
            if get_camera_type_func:
                camera_type = get_camera_type_func()
            
            if camera_type == "ZWO":
                _capture_shot.camera = ZWOCameraController()
            else:
                _capture_shot.camera = POACameraController()
            
            _capture_shot.camera_type = camera_type
        
        try:
            # Get current settings from callback
            if settings_callback is not None:
                settings = settings_callback()
                exposure_ms = settings['exposure_ms']
                gain = settings['gain']
            else:
                # Fallback to hardcoded values if no callback available
                exposure_ms = 50
                gain = 300
            
            # Connect to camera if not already connected
            if not _capture_shot.camera.is_connected:
                if not _capture_shot.camera.connect(camera_index=0, width=1024, height=1024):
                    show_info("❌ Failed to connect to camera")
                    return
                
                # Set camera settings
                _capture_shot.camera.set_exposure(exposure_ms * 1000)  # Convert ms to µs
                _capture_shot.camera.set_gain(gain)
            else:
                # Update camera settings even if already connected
                _capture_shot.camera.set_exposure(exposure_ms * 1000)  # Convert ms to µs
                _capture_shot.camera.set_gain(gain)
            
            # Start stream temporarily
            if not _capture_shot.camera.start_stream():
                show_info("❌ Failed to start camera stream")
                _capture_shot.camera.disconnect()
                return
            
            # Wait a bit for the camera to settle
            time.sleep(0.1)
            
            # Try to get a frame for up to 1 second
            start_time = time.time()
            frame = None
            while time.time() - start_time < 1.0:
                frame = _capture_shot.camera.get_frame()
                if frame is not None:
                    break
                time.sleep(0.05)
            
            # Stop stream
            _capture_shot.camera.stop_stream()
            
            if frame is not None:
                # Reshape frame if needed
                if frame.ndim == 3 and frame.shape[2] == 1:
                    frame = frame.squeeze()
                
                # Generate unique name for the layer including settings
                timestamp = time.strftime("%H-%M-%S")
                layer_name = f"Camera Shot {timestamp} (Exp: {exposure_ms}ms, Gain: {gain})"
                
                # Add as new layer
                viewer.add_image(
                    frame,
                    name=layer_name,
                    colormap="gray",
                    blending="additive",
                    visible=True
                )
                show_info(f"✨ Captured image saved as '{layer_name}'")
            else:
                show_info("❌ Failed to capture image")
                
        except Exception as e:
            show_info(f"❌ Error capturing image: {str(e)}")
        finally:
            # Cleanup if we connected in this function
            # Check if camera_live widget exists and is connected
            camera_live_exists = hasattr(capture_shot, 'camera_live_widget') and hasattr(capture_shot.camera_live_widget, 'camera')
            if not camera_live_exists or not capture_shot.camera_live_widget.camera.is_connected:
                _capture_shot.camera.disconnect()
    
    return _capture_shot


class CameraControlWidget(QWidget):
    """Camera control widget with camera selection and exposure/gain sliders"""
    
    def __init__(self, camera_live_widget, capture_shot_widget, parent=None):
        super().__init__(parent)
        self.camera_live_widget = camera_live_widget
        self.capture_shot_widget = capture_shot_widget
        
        layout = QGridLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        
        # Camera type selection row
        camera_type_widget = QWidget()
        camera_type_layout = QHBoxLayout()
        camera_type_layout.setSpacing(5)
        camera_type_layout.setContentsMargins(0, 0, 0, 0)
        
        camera_type_label = QLabel("Camera Type:")
        camera_type_layout.addWidget(camera_type_label)
        
        self.camera_type_combo = QComboBox()
        self.camera_type_combo.addItem("POA Camera")
        self.camera_type_combo.addItem("ZWO Camera")
        self.camera_type_combo.currentTextChanged.connect(self.on_camera_type_changed)
        camera_type_layout.addWidget(self.camera_type_combo)
        
        camera_type_widget.setLayout(camera_type_layout)
        layout.addWidget(camera_type_widget, 0, 0, 1, 2)  # Span 2 columns
        
        # Second row: Camera buttons (2 columns)
        layout.addWidget(camera_live_widget.native, 1, 0)
        layout.addWidget(capture_shot_widget.native, 1, 1)
        
        # Third row: Sliders
        # Exposure control (first column)
        exposure_widget = QWidget()
        exposure_layout = QVBoxLayout()
        exposure_layout.setSpacing(0)
        exposure_layout.setContentsMargins(0, 0, 0, 0)
        
        exp_label = QLabel("Exposure (ms):")
        exp_label.setAlignment(Qt.AlignCenter)
        exposure_layout.addWidget(exp_label)
        
        self.exposure_slider = QSlider(Qt.Horizontal)
        self.exposure_slider.setMinimum(1)
        self.exposure_slider.setMaximum(1000)
        self.exposure_slider.setValue(50)
        self.exposure_slider.valueChanged.connect(self.update_exposure)
        exposure_layout.addWidget(self.exposure_slider)
        
        exposure_widget.setLayout(exposure_layout)
        layout.addWidget(exposure_widget, 2, 0)
        
        # Gain control (second column)
        gain_widget = QWidget()
        gain_layout = QVBoxLayout()
        gain_layout.setSpacing(0)
        gain_layout.setContentsMargins(0, 0, 0, 0)
        
        gain_label = QLabel("Gain:")
        gain_label.setAlignment(Qt.AlignCenter)
        gain_layout.addWidget(gain_label)
        
        self.gain_slider = QSlider(Qt.Horizontal)
        self.gain_slider.setMinimum(0)
        self.gain_slider.setMaximum(1000)
        self.gain_slider.setValue(300)
        self.gain_slider.valueChanged.connect(self.update_gain)
        gain_layout.addWidget(self.gain_slider)
        
        gain_widget.setLayout(gain_layout)
        layout.addWidget(gain_widget, 2, 1)
        
        # Set fixed height for better appearance
        self.setFixedHeight(150)  # Increased to accommodate camera selection
    
    def get_camera_type(self):
        """Get the currently selected camera type"""
        if self.camera_type_combo.currentText() == "ZWO Camera":
            return "ZWO"
        else:
            return "POA"
    
    @pyqtSlot(str)
    def on_camera_type_changed(self, camera_type_text):
        """Handle camera type change"""
        # Reset camera instances when type changes
        if hasattr(self.camera_live_widget, 'camera'):
            if self.camera_live_widget.is_running:
                show_info("⚠️ Please stop camera live view before changing camera type")
                return
            
            # Disconnect current camera
            self.camera_live_widget.camera.disconnect()
            del self.camera_live_widget.camera
        
        if hasattr(self.capture_shot_widget, 'camera'):
            self.capture_shot_widget.camera.disconnect()
            del self.capture_shot_widget.camera
        
        # Show info about the change
        camera_type = "ZWO" if camera_type_text == "ZWO Camera" else "POA"
        show_info(f"📷 Switched to {camera_type} camera mode")
    
    @pyqtSlot(int)
    def update_exposure(self, value):
        if hasattr(self.camera_live_widget, 'camera'):
            self.camera_live_widget.camera.set_exposure(value * 1000)  # Convert ms to µs
        if hasattr(self.capture_shot_widget, 'camera'):
            self.capture_shot_widget.camera.set_exposure(value * 1000)  # Convert ms to µs
    
    @pyqtSlot(int)
    def update_gain(self, value):
        if hasattr(self.camera_live_widget, 'camera'):
            self.camera_live_widget.camera.set_gain(value)
        if hasattr(self.capture_shot_widget, 'camera'):
            self.capture_shot_widget.camera.set_gain(value)


def create_camera_control_widget(viewer):
    """Factory function to create a complete camera control widget with proper connections"""
    # Create a settings container to hold current values
    camera_settings = {'exposure_ms': 50, 'gain': 300}
    
    # We need to create the control widget first to have access to get_camera_type
    # So we'll create placeholders first
    camera_control_widget = None
    
    # Camera type callback function
    def get_camera_type():
        if camera_control_widget:
            return camera_control_widget.get_camera_type()
        return "POA"  # Default
    
    # Create the camera live widget with camera type callback
    camera_live_widget = camera_live(viewer, get_camera_type)
    
    # Create capture_shot widget with settings callback and camera type callback
    capture_shot_widget = capture_shot(viewer, lambda: camera_settings, get_camera_type)
    
    # Create the control widget
    camera_control_widget = CameraControlWidget(camera_live_widget, capture_shot_widget)
    
    # Update the settings callback to get values from sliders
    def update_settings():
        camera_settings['exposure_ms'] = camera_control_widget.exposure_slider.value()
        camera_settings['gain'] = camera_control_widget.gain_slider.value()
    
    # Connect slider changes to update the settings
    camera_control_widget.exposure_slider.valueChanged.connect(lambda: update_settings())
    camera_control_widget.gain_slider.valueChanged.connect(lambda: update_settings())
    
    # Initialize settings
    update_settings()
    
    return camera_control_widget 