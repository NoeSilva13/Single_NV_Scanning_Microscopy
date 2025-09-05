#!/usr/bin/env python3
"""
Qt-based CCD Camera Spectrometer Application
Uses POA camera to capture horizontal line spectra and display wavelength vs intensity plots
"""

import sys
import time
import numpy as np
from typing import Optional, Tuple
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QGridLayout, QLabel, QSlider, QPushButton, 
                            QSpinBox, QDoubleSpinBox, QComboBox, QGroupBox, QSplitter,
                            QCheckBox, QStatusBar, QMessageBox, QFileDialog)
from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal, QMutex
from PyQt5.QtGui import QPixmap, QImage, QFont
import pyqtgraph as pg
import cv2

# Import camera module
from Camera.camera_video_mode import POACameraController
from Camera import pyPOACamera


class CameraWorker(QThread):
    """Worker thread for camera operations"""
    frame_ready = pyqtSignal(np.ndarray)
    error_occurred = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.camera = POACameraController()
        self.running = False
        self.mutex = QMutex()
        
    def initialize_camera(self, camera_index: int = 0) -> bool:
        """Initialize camera with 1920x1080 resolution"""
        try:
            # Connect with 1920x1080 resolution
            success = self.camera.connect(camera_index, width=1920, height=1080)
            if success:
                # Set image format to RAW8 for better performance
                self.camera.image_format = pyPOACamera.POAImgFormat.POA_RAW8
                return True
            else:
                self.error_occurred.emit("Failed to connect to camera")
                return False
        except Exception as e:
            self.error_occurred.emit(f"Camera initialization error: {str(e)}")
            return False
    
    def start_streaming(self):
        """Start camera streaming"""
        self.mutex.lock()
        self.running = True
        self.mutex.unlock()
        
        if self.camera.is_connected:
            if self.camera.start_stream():
                self.start()
            else:
                self.error_occurred.emit("Failed to start camera stream")
    
    def stop_streaming(self):
        """Stop camera streaming"""
        self.mutex.lock()
        self.running = False
        self.mutex.unlock()
        
        if self.camera.is_connected:
            self.camera.stop_stream()
        
        self.wait()
    
    def run(self):
        """Main camera acquisition loop"""
        while True:
            self.mutex.lock()
            should_run = self.running
            self.mutex.unlock()
            
            if not should_run:
                break
                
            if self.camera.is_connected and self.camera.is_streaming:
                frame = self.camera.get_frame()
                if frame is not None:
                    self.frame_ready.emit(frame)
                    
            self.msleep(33)  # ~30 FPS
    
    def set_exposure(self, exposure_us: int):
        """Set camera exposure time"""
        if self.camera.is_connected:
            self.camera.set_exposure(exposure_us)
    
    def set_gain(self, gain: int):
        """Set camera gain"""
        if self.camera.is_connected:
            self.camera.set_gain(gain)
    
    def get_camera_info(self) -> dict:
        """Get camera information"""
        if self.camera.is_connected:
            return {
                'width': self.camera.img_width,
                'height': self.camera.img_height,
                'exposure': self.camera.get_exposure(),
                'gain': self.camera.get_gain(),
                'model': self.camera.camera_props.cameraModelName if self.camera.camera_props else 'Unknown'
            }
        return {}
    
    def cleanup(self):
        """Clean up camera resources"""
        self.stop_streaming()
        self.camera.disconnect()


class SpectrumProcessor:
    """Process camera frames to extract spectral data"""
    
    def __init__(self):
        self.wavelength_calibration = None
        self.roi_start_y = 0
        self.roi_height = 50
        self.roi_start_x = 0
        self.roi_width = 1920
        self.dark_frame = None
        self.reference_frame = None
        
    def set_roi(self, start_y: int, height: int, start_x: int = 0, width: int = 1920):
        """Set region of interest for spectrum extraction"""
        self.roi_start_y = start_y
        self.roi_height = height
        self.roi_start_x = start_x
        self.roi_width = width
    
    def set_wavelength_calibration(self, wavelengths: np.ndarray):
        """Set wavelength calibration array"""
        self.wavelength_calibration = wavelengths
    
    def set_dark_frame(self, frame: np.ndarray):
        """Set dark frame for subtraction"""
        if frame is not None:
            # Extract ROI with both x and y dimensions and average vertically
            roi = frame[self.roi_start_y:self.roi_start_y + self.roi_height, 
                       self.roi_start_x:self.roi_start_x + self.roi_width]
            self.dark_frame = np.mean(roi, axis=0)
    
    def set_reference_frame(self, frame: np.ndarray):
        """Set reference frame for normalization"""
        if frame is not None:
            # Extract ROI with both x and y dimensions and average vertically
            roi = frame[self.roi_start_y:self.roi_start_y + self.roi_height, 
                       self.roi_start_x:self.roi_start_x + self.roi_width]
            self.reference_frame = np.mean(roi, axis=0)
    
    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Extract spectrum from frame
        
        Returns:
            tuple: (wavelengths, intensities) or (pixels, intensities) if no calibration
        """
        # Handle different frame formats
        if len(frame.shape) == 3:
            # Color or multi-channel image, convert to grayscale
            if frame.shape[2] == 3:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                frame = frame[:, :, 0]  # Take first channel
        
        # Extract ROI with both x and y dimensions
        roi = frame[self.roi_start_y:self.roi_start_y + self.roi_height, 
                   self.roi_start_x:self.roi_start_x + self.roi_width]
        
        # Average vertically to get horizontal line spectrum
        spectrum = np.mean(roi, axis=0, dtype=np.float64)
        
        # Apply dark frame subtraction
        if self.dark_frame is not None:
            spectrum = spectrum - self.dark_frame
        
        # Apply reference normalization
        if self.reference_frame is not None:
            ref_corrected = self.reference_frame
            if self.dark_frame is not None:
                ref_corrected = ref_corrected - self.dark_frame
            
            # Avoid division by zero
            ref_corrected = np.where(ref_corrected > 0, ref_corrected, 1)
            spectrum = spectrum / ref_corrected
        
        # Create x-axis (wavelengths or pixels)
        if self.wavelength_calibration is not None:
            # Extract the wavelength range corresponding to the selected x ROI
            x_axis = self.wavelength_calibration[self.roi_start_x:self.roi_start_x + self.roi_width]
        else:
            # Use pixel indices relative to the ROI start
            x_axis = np.arange(self.roi_start_x, self.roi_start_x + len(spectrum))
        
        return x_axis, spectrum
    
    def create_default_wavelength_calibration(self, num_pixels: int, 
                                           start_wavelength: float = 400.0,
                                           end_wavelength: float = 800.0) -> np.ndarray:
        """Create default linear wavelength calibration"""
        return np.linspace(start_wavelength, end_wavelength, num_pixels)


class SpectrometerMainWindow(QMainWindow):
    """Main window for the spectrometer application"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CCD Camera Spectrometer")
        self.setGeometry(100, 100, 1400, 800)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #262930;
                color: #ffffff;
            }
            QWidget {
                background-color: #262930;
                color: #ffffff;
            }
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
            QPushButton:disabled {
                background-color: #555555;
                color: #999999;
            }
            QGroupBox {
                color: #ffffff;
                border: 2px solid #555555;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #00d4aa;
            }
            QLabel {
                color: #ffffff;
            }
            QLineEdit {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px;
                font-size: 10pt;
            }
            QLineEdit:focus {
                border: 2px solid #00d4aa;
            }
            QSpinBox, QDoubleSpinBox {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px;
                font-size: 10pt;
            }
            QSpinBox:focus, QDoubleSpinBox:focus {
                border: 2px solid #00d4aa;
            }
            QTextEdit {
                background-color: #1e1e1e;
                color: #00ff00;
                border: 1px solid #555555;
                border-radius: 4px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 9pt;
            }
            QProgressBar {
                border: 1px solid #555555;
                border-radius: 4px;
                background-color: #3c3c3c;
                text-align: center;
                color: #ffffff;
            }
            QProgressBar::chunk {
                background-color: #00d4aa;
                border-radius: 3px;
            }
            QScrollArea {
                background-color: #262930;
                border: none;
            }
            QSplitter::handle {
                background-color: #555555;
            }
        """)
        # Initialize components
        self.camera_worker = CameraWorker()
        self.spectrum_processor = SpectrumProcessor()
        self.current_frame = None
        self.is_recording = False
        self.recorded_spectra = []
        
        # Setup UI
        self.setup_ui()
        self.setup_connections()
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready - Start camera, then use ROI button in camera view to select spectrum region")
        
        # Initialize camera
        self.initialize_camera()
    
    def setup_ui(self):
        """Setup the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout(central_widget)
        
        # Create splitter for resizable panels
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # Left panel - Camera view and controls
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # Camera view with performance optimizations
        self.camera_view = pg.ImageView()
        self.camera_view.setMinimumSize(400, 300)
        
        # Optimize ImageView for better performance
        self.camera_view.ui.histogram.setEnabled(False)  # Disable histogram during resize
        self.camera_view.ui.roiBtn.setCheckable(True)    # Make ROI button toggle-able
        
        left_layout.addWidget(self.camera_view)
        
        # Setup ROI button with simpler implementation
        self.setup_roi_button()
        
        # ROI controls
        roi_group = QGroupBox("ROI Settings")
        roi_layout = QGridLayout(roi_group)
        
        # Add instruction label
        instruction_label = QLabel("1. Start camera first\n2. Click ROI button in camera view\n3. Drag rectangle over spectral region\n4. Click 'Apply Visual ROI' button")
        instruction_label.setWordWrap(True)
        instruction_label.setStyleSheet("color: #00d4aa; font-size: 9pt; font-style: italic;")
        roi_layout.addWidget(instruction_label, 0, 0, 1, 2)
        
        roi_layout.addWidget(QLabel("Start Y:"), 1, 0)
        self.roi_start_spinbox = QSpinBox()
        self.roi_start_spinbox.setRange(0, 1920)  # Swapped from 1080 due to rotation
        self.roi_start_spinbox.setValue(900)  # Adjusted for rotation
        roi_layout.addWidget(self.roi_start_spinbox, 1, 1)
        
        roi_layout.addWidget(QLabel("Height:"), 2, 0)
        self.roi_height_spinbox = QSpinBox()
        self.roi_height_spinbox.setRange(1, 500)
        self.roi_height_spinbox.setValue(50)
        roi_layout.addWidget(self.roi_height_spinbox, 2, 1)
        
        roi_layout.addWidget(QLabel("Start X:"), 3, 0)
        self.roi_start_x_spinbox = QSpinBox()
        self.roi_start_x_spinbox.setRange(0, 1080)  # Swapped from 1920 due to rotation
        self.roi_start_x_spinbox.setValue(0)
        roi_layout.addWidget(self.roi_start_x_spinbox, 3, 1)
        
        roi_layout.addWidget(QLabel("Width:"), 4, 0)
        self.roi_width_spinbox = QSpinBox()
        self.roi_width_spinbox.setRange(1, 1080)  # Swapped from 1920 due to rotation
        self.roi_width_spinbox.setValue(1080)  # Adjusted for rotation
        roi_layout.addWidget(self.roi_width_spinbox, 4, 1)
        
        # Add the ROI button after it's created
        if hasattr(self, 'apply_visual_roi_button'):
            roi_layout.addWidget(self.apply_visual_roi_button, 5, 0, 1, 2)
        
        left_layout.addWidget(roi_group)
        
        # Camera controls
        camera_group = QGroupBox("Camera Controls")
        camera_layout = QGridLayout(camera_group)
        
        # Exposure control
        camera_layout.addWidget(QLabel("Exposure:"), 0, 0)
        self.exposure_label = QLabel("50.0 ms")
        self.exposure_label.setMinimumWidth(60)
        self.exposure_label.setAlignment(Qt.AlignCenter)
        camera_layout.addWidget(self.exposure_label, 0, 1)
        
        self.exposure_slider = QSlider(Qt.Horizontal)
        self.exposure_slider.setRange(1, 10000)  # 0.1ms to 10000ms (will divide by 10)
        self.exposure_slider.setValue(500)  # 50ms default
        self.exposure_slider.setToolTip("Exposure time in milliseconds")
        camera_layout.addWidget(self.exposure_slider, 0, 2)
        
        # Gain control
        camera_layout.addWidget(QLabel("Gain:"), 1, 0)
        self.gain_label = QLabel("300")
        self.gain_label.setMinimumWidth(60)
        self.gain_label.setAlignment(Qt.AlignCenter)
        camera_layout.addWidget(self.gain_label, 1, 1)
        
        self.gain_slider = QSlider(Qt.Horizontal)
        self.gain_slider.setRange(0, 1000)
        self.gain_slider.setValue(300)
        self.gain_slider.setToolTip("Camera gain (0-1000)")
        camera_layout.addWidget(self.gain_slider, 1, 2)
        
        # Control buttons
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Camera")
        self.stop_button = QPushButton("Stop Camera")
        self.stop_button.setEnabled(False)
        
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        camera_layout.addLayout(button_layout, 2, 0, 1, 3)
        
        left_layout.addWidget(camera_group)
        
        # Calibration controls
        cal_group = QGroupBox("Wavelength Calibration")
        cal_layout = QGridLayout(cal_group)
        
        cal_layout.addWidget(QLabel("Start λ (nm):"), 0, 0)
        self.start_wavelength_spinbox = QDoubleSpinBox()
        self.start_wavelength_spinbox.setRange(200, 1000)
        self.start_wavelength_spinbox.setValue(400)
        self.start_wavelength_spinbox.setSuffix(" nm")
        cal_layout.addWidget(self.start_wavelength_spinbox, 0, 1)
        
        cal_layout.addWidget(QLabel("End λ (nm):"), 1, 0)
        self.end_wavelength_spinbox = QDoubleSpinBox()
        self.end_wavelength_spinbox.setRange(200, 1000)
        self.end_wavelength_spinbox.setValue(800)
        self.end_wavelength_spinbox.setSuffix(" nm")
        cal_layout.addWidget(self.end_wavelength_spinbox, 1, 1)
        
        self.apply_calibration_button = QPushButton("Apply Calibration")
        cal_layout.addWidget(self.apply_calibration_button, 2, 0, 1, 2)
        
        left_layout.addWidget(cal_group)
        

        
        # Right panel - Spectrum display
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # Spectrum plot
        self.spectrum_plot = pg.PlotWidget()
        self.spectrum_plot.setLabel('left', 'Intensity')
        self.spectrum_plot.setLabel('bottom', 'Wavelength (nm)')
        self.spectrum_plot.setTitle('Spectrum')
        self.spectrum_plot.showGrid(x=True, y=True)
        right_layout.addWidget(self.spectrum_plot)
        
        # Recording controls
        record_group = QGroupBox("Recording")
        record_layout = QHBoxLayout(record_group)
        
        self.record_button = QPushButton("Start Recording")
        self.save_button = QPushButton("Save Spectrum")
        self.clear_button = QPushButton("Clear")
        
        record_layout.addWidget(self.record_button)
        record_layout.addWidget(self.save_button)
        record_layout.addWidget(self.clear_button)
        
        right_layout.addWidget(record_group)
        
        # Add panels to splitter
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
    
    def setup_connections(self):
        """Setup signal connections"""
        # Camera worker signals
        self.camera_worker.frame_ready.connect(self.update_frame)
        self.camera_worker.error_occurred.connect(self.handle_error)
        
        # Button connections
        self.start_button.clicked.connect(self.start_camera)
        self.stop_button.clicked.connect(self.stop_camera)
        self.apply_calibration_button.clicked.connect(self.apply_wavelength_calibration)
        
        # Control connections
        self.exposure_slider.valueChanged.connect(self.update_exposure)
        self.gain_slider.valueChanged.connect(self.update_gain)
        self.roi_start_spinbox.valueChanged.connect(self.update_roi)
        self.roi_height_spinbox.valueChanged.connect(self.update_roi)
        self.roi_start_x_spinbox.valueChanged.connect(self.update_roi)
        self.roi_width_spinbox.valueChanged.connect(self.update_roi)
        

        
        # Recording controls
        self.record_button.clicked.connect(self.toggle_recording)
        self.save_button.clicked.connect(self.save_spectrum)
        self.clear_button.clicked.connect(self.clear_spectrum)
    
    def sync_gui_with_camera_values(self):
        """Synchronize GUI controls with actual camera values"""
        try:
            # Wait a moment for camera to be ready
            import time
            time.sleep(0.1)
            
            info = self.camera_worker.get_camera_info()
            if info:
                # Get actual camera values
                actual_exposure_us = info.get('exposure', 50000)
                actual_gain = info.get('gain', 300)
                
                # Convert exposure from microseconds to milliseconds
                actual_exposure_ms = actual_exposure_us / 1000.0
                
                # Only update GUI if values are different from current GUI values
                current_exposure_ms = self.exposure_slider.value() / 10.0  # Convert slider value to ms
                current_gain = self.gain_slider.value()
                
                if abs(current_exposure_ms - actual_exposure_ms) > 0.1 or current_gain != actual_gain:
                    # Temporarily disconnect signals to avoid triggering camera updates
                    self.exposure_slider.valueChanged.disconnect()
                    self.gain_slider.valueChanged.disconnect()
                    
                    # Update GUI with actual values
                    self.exposure_slider.setValue(int(actual_exposure_ms * 10))  # Convert ms to slider value
                    self.gain_slider.setValue(actual_gain)
                    
                    # Update labels
                    self.exposure_label.setText(f"{actual_exposure_ms:.1f} ms")
                    self.gain_label.setText(str(actual_gain))
                    
                    # Reconnect signals
                    self.exposure_slider.valueChanged.connect(self.update_exposure)
                    self.gain_slider.valueChanged.connect(self.update_gain)
                    
                    print(f"GUI updated with actual camera values - Exposure: {actual_exposure_ms:.1f}ms, Gain: {actual_gain}")
                
                # Update status to show actual values
                self.status_bar.showMessage(f"Camera ready - Exposure: {actual_exposure_ms:.1f}ms, Gain: {actual_gain}")
                
        except Exception as e:
            print(f"Error syncing GUI with camera values: {e}")
    
    def initialize_camera(self):
        """Initialize camera connection"""
        self.status_bar.showMessage("Initializing camera...")
        
        # Try to initialize camera
        if self.camera_worker.initialize_camera():
            info = self.camera_worker.get_camera_info()
            self.status_bar.showMessage(f"Camera ready: {info.get('model', 'Unknown')} - {info.get('width', 0)}x{info.get('height', 0)}")
            
            # Sync GUI with actual camera values
            self.sync_gui_with_camera_values()
            
            # Set initial ROI
            self.update_roi()
            
            # Apply default wavelength calibration
            self.apply_wavelength_calibration()
        else:
            self.status_bar.showMessage("Failed to initialize camera")
    
    def start_camera(self):
        """Start camera streaming"""
        self.camera_worker.start_streaming()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        
        # Sync GUI with actual camera values after streaming starts
        self.sync_gui_with_camera_values()
        
        self.status_bar.showMessage("Camera streaming started")
    
    def stop_camera(self):
        """Stop camera streaming"""
        self.camera_worker.stop_streaming()
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_bar.showMessage("Camera streaming stopped")
    
    def update_frame(self, frame: np.ndarray):
        """Update camera view and process spectrum"""
        self.current_frame = frame
        
        # Rotate frame 90 degrees clockwise to compensate for camera rotation
        rotated_frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        
        # Display frame in camera view
        self.camera_view.setImage(rotated_frame.T)
        
        # Process spectrum using the rotated frame
        wavelengths, intensities = self.spectrum_processor.process_frame(rotated_frame)
        
        # Update spectrum plot
        self.spectrum_plot.clear()
        self.spectrum_plot.plot(wavelengths, intensities, pen='#00d4aa', width=2)
        
        # If recording, save spectrum
        if self.is_recording:
            self.recorded_spectra.append((wavelengths.copy(), intensities.copy()))
    
    def handle_error(self, error_msg: str):
        """Handle camera errors"""
        self.status_bar.showMessage(f"Error: {error_msg}")
        QMessageBox.critical(self, "Camera Error", error_msg)
    
    def update_exposure(self, value: int):
        """Update camera exposure from slider"""
        exposure_ms = value / 10.0  # Convert slider value to ms (0.1ms precision)
        exposure_us = int(exposure_ms * 1000)  # Convert ms to us
        self.exposure_label.setText(f"{exposure_ms:.1f} ms")
        self.camera_worker.set_exposure(exposure_us)
    
    def update_gain(self, value: int):
        """Update camera gain from slider"""
        self.gain_label.setText(str(value))
        self.camera_worker.set_gain(value)
    

    
    def apply_wavelength_calibration(self):
        """Apply wavelength calibration"""
        start_wl = self.start_wavelength_spinbox.value()
        end_wl = self.end_wavelength_spinbox.value()
        
        # Get camera width (assuming 1920 pixels)
        info = self.camera_worker.get_camera_info()
        width = info.get('width', 1920)
        
        # Create linear calibration
        wavelengths = self.spectrum_processor.create_default_wavelength_calibration(
            width, start_wl, end_wl)
        self.spectrum_processor.set_wavelength_calibration(wavelengths)
        
        # Update plot labels
        self.spectrum_plot.setLabel('bottom', 'Wavelength (nm)')
        self.status_bar.showMessage(f"Wavelength calibration applied: {start_wl}-{end_wl} nm")
    

    def toggle_recording(self):
        """Toggle spectrum recording"""
        if self.is_recording:
            self.is_recording = False
            self.record_button.setText("Start Recording")
            self.status_bar.showMessage(f"Recording stopped. {len(self.recorded_spectra)} spectra recorded")
        else:
            self.is_recording = True
            self.recorded_spectra = []
            self.record_button.setText("Stop Recording")
            self.status_bar.showMessage("Recording started")
    
    def save_spectrum(self):
        """Save current or recorded spectra"""
        if self.recorded_spectra:
            # Save recorded spectra
            filename, _ = QFileDialog.getSaveFileName(self, "Save Recorded Spectra", "", "CSV Files (*.csv)")
            if filename:
                self.save_spectra_to_file(filename, self.recorded_spectra)
        elif self.current_frame is not None:
            # Save current spectrum
            filename, _ = QFileDialog.getSaveFileName(self, "Save Current Spectrum", "", "CSV Files (*.csv)")
            if filename:
                wavelengths, intensities = self.spectrum_processor.process_frame(self.current_frame)
                self.save_spectra_to_file(filename, [(wavelengths, intensities)])
    
    def save_spectra_to_file(self, filename: str, spectra: list):
        """Save spectra to CSV file"""
        try:
            with open(filename, 'w') as f:
                if len(spectra) == 1:
                    # Single spectrum
                    wavelengths, intensities = spectra[0]
                    f.write("Wavelength,Intensity\n")
                    for w, i in zip(wavelengths, intensities):
                        f.write(f"{w:.2f},{i:.6f}\n")
                else:
                    # Multiple spectra
                    f.write("Wavelength," + ",".join([f"Spectrum_{i+1}" for i in range(len(spectra))]) + "\n")
                    wavelengths = spectra[0][0]  # Assume all have same wavelength axis
                    for j, w in enumerate(wavelengths):
                        line = f"{w:.2f}"
                        for wavelengths_i, intensities_i in spectra:
                            line += f",{intensities_i[j]:.6f}"
                        f.write(line + "\n")
            
            self.status_bar.showMessage(f"Spectra saved to {filename}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save file: {str(e)}")
    
    def clear_spectrum(self):
        """Clear spectrum plot"""
        self.spectrum_plot.clear()
        self.recorded_spectra = []
        self.status_bar.showMessage("Spectrum cleared")
    
    def setup_roi_button(self):
        """Setup ROI button with simplified functionality"""
        try:
            # Enable ROI functionality but don't auto-sync
            self.camera_view.ui.roiBtn.setEnabled(True)
            self.camera_view.ui.roiBtn.setToolTip("Click to enable visual ROI selection on camera image")
            
            # Connect ROI button to our initialization
            self.camera_view.ui.roiBtn.clicked.connect(self._handle_roi_button_click)
            
            # Create the apply button
            self.apply_visual_roi_button = QPushButton("Apply Visual ROI")
            self.apply_visual_roi_button.setToolTip("Apply the visual ROI selection to spectrum processing")
            self.apply_visual_roi_button.clicked.connect(self.apply_visual_roi)
            

            
        except Exception as e:
            print(f"ROI setup error: {e}")
            # Create disabled button as fallback
            self.apply_visual_roi_button = QPushButton("Visual ROI Unavailable")
            self.apply_visual_roi_button.setEnabled(False)
            self.status_bar.showMessage("ROI setup failed - using manual controls only")
    
    def initialize_visual_roi(self):
        """Initialize the visual ROI with proper size and position"""
        try:
            # Pause camera during ROI operations for better performance
            self._pause_camera_for_roi()
            
            # Give PyQtGraph time to create the ROI
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(100, self._setup_roi_rectangle)
            
        except Exception as e:
            print(f"Initialize visual ROI error: {e}")
            self.status_bar.showMessage("Error initializing visual ROI")
    
    def _setup_roi_rectangle(self):
        """Setup the ROI rectangle with proper dimensions and optimizations"""
        try:
            roi_item = self.camera_view.roi
            if roi_item is not None:
                # Disable real-time processing during setup to improve performance
                roi_item.setAcceptedMouseButtons(pg.QtCore.Qt.LeftButton)
                
                # Get current ROI settings or use defaults
                start_x = self.roi_start_x_spinbox.value()
                start_y = self.roi_start_spinbox.value()
                width = self.roi_width_spinbox.value()
                height = self.roi_height_spinbox.value()
                
                # Get image dimensions for proper sizing
                if self.current_frame is not None:
                    if len(self.current_frame.shape) == 3:
                        # After 90-degree rotation, width and height are swapped
                        img_width, img_height = self.current_frame.shape[:2]
                    else:
                        # After 90-degree rotation, width and height are swapped
                        img_width, img_height = self.current_frame.shape
                else:
                    # Use defaults if no frame available (swapped for 90-degree rotation)
                    img_height, img_width = 1920, 1080
                
                # Set ROI size from spinbox values
                roi_width = width
                roi_height = height
                
                # Position the ROI from spinbox values
                roi_x = start_x
                roi_y = start_y
                
                # Optimize ROI for better performance
                self._optimize_roi_performance(roi_item)
                
                # Set the ROI rectangle
                roi_item.setPos([roi_x, roi_y])
                roi_item.setSize([roi_width, roi_height])
                
                # Make sure it's visible
                roi_item.show()
                
                self.status_bar.showMessage(f"Visual ROI initialized: drag to move, resize with corners to select X/Y region. Camera paused for performance.")
                
            else:
                self.status_bar.showMessage("ROI not available yet - please try again")
                # Resume camera if ROI setup failed
                self._resume_camera_from_roi()
                
        except Exception as e:
            print(f"Setup ROI rectangle error: {e}")
            self.status_bar.showMessage("Error setting up ROI rectangle")
            # Resume camera on error
            self._resume_camera_from_roi()
    
    def _optimize_roi_performance(self, roi_item):
        """Optimize ROI for better performance during resize operations"""
        try:
            # Disable some computationally expensive features
            if hasattr(roi_item, 'setAcceptedMouseButtons'):
                roi_item.setAcceptedMouseButtons(pg.QtCore.Qt.LeftButton)
            
            # Connect signals for better performance management
            if hasattr(roi_item, 'sigRegionChanged'):
                roi_item.sigRegionChanged.connect(self._on_roi_changing)
            
            if hasattr(roi_item, 'sigRegionChangeFinished'):
                # Only update when resize is finished, not during
                roi_item.sigRegionChangeFinished.connect(self._on_roi_resize_finished)
            
            # Set reasonable bounds to prevent extreme resizing
            if hasattr(roi_item, 'maxBounds'):
                roi_item.maxBounds = pg.QtCore.QRectF(0, 0, 1920, 1080)
            
            # Disable real-time ROI statistics computation
            if hasattr(roi_item, 'setVisible'):
                roi_item.setVisible(True)
            
        except Exception as e:
            print(f"ROI optimization error: {e}")
    
    def _on_roi_changing(self):
        """Handle ROI changes during resize (temporary performance optimization)"""
        try:
            # Temporarily reduce camera update frequency during ROI resize
            if hasattr(self, '_roi_resize_active'):
                return
                
            self._roi_resize_active = True
            self.status_bar.showMessage("Resizing ROI... (release mouse to finish)")
            
            # Use a timer to detect when resize is done
            if hasattr(self, '_roi_resize_timer'):
                self._roi_resize_timer.stop()
            
            from PyQt5.QtCore import QTimer
            self._roi_resize_timer = QTimer()
            self._roi_resize_timer.setSingleShot(True)
            self._roi_resize_timer.timeout.connect(self._on_roi_resize_timeout)
            self._roi_resize_timer.start(500)  # 500ms delay
            
        except Exception as e:
            print(f"ROI changing error: {e}")
    
    def _on_roi_resize_timeout(self):
        """Handle ROI resize timeout"""
        try:
            self._roi_resize_active = False
            self.status_bar.showMessage("ROI resize completed - click 'Apply Visual ROI' to use")
        except Exception as e:
            print(f"ROI resize timeout error: {e}")
    
    def _on_roi_resize_finished(self):
        """Handle ROI resize completion"""
        try:
            # Update status when resize is complete
            self.status_bar.showMessage("ROI resize completed - click 'Apply Visual ROI' to use")
        except Exception as e:
            print(f"ROI resize finished error: {e}")
    
    def _pause_camera_for_roi(self):
        """Pause camera during ROI operations for better performance"""
        try:
            # Avoid double-pausing - check if flags exist AND are True
            if (hasattr(self, '_camera_was_streaming') and 
                hasattr(self, '_roi_pause_active') and 
                self._camera_was_streaming and 
                self._roi_pause_active):
                return  # Already paused
                
            # Check if camera worker thread is running (same approach as stop_camera button)
            is_camera_running = (self.camera_worker.isRunning() and 
                               self.camera_worker.camera.is_connected and 
                               hasattr(self, 'current_frame') and 
                               self.current_frame is not None)
            
            # Remember current state
            self._camera_was_streaming = is_camera_running
            self._roi_pause_active = True
            
            if self._camera_was_streaming:
                # Use exact same approach as stop_camera button
                self.camera_worker.stop_streaming()
                self.status_bar.showMessage("Camera paused for ROI operations...")
                
                # Update button states (same as stop_camera)
                self.start_button.setEnabled(True)
                self.stop_button.setEnabled(False)
            else:
                self.status_bar.showMessage("Camera already stopped - ROI ready")
                
        except Exception as e:
            print(f"Pause camera error: {e}")
            self._camera_was_streaming = False
            self._roi_pause_active = False
    
    def _resume_camera_from_roi(self):
        """Resume camera after ROI operations are complete"""
        try:
            # Only resume if camera was streaming before we paused it
            if (hasattr(self, '_camera_was_streaming') and 
                hasattr(self, '_roi_pause_active') and 
                self._camera_was_streaming and 
                self._roi_pause_active):
                
                if self.camera_worker.camera.is_connected:
                    # Use exact same approach as start_camera button
                    self.camera_worker.start_streaming()
                    self.status_bar.showMessage("Camera resumed after ROI operations")
                    
                    # Update button states (same as start_camera)
                    self.start_button.setEnabled(False)
                    self.stop_button.setEnabled(True)
                else:
                    self.status_bar.showMessage("Camera not connected - cannot resume")
                
            else:
                self.status_bar.showMessage("Camera state unchanged")
                
            # Reset the flags
            self._camera_was_streaming = False
            self._roi_pause_active = False
                
        except Exception as e:
            print(f"Resume camera error: {e}")
            self._camera_was_streaming = False
            self._roi_pause_active = False
    
    def _handle_roi_button_click(self):
        """Handle ROI button clicks (both enable and disable)"""
        try:
            # Check if ROI is being enabled or disabled
            if self.camera_view.ui.roiBtn.isChecked():
                # ROI is being enabled - initialize it
                self.initialize_visual_roi()
            else:
                # ROI is being disabled - resume camera
                self._resume_camera_from_roi()
                self.status_bar.showMessage("ROI disabled - camera resumed")
                
        except Exception as e:
            print(f"Handle ROI button click error: {e}")
            self.status_bar.showMessage("Error handling ROI button")
            # Try to resume camera on error
            self._resume_camera_from_roi()
    


    
    def apply_visual_roi(self):
        """Apply the current visual ROI selection to our spectrum processing"""
        try:
            roi_item = self.camera_view.roi
            if roi_item is not None and self.current_frame is not None:
                # Get ROI position and size
                pos = roi_item.pos()
                size = roi_item.size()
                
                # Extract X and Y position and size (roi uses [x, y] format)
                start_x = int(pos[0])
                start_y = int(pos[1])
                width = int(size[0])
                height = int(size[1])
                
                # Clamp values to valid ranges
                start_x = max(0, min(start_x, 1919))
                start_y = max(0, min(start_y, 1079))
                width = max(1, min(width, 1920 - start_x))
                height = max(1, min(height, 1080 - start_y))
                
                # Update our controls
                self.roi_start_spinbox.setValue(start_y)
                self.roi_height_spinbox.setValue(height)
                self.roi_start_x_spinbox.setValue(start_x)
                self.roi_width_spinbox.setValue(width)
                
                # Update spectrum processor
                self.spectrum_processor.set_roi(start_y, height, start_x, width)
                
                # Close ROI view by unchecking the ROI button (temporarily disconnect to avoid double-resume)
                self.camera_view.ui.roiBtn.clicked.disconnect(self._handle_roi_button_click)
                self.camera_view.ui.roiBtn.setChecked(False)
                self.camera_view.ui.roiBtn.clicked.connect(self._handle_roi_button_click)
                
                # Resume camera after applying ROI
                self._resume_camera_from_roi()
                
                self.status_bar.showMessage(f"Visual ROI applied: X={start_x}, Y={start_y}, Width={width}, Height={height}. ROI closed, camera resumed.")
            else:
                self.status_bar.showMessage("No visual ROI active or no camera frame available")
                # Close ROI view and resume camera even if ROI application failed
                self.camera_view.ui.roiBtn.clicked.disconnect(self._handle_roi_button_click)
                self.camera_view.ui.roiBtn.setChecked(False)
                self.camera_view.ui.roiBtn.clicked.connect(self._handle_roi_button_click)
                self._resume_camera_from_roi()
        except Exception as e:
            print(f"Apply visual ROI error: {e}")
            self.status_bar.showMessage("Error applying visual ROI - using manual controls")
            # Close ROI view and resume camera on error
            self.camera_view.ui.roiBtn.clicked.disconnect(self._handle_roi_button_click)
            self.camera_view.ui.roiBtn.setChecked(False)
            self.camera_view.ui.roiBtn.clicked.connect(self._handle_roi_button_click)
            self._resume_camera_from_roi()
    

    def update_roi(self):
        """Update ROI settings"""
        start_y = self.roi_start_spinbox.value()
        height = self.roi_height_spinbox.value()
        start_x = self.roi_start_x_spinbox.value()
        width = self.roi_width_spinbox.value()
        self.spectrum_processor.set_roi(start_y, height, start_x, width)
    
    def closeEvent(self, event):
        """Handle application close"""
        self.camera_worker.cleanup()
        event.accept()


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    # Note: Main styling is now applied in the SpectrometerMainWindow class
    # This ensures consistent styling across all components
    
    window = SpectrometerMainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main() 