"""
Scan control widgets for the Napari Scanning SPD application.

Contains magicgui widgets for:
- Starting new scans
- Controlling scanner position
- Saving images
- Resetting zoom
- Updating scan parameters
- Stopping ongoing scans
"""

import threading
import json
import numpy as np
from magicgui import magicgui
from napari.utils.notifications import show_info


def new_scan(scan_pattern_func, scan_points_manager, shapes):
    """Factory function to create new_scan widget with dependencies"""
    
    @magicgui(call_button="🔬 New Scan")
    def _new_scan():
        """Initiates a new scan using the current scan parameters from scan_points_manager.
        Runs the scan in a separate thread to prevent UI freezing.
        """
        def run_new_scan():
            # Get current scan points from the manager
            x_points, y_points = scan_points_manager.get_points()
            scan_pattern_func(x_points, y_points)
            shapes.data = []
        threading.Thread(target=run_new_scan, daemon=True).start()
        show_info("🔬 New scan started")
    
    return _new_scan


def close_scanner(output_task):
    """Factory function to create close_scanner widget with dependencies"""
    
    @magicgui(call_button="🎯 Set to Zero")
    def _close_scanner():
        """Sets the Galvo scanner controller to its zero position.
        Runs in a separate thread.
        """
        def run_close():
            output_task.write([0, 0])
        
        threading.Thread(target=run_close, daemon=True).start()
        show_info("🎯 Scanner set to zero")
    
    return _close_scanner


def save_image(viewer, data_path_func):
    """Factory function to create save_image widget with dependencies"""
    
    @magicgui(call_button="📷 Save Image")
    def _save_image():
        """Saves the current view of the Napari canvas as a PNG image.
        The filename is derived from the data_path of the scan.
        """
        data_path = data_path_func()
        if data_path:
            viewer.screenshot(path=f"{data_path}.png", canvas_only=True, flash=True)
            show_info("📷 Image saved")
        else:
            show_info("❌ No scan data to save")
    
    return _save_image


def reset_zoom(scan_pattern_func, scan_history, config_manager, scan_points_manager,
               shapes, update_scan_parameters_func, update_scan_parameters_widget_func,
               zoom_level_manager):
    """Factory function to create reset_zoom widget with dependencies"""
    
    @magicgui(call_button="🔄 Reset Zoom")
    def _reset_zoom():
        shapes.data = []  # Clear rectangle
        current_zoom = zoom_level_manager.get_zoom_level()
        
        if current_zoom == 0:
            show_info("🔁 You are already in the original view.")
            return
        
        # Get original points from history or use default config values
        if scan_history:
            orig_x_points, orig_y_points = scan_history[0]
        else:
            # Fallback to default config values
            config = config_manager.get_config()
            x_range = config['scan_range']['x']
            y_range = config['scan_range']['y']
            x_res = config['resolution']['x']
            y_res = config['resolution']['y']
            orig_x_points = np.linspace(x_range[0], x_range[1], x_res)
            orig_y_points = np.linspace(y_range[0], y_range[1], y_res)
        
        scan_history.clear()
        zoom_level_manager.set_zoom_level(0)

        def run_reset():
            # Update both managers with the original values
            update_scan_parameters_func(
                x_range=[orig_x_points[0], orig_x_points[-1]],
                y_range=[orig_y_points[0], orig_y_points[-1]],
                x_res=len(orig_x_points),
                y_res=len(orig_y_points)
            )
            scan_points_manager.update_points(
                x_range=[orig_x_points[0], orig_x_points[-1]],
                y_range=[orig_y_points[0], orig_y_points[-1]],
                x_res=len(orig_x_points),
                y_res=len(orig_y_points)
            )
            scan_pattern_func(orig_x_points, orig_y_points)
            shapes.data = []
            update_scan_parameters_widget_func()
            
        threading.Thread(target=run_reset, daemon=True).start()
    
    return _reset_zoom


def update_scan_parameters(config_manager, scan_points_manager):
    """Factory function to create update_scan_parameters widget with dependencies"""
    
    # Get initial values from config
    config = config_manager.get_config()
    x_range = config['scan_range']['x']
    y_range = config['scan_range']['y']
    x_res = config['resolution']['x']
    y_res = config['resolution']['y']
    
    @magicgui(
        x_min={"widget_type": "FloatSpinBox", "value": x_range[0], "min": -10, "max": 10, "step": 0.1, "label": "X Min (V)"},
        x_max={"widget_type": "FloatSpinBox", "value": x_range[1], "min": -10, "max": 10, "step": 0.1, "label": "X Max (V)"},
        y_min={"widget_type": "FloatSpinBox", "value": y_range[0], "min": -10, "max": 10, "step": 0.1, "label": "Y Min (V)"},
        y_max={"widget_type": "FloatSpinBox", "value": y_range[1], "min": -10, "max": 10, "step": 0.1, "label": "Y Max (V)"},
        x_resolution={"widget_type": "SpinBox", "value": x_res, "min": 2, "max": 200, "label": "X Res (px)"},
        y_resolution={"widget_type": "SpinBox", "value": y_res, "min": 2, "max": 200, "label": "Y Res (px)"},
        call_button="Apply Changes"
    )
    def _update_scan_parameters(
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
        x_resolution: int,
        y_resolution: int,
    ) -> None:
        # Update config manager
        config_manager.update_scan_parameters(
            x_range=[x_min, x_max],
            y_range=[y_min, y_max],
            x_res=x_resolution,
            y_res=y_resolution
        )
        
        # Update scan points manager
        scan_points_manager.update_points(
            x_range=[x_min, x_max],
            y_range=[y_min, y_max],
            x_res=x_resolution,
            y_res=y_resolution
        )
        
        show_info('⚠️ Scan parameters updated successfully!')
    
    return _update_scan_parameters


def update_scan_parameters_widget(widget_instance, config_manager):
    """Update the scan parameters widget with current values."""
    def _update_widget():
        config = config_manager.get_config()
        x_range = config['scan_range']['x']
        y_range = config['scan_range']['y']
        x_res = config['resolution']['x']
        y_res = config['resolution']['y']
        
        widget_instance.x_min.value = x_range[0]
        widget_instance.x_max.value = x_range[1]
        widget_instance.y_min.value = y_range[0]
        widget_instance.y_max.value = y_range[1]
        widget_instance.x_resolution.value = x_res
        widget_instance.y_resolution.value = y_res
    
    return _update_widget


def stop_scan(scan_in_progress, stop_scan_requested):
    """Factory function to create stop_scan widget with dependencies"""
    
    @magicgui(call_button="🛑 Stop Scan")
    def _stop_scan():
        """Safely stop the current scanning process."""
        if scan_in_progress[0]:  # Use list to allow modification of mutable object
            stop_scan_requested[0] = True
            show_info("🛑 Stopping scan... Please wait.")
        else:
            show_info("ℹ️ No scan currently in progress.")
    
    return _stop_scan 