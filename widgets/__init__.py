"""
Widgets package for the Napari Scanning SPD application.

This package contains all UI widgets used in the microscopy control software.
"""

from .scan_controls import (
    new_scan,
    close_scanner,
    save_image,
    reset_zoom,
    update_scan_parameters,
    update_scan_parameters_widget
)

from .camera_controls import (
    camera_live,
    capture_shot,
    CameraControlWidget,
    CameraUpdateThread
)

from .auto_focus import (
    auto_focus,
    SignalBridge,
    create_focus_plot_widget
)

from .single_axis_scan import SingleAxisScanWidget

from .file_operations import load_scan
from .piezo_controls import PiezoControlWidget

__all__ = [
    # Scan controls
    'new_scan',
    'close_scanner', 
    'save_image',
    'reset_zoom',
    'update_scan_parameters',
    'update_scan_parameters_widget',
    
    # Camera controls
    'camera_live',
    'capture_shot',
    'CameraControlWidget',
    'CameraUpdateThread',
    
    # Auto focus
    'auto_focus',
    'SignalBridge',
    'create_focus_plot_widget',
    
    # Single axis scan
    'SingleAxisScanWidget',
    
    # File operations
    'load_scan',
    
    # Piezo controls
    'PiezoControlWidget'
] 