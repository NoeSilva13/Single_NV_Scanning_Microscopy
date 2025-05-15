"""
Confocal Single-NV Microscopy Control Software
-------------------------------------------
This software controls a confocal microscope setup for single NV center imaging using:
- Thorlabs LSKGG4 Galvo-Galvo Scanner
- National Instruments USB-6453 DAQ
- Avalanche Photo Diode APD

The system provides real-time visualization and control through a Napari-based GUI.
"""

import numpy as np 
import napari
import time
import json
import nidaqmx
from nidaqmx.constants import (TerminalConfiguration, Edge, CountDirection, AcquisitionType, SampleTimingType)
from galvo_controller import GalvoScannerController
from data_manager import DataManager
import threading
from magicgui import magicgui
from napari.utils.notifications import show_info
from live_plot_napari_widget import live_plot

# --------------------- INITIAL CONFIGURATION ---------------------
# Load scanning parameters from config file
config = json.load(open("config_template.json"))
galvo_controller = GalvoScannerController()  # Initialize galvo scanner control
data_manager = DataManager()  # Initialize data saving system

# Extract scan parameters from config
x_range = config['scan_range']['x']  # X scanning range in volts
y_range = config['scan_range']['y']  # Y scanning range in volts
x_res = config['resolution']['x']    # X resolution in pixels
y_res = config['resolution']['y']    # Y resolution in pixels

# Create initial scanning grids
original_x_points = np.linspace(x_range[0], x_range[1], x_res)
original_y_points = np.linspace(y_range[0], y_range[1], y_res)

# Global state variables
zoom_level = 0          # Current zoom level
max_zoom = 3           # Maximum allowed zoom levels
contrast_limits = (0, 10)  # Initial image contrast range
scan_history = []      # Store scan parameters for zoom history
image = np.zeros((y_res, x_res), dtype=np.float32)  # Initialize empty image
data_path = None       # Path for saving data

# Initialize DAQ monitoring task for APD signal
# RSE (Referenced Single-Ended) configuration for voltage reading
monitor_task = nidaqmx.Task()
monitor_task.ai_channels.add_ai_voltage_chan(galvo_controller.xout_voltage, terminal_config=TerminalConfiguration.RSE)
monitor_task.start()

# Store original parameters for reset functionality
original_scan_params = {
    'x_range': None,
    'y_range': None,
    'x_res': None,
    'y_res': None
}

# --------------------- NAPARI VIEWER SETUP ---------------------
viewer = napari.Viewer() # Initialize Napari viewer
# Set window size (width, height)
viewer.window.resize(1200, 800)
# Add an image layer to display the live scan. Data is initialized as an empty array 'image'.
layer = viewer.add_image(image, name="live scan", colormap="viridis", scale=(1, 1), contrast_limits=contrast_limits)
# Add a shapes layer to display the zoom area. Initially empty.
shapes = viewer.add_shapes(name="zoom area", shape_type="rectangle", edge_color='red', face_color='transparent', edge_width=0)

# --------------------- MPL WIDGET (SIGNAL LIVE PLOT) ---------------------

# Create and add the MPL widget to the viewer for live signal monitoring.
# 'measure_function' is a lambda function that returns the current APD signal value (voltage).
# 'histogram_range' is the number of data points to plot before overwriting.
# 'dt' is the time between data points in seconds (converted to milliseconds internally).
mpl_widget = live_plot(measure_function=lambda: monitor_task.read(), histogram_range=100, dt=0.1)
viewer.window.add_dock_widget(mpl_widget, area='right', name='Signal Plot')

# --------------------- SCANNING ---------------------
def scan_pattern(x_points, y_points):
    """
    Perform a raster scan pattern using the galvo mirrors and collect APD counts.
    
    Args:
        x_points (array): Voltage values for X galvo positions
        y_points (array): Voltage values for Y galvo positions
    
    Returns:
        tuple: The x and y points used for scanning (for history tracking)
    """
    global image, layer, data_path

    height, width = len(y_points), len(x_points)
    image = np.zeros((height, width), dtype=np.float32)
    layer.data = image
    layer.contrast_limits = contrast_limits
    
    # Configure analog output task for galvo control
    with nidaqmx.Task() as ao_task:
        ao_task.ao_channels.add_ao_voltage_chan(galvo_controller.xin_control)  # X galvo
        ao_task.ao_channels.add_ao_voltage_chan(galvo_controller.yin_control)  # Y galvo

        # Perform raster scan
        for y_idx, y in enumerate(y_points):
            for x_idx, x in enumerate(x_points):
                ao_task.write([x, y])  # Move galvos to position
                time.sleep(0.001)      # Settling time for galvos
                voltage = monitor_task.read()  # Read APD signal
                print(voltage)
                image[y_idx, x_idx] = voltage  # Store in image
                layer.data = image  # Update display
    
    # Adjust contrast and save data
    layer.contrast_limits = (np.min(image), np.max(image))
    data_path = data_manager.save_scan_data(image)
    return x_points, y_points

@magicgui(call_button="🔬 New Scan")
def new_scan():
    global original_x_points, original_y_points
    
    def run_new_scan():
        scan_pattern(original_x_points, original_y_points)
        shapes.data = []
    threading.Thread(target=run_new_scan, daemon=True).start()
    show_info("🔬 New scan started")
    

@magicgui(call_button="🎯 Set to Zero")
def close_scanner():
    def run_close():
        galvo_controller.close()
    
    threading.Thread(target=run_close, daemon=True).start()
    show_info("🎯 Scanner set to zero")

@magicgui(call_button="📷 Save Image")
def save_image():
    viewer.screenshot(path=f"{data_path}.png", canvas_only=True, flash=True)
    show_info("📷 Image saved")

# --------------------- SCAN PARAMETERS WIDGET ---------------------
def update_scan_parameters_widget():
    """Update the scan parameters widget with current values."""
    update_scan_parameters.x_min.value = x_range[0]
    update_scan_parameters.x_max.value = x_range[1]
    update_scan_parameters.y_min.value = y_range[0]
    update_scan_parameters.y_max.value = y_range[1]
    update_scan_parameters.x_resolution.value = x_res
    update_scan_parameters.y_resolution.value = y_res

@magicgui(
    x_min={"widget_type": "FloatSpinBox", "value": x_range[0], "min": -10, "max": 10, "step": 0.1},
    x_max={"widget_type": "FloatSpinBox", "value": x_range[1], "min": -10, "max": 10, "step": 0.1},
    y_min={"widget_type": "FloatSpinBox", "value": y_range[0], "min": -10, "max": 10, "step": 0.1},
    y_max={"widget_type": "FloatSpinBox", "value": y_range[1], "min": -10, "max": 10, "step": 0.1},
    x_resolution={"widget_type": "SpinBox", "value": x_res, "min": 2, "max": 100},
    y_resolution={"widget_type": "SpinBox", "value": y_res, "min": 2, "max": 100},
    call_button="Apply Changes"
)
def update_scan_parameters(
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    x_resolution: int,
    y_resolution: int,
) -> None:
    global x_range, y_range, x_res, y_res, original_x_points, original_y_points, config
    
    # Update global variables
    x_range = [x_min, x_max]
    y_range = [y_min, y_max]
    x_res = x_resolution
    y_res = y_resolution
    
    # Update config
    config['scan_range']['x'] = x_range
    config['scan_range']['y'] = y_range
    config['resolution']['x'] = x_res
    config['resolution']['y'] = y_res
    
    # Update scan points
    original_x_points = np.linspace(x_range[0], x_range[1], x_res)
    original_y_points = np.linspace(y_range[0], y_range[1], y_res)
    
    # Save updated config
    with open("config_template.json", 'w') as f:
        json.dump(config, f, indent=4)
    
    show_info('⚠️ Scan parameters updated successfully!')
# --------------------- ZOOM BY REGION ---------------------

zoom_in_progress = False  # Flag global
@shapes.events.data.connect
def on_shape_added(event):
    """
    Handle zoom region selection in the GUI.
    Triggered when user draws a rectangle to zoom into a region.
    Maintains aspect ratio and resolution while zooming into selected area.
    """
    global zoom_level, max_zoom, scan_history
    global original_x_points, original_y_points, zoom_in_progress

    if zoom_in_progress:
        return  # Prevent multiple simultaneous zoom operations

    if zoom_level >= max_zoom:
        show_info(f"⚠️ Max zoom reached ({max_zoom} levels).")
        return

    if len(shapes.data) == 0:
        return

    # Store original parameters on first zoom
    if zoom_level == 0:
        original_scan_params['x_range'] = x_range.copy()
        original_scan_params['y_range'] = y_range.copy()
        original_scan_params['x_res'] = x_res
        original_scan_params['y_res'] = y_res

    # Calculate new scan region from selected rectangle
    rect = shapes.data[-1]
    min_y, min_x = np.floor(np.min(rect, axis=0)).astype(int)
    max_y, max_x = np.ceil(np.max(rect, axis=0)).astype(int)

    # Ensure zoom region stays within image bounds
    height, width = layer.data.shape
    min_x = max(0, min_x)
    max_x = min(width, max_x)
    min_y = max(0, min_y)
    max_y = min(height, max_y)

    # Save current state for zoom history
    scan_history.append((original_x_points, original_y_points))

    # Calculate new scan points maintaining original resolution
    x_zoom = np.linspace(original_x_points[min_x], original_x_points[max_x - 1], x_res)
    y_zoom = np.linspace(original_y_points[min_y], original_y_points[max_y - 1], y_res)

    def run_zoom():
        global original_x_points, original_y_points, zoom_level, zoom_in_progress
        zoom_in_progress = True  # Activate flag
        update_scan_parameters(
            x_min=x_zoom[0],
            x_max=x_zoom[-1],
            y_min=y_zoom[0],
            y_max=y_zoom[-1],
            x_resolution=x_res,
            y_resolution=y_res
        )
        shapes.data = []  # Clear rectangle
        original_x_points, original_y_points = scan_pattern(x_zoom, y_zoom)
        zoom_level += 1
        update_scan_parameters_widget()  # Update widget values to match current zoom
        zoom_in_progress = False  # Release flag

    threading.Thread(target=run_zoom, daemon=True).start()


# --------------------- RESET BUTTON ---------------------
@magicgui(call_button="🔄 Reset Zoom")
def reset_zoom():
    global zoom_level, scan_history, original_x_points, original_y_points, x_range, y_range, x_res, y_res
    shapes.data = []  # Clear rectangle
    if zoom_level == 0:
        show_info("🔁 You are already in the original view.")
        return
    
    
    original_x_points, original_y_points = scan_history[0]
    scan_history.clear()
    zoom_level = 0

    def run_reset():
        update_scan_parameters(
            x_min=original_x_points[0],
            x_max=original_x_points[-1],
            y_min=original_y_points[0],
            y_max=original_y_points[-1],
            x_resolution=x_res,
            y_resolution=y_res
        )
        scan_pattern(original_x_points, original_y_points)
        shapes.data = []
        update_scan_parameters_widget()
        
    threading.Thread(target=run_reset, daemon=True).start()

# Add interface elements to Napari viewer
viewer.window.add_dock_widget(reset_zoom, area="right")         # Reset zoom button
viewer.window.add_dock_widget(new_scan, area="right")          # Start new scan
viewer.window.add_dock_widget(save_image, area="right")        # Save current image
viewer.window.add_dock_widget(close_scanner, area="right")     # Set galvos to zero
viewer.window.add_dock_widget(update_scan_parameters, area="right", name="Scan Parameters")  # Scan parameter controls

napari.run()  # Start the Napari event loop
