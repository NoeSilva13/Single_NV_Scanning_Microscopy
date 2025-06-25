"""
File operations widgets for the Qt-based Scanning SPD application.

Contains widgets for:
- Loading saved scans
- Opening external applications (ODMR GUI)
- Future file operations like export, import, etc.
"""

import time
import subprocess
import sys
import os
import numpy as np
from PyQt5.QtWidgets import QFileDialog, QPushButton
from PyQt5.QtCore import Qt


class LoadScanWidget(QPushButton):
    """Widget for loading saved scans"""
    
    def __init__(self, image_display=None, status_callback=None):
        super().__init__("📂 Load Scan")
        self.image_display = image_display
        self.status_callback = status_callback
        
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
        
        self.clicked.connect(self._load_scan)
    
    def _load_scan(self):
        """Load a previously saved scan with correct scaling"""
        # Open file dialog to select .npz file
        file_dialog = QFileDialog()
        file_dialog.setNameFilter("Scan files (*.npz)")
        file_dialog.setFileMode(QFileDialog.ExistingFile)
        
        if file_dialog.exec_():
            filenames = file_dialog.selectedFiles()
            if filenames:
                try:
                    # Load the .npz file
                    data = np.load(filenames[0])
                    image = data['image']
                    scale_x = data['scale_x']
                    scale_y = data['scale_y']
                    
                    # Generate unique name for the layer
                    timestamp = time.strftime("%H-%M-%S")
                    layer_name = f"Loaded Scan {timestamp}"
                    
                    # Update the image display if available
                    if self.image_display is not None:
                        # For Qt implementation, we can set the loaded image
                        # We'll need to convert the scale information to points
                        # This is a simplified version - you might need to reconstruct x_points and y_points
                        self.image_display.set_image(image)
                        
                        # Set contrast limits
                        if not np.all(np.isnan(image)):
                            min_val = np.nanmin(image)
                            max_val = np.nanmax(image)
                            if not np.isclose(min_val, max_val):
                                self.image_display.set_contrast(min_val, max_val)
                    
                    if self.status_callback:
                        self.status_callback(f"✨ Loaded scan as '{layer_name}'")
                        
                except Exception as e:
                    if self.status_callback:
                        self.status_callback(f"❌ Error loading scan: {str(e)}")


class ODMRGuiWidget(QPushButton):
    """Widget for opening ODMR GUI"""
    
    def __init__(self, status_callback=None):
        super().__init__("📡 ODMR GUI")
        self.status_callback = status_callback
        
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
        
        self.clicked.connect(self._open_odmr_gui)
    
    def _open_odmr_gui(self):
        """Open the ODMR GUI application in a separate process"""
        try:
            # Get the path to the ODMR GUI script
            script_path = os.path.join(os.getcwd(), "odmr_gui_qt.py")
            
            if not os.path.exists(script_path):
                if self.status_callback:
                    self.status_callback(f"❌ ODMR GUI script not found at: {script_path}")
                return
            
            # Launch the ODMR GUI in a separate process
            subprocess.Popen([sys.executable, script_path])
            if self.status_callback:
                self.status_callback("📡 ODMR GUI launched successfully")
            
        except Exception as e:
            if self.status_callback:
                self.status_callback(f"❌ Error launching ODMR GUI: {str(e)}")


def load_scan(image_display=None, status_callback=None):
    """Factory function to create load_scan widget with dependencies"""
    return LoadScanWidget(image_display, status_callback)


def open_odmr_gui(status_callback=None):
    """Factory function to create ODMR GUI button widget"""
    return ODMRGuiWidget(status_callback) 