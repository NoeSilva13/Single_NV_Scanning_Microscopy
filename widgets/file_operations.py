"""
File operations widgets for the Napari Scanning SPD application.

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
from PyQt5.QtWidgets import QFileDialog
from magicgui import magicgui
from napari.utils.notifications import show_info


def load_scan(viewer):
    """Factory function to create load_scan widget with dependencies"""
    
    @magicgui(call_button="📂 Load Scan")
    def _load_scan():
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
                    
                    # Add as new layer with correct scale
                    new_layer = viewer.add_image(
                        image,
                        name=layer_name,
                        colormap="viridis",
                        blending="additive",
                        visible=True,
                        scale=(scale_y, scale_x)
                    )
                    
                    # Set contrast limits
                    if not np.all(np.isnan(image)):
                        min_val = np.nanmin(image)
                        max_val = np.nanmax(image)
                        if not np.isclose(min_val, max_val):
                            new_layer.contrast_limits = (min_val, max_val)
                    
                    show_info(f"✨ Loaded scan as '{layer_name}'")
                except Exception as e:
                    show_info(f"❌ Error loading scan: {str(e)}")
    
    return _load_scan 


def open_odmr_gui():
    """Factory function to create ODMR GUI button widget"""
    
    @magicgui(call_button="📡 ODMR GUI")
    def _open_odmr_gui():
        """Open the ODMR GUI application in a separate process"""
        try:
            # Get the path to the ODMR GUI script
            script_path = os.path.join(os.getcwd(), "odmr_gui_qt.py")
            
            if not os.path.exists(script_path):
                show_info(f"❌ ODMR GUI script not found at: {script_path}")
                return
            
            # Launch the ODMR GUI in a separate process
            subprocess.Popen([sys.executable, script_path])
            show_info("📡 ODMR GUI launched successfully")
            
        except Exception as e:
            show_info(f"❌ Error launching ODMR GUI: {str(e)}")
    
    return _open_odmr_gui 