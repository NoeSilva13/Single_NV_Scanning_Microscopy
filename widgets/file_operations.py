"""
File operations widgets for the Napari Scanning SPD application.

Contains widgets for:
- Loading saved scans
- Future file operations like export, import, etc.
"""

import time
import numpy as np
from qtpy.QtWidgets import QFileDialog, QMessageBox
from magicgui import magicgui
from napari.utils.notifications import show_info
from utils import MICRONS_PER_VOLT


def _is_um_format(data):
    """Return True if the saved file already stores positions in micrometers."""
    files = getattr(data, 'files', [])
    if 'units' in files:
        try:
            return str(data['units']) == 'um'
        except Exception:
            return False
    return 'format_version' in files


def load_scan(viewer, scan_params_manager=None, scan_points_manager=None, update_widget_func=None):
    """Factory function to create load_scan widget with dependencies"""
    
    def display_scan_parameters(data):
        """Display scan parameters in a message box"""
        try:
            params = []
            unit = 'µm' if _is_um_format(data) else 'V'
            # Basic scan parameters
            if 'x_range' in data:
                params.append(f"X Range: {data['x_range'][0]:.3f}{unit} to {data['x_range'][1]:.3f}{unit}")
            if 'y_range' in data:
                params.append(f"Y Range: {data['y_range'][0]:.3f}{unit} to {data['y_range'][1]:.3f}{unit}")
            if 'z_range' in data:
                params.append(f"Z Range: {data['z_range'][0]:.3f}µm to {data['z_range'][1]:.3f}µm")
            if 'scan_mode' in data:
                params.append(f"Scan Mode: {data['scan_mode']}")
            if 'x_resolution' in data:
                params.append(f"X Resolution: {data['x_resolution']} px")
            if 'y_resolution' in data:
                params.append(f"Y Resolution: {data['y_resolution']} px")
            if 'dwell_time' in data:
                params.append(f"Dwell Time: {data['dwell_time']:.3f} s")
            if 'timestamp' in data:
                params.append(f"Timestamp: {data['timestamp']}")
            
            # Scale information
            if 'scale_x' in data and 'scale_y' in data:
                params.append(f"Scale: {data['scale_x']:.3f} × {data['scale_y']:.3f} µm/px")
            
            # Create message box with parameters
            msg = QMessageBox()
            msg.setWindowTitle("Scan Parameters")
            msg.setText("Loaded scan parameters:\n\n" + "\n".join(params))
            msg.setIcon(QMessageBox.Icon.Information)
            
            # Style the message box to match Napari dark theme
            msg.setStyleSheet("""
                QMessageBox {
                    background-color: #262930;
                    color: #ffffff;
                }
                QMessageBox QLabel {
                    color: #ffffff;
                }
                QPushButton {
                    background-color: #44475a;
                    color: #ffffff;
                    border: 1px solid #44475a;
                    padding: 5px 15px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #6272a4;
                    border: 1px solid #6272a4;
                }
                QPushButton:pressed {
                    background-color: #3c3f4c;
                }
            """)
            
            # Apply is only meaningful for 2D XY-style files with ranges/resolutions.
            can_apply = (
                scan_params_manager and scan_points_manager and update_widget_func
                and 'x_range' in data and 'y_range' in data
                and 'x_resolution' in data and 'y_resolution' in data
            )
            if can_apply:
                msg.setStandardButtons(QMessageBox.StandardButton.Apply | QMessageBox.StandardButton.Ok)
                result = msg.exec()
                
                # If Apply was clicked, update the scan parameters (µm canonical).
                if result == QMessageBox.StandardButton.Apply:
                    x_range = np.asarray(data['x_range'], dtype=float)
                    y_range = np.asarray(data['y_range'], dtype=float)
                    # Old files stored ranges in volts; convert to µm using the
                    # saved calibration if present, otherwise the current one.
                    if not _is_um_format(data):
                        mpv = float(data['microns_per_volt']) if 'microns_per_volt' in data else MICRONS_PER_VOLT
                        x_range = x_range * mpv
                        y_range = y_range * mpv

                    update_params = {
                        'x_range': x_range.tolist(),
                        'y_range': y_range.tolist(),
                        'x_res': int(data['x_resolution']),
                        'y_res': int(data['y_resolution'])
                    }
                    if 'dwell_time' in data:
                        update_params['dwell_time'] = float(data['dwell_time'])
                    
                    scan_params_manager.update_scan_parameters(**update_params)
                    scan_points_manager.update_points(
                        x_range=x_range.tolist(),
                        y_range=y_range.tolist(),
                        x_res=int(data['x_resolution']),
                        y_res=int(data['y_resolution'])
                    )
                    update_widget_func()
                    show_info("✨ Applied scan parameters from loaded file")
            else:
                msg.exec()
                
        except Exception as e:
            show_info(f"⚠️ Could not display all parameters: {str(e)}")
    
    @magicgui(call_button="📂 Load Scan")
    def _load_scan():
        """Load a previously saved scan with correct scaling"""
        # Open file dialog to select .npz file
        file_dialog = QFileDialog()
        file_dialog.setNameFilter("Scan files (*.npz)")
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        
        if file_dialog.exec():
            filenames = file_dialog.selectedFiles()
            if filenames:
                try:
                    # Load the .npz file
                    data = np.load(filenames[0], allow_pickle=True)
                    image = data['image']

                    # Generate unique name for the layer
                    timestamp = time.strftime("%H-%M-%S")
                    layer_name = f"Loaded Scan {timestamp}"

                    # Scale/units are always stored in µm/px, so both old (volts)
                    # and new (µm) files visualize identically. 3D volumes carry a
                    # third (Z) scale.
                    if image.ndim == 3:
                        scale_z = float(data['scale_z']) if 'scale_z' in data else 1.0
                        scale_y = float(data['scale_y'])
                        scale_x = float(data['scale_x'])
                        new_layer = viewer.add_image(
                            image,
                            name=layer_name,
                            colormap="viridis",
                            blending="additive",
                            visible=True,
                            scale=(scale_z, scale_y, scale_x),
                            units=('µm', 'µm', 'µm')
                        )
                    else:
                        scale_x = float(data['scale_x'])
                        scale_y = float(data['scale_y'])
                        new_layer = viewer.add_image(
                            image,
                            name=layer_name,
                            colormap="viridis",
                            blending="additive",
                            visible=True,
                            scale=(scale_y, scale_x),
                            units=('µm', 'µm')
                        )
                    
                    # Set contrast limits
                    if not np.all(np.isnan(image)):
                        min_val = np.nanmin(image)
                        max_val = np.nanmax(image)
                        if not np.isclose(min_val, max_val):
                            new_layer.contrast_limits = (min_val, max_val)
                    
                    show_info(f"✨ Loaded scan as '{layer_name}'")
                    
                    # Display scan parameters
                    display_scan_parameters(data)
                    
                except Exception as e:
                    show_info(f"❌ Error loading scan: {str(e)}")
    
    return _load_scan 