"""
Confocal Single-NV Microscopy Control Software
-------------------------------------------
This software controls a confocal microscope setup for single NV center imaging using:
- Thorlabs LSKGG4 Galvo-Galvo Scanner
- National Instruments USB-6453 DAQ
- Single Photon Detector SPD

The system provides real-time visualization and control through a Napari-based GUI.
"""

import sys
import os

# Add the Camera directory to the Python path
camera_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Camera')
if camera_dir not in sys.path:
    sys.path.append(camera_dir)
from camera_video_mode import POACameraController
import cv2

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
from TimeTagger import createTimeTagger, Countrate, Counter, createTimeTaggerVirtual  # Swabian TimeTagger API
from plot_scan_results import plot_scan_results
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QSlider, QFrame, QGridLayout
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt5.QtCore import QObject, pyqtSignal, QThread, QTimerEvent, Qt
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtCore import pyqtSlot
from piezo_controller import PiezoController, simulate_auto_focus

# --------------------- INITIAL CONFIGURATION ---------------------
# Load scanning parameters from config file
config = json.load(open("config_template.json"))
galvo_controller = GalvoScannerController() # Initialize galvo scanner control
data_manager = DataManager() # Initialize data saving system

# Extract scan parameters from config
x_range = config['scan_range']['x']     # X scanning range in volts
y_range = config['scan_range']['y']     # Y scanning range in volts
x_res = config['resolution']['x']       # X resolution in pixels
y_res = config['resolution']['y']       # Y resolution in pixels

# Create initial scanning grids
original_x_points = np.linspace(x_range[0], x_range[1], x_res)
original_y_points = np.linspace(y_range[0], y_range[1], y_res)

# Global state variables
zoom_level = 0          # Current zoom level
max_zoom = 3           # Maximum allowed zoom levels
contrast_limits = (0, 10000)  # Initial image contrast range
scan_history = []      # Store scan parameters for zoom history
image = np.zeros((y_res, x_res), dtype=np.float32)  # Initialize empty image
data_path = None       # Path for saving data

# Initialize DAQ output task for galvo control
output_task = nidaqmx.Task()
output_task.ao_channels.add_ao_voltage_chan(galvo_controller.xin_control)
output_task.ao_channels.add_ao_voltage_chan(galvo_controller.yin_control)
output_task.start()

# Store original parameters for reset functionality
original_scan_params = {
    'x_range': None,
    'y_range': None,
    'x_res': None,
    'y_res': None
}

# --------------------- SCALE FUNCTION ---------------------
def calculate_scale(V1, V2, image_width_px, L=6.86, volts_per_degree=1.33):
    """Calculate microns per pixel based on galvo settings"""
    theta_deg = abs(V2 - V1) / volts_per_degree
    scan_width_mm = 2 * L * np.tan(np.radians(theta_deg / 2))
    return (scan_width_mm * 1000) / image_width_px  # Convert to microns/px

# --------------------- NAPARI VIEWER SETUP ---------------------
viewer = napari.Viewer(title="NV Scanning Microscopy") # Initialize Napari viewer
# Set window size (width, height)
viewer.window.resize(1200, 800)
# Add an image layer to display the live scan. Data is initialized as an empty array 'image'.
layer = viewer.add_image(image, name="live scan", colormap="viridis", scale=(1, 1), contrast_limits=contrast_limits)
# Add a points layer to show current scanner position
points_layer = viewer.add_points(ndim=2, name="scanner position", face_color='red', size=5, opacity=1, symbol='o')
# Add a shapes layer to display the zoom area. Initially empty.
shapes = viewer.add_shapes(name="zoom area", shape_type="rectangle", edge_color='red', face_color='transparent', edge_width=0)

# Configure scale bar
viewer.scale_bar.visible = True
viewer.scale_bar.unit = "µm"
viewer.scale_bar.position = "bottom_left"

# Calculate scale (in microns/pixel)
scale_um_per_px_x = calculate_scale(x_range[0], x_range[1], x_res)
scale_um_per_px_y = calculate_scale(y_range[0], y_range[1], y_res)
layer.scale = (scale_um_per_px_y, scale_um_per_px_x)

# --------------------- TIMETAGGER SETUP ---------------------
#tagger = createTimeTagger() 
#tagger.reset()
#Virtual TimeTagger for testing purposes uncomment the following two lines
tagger = createTimeTaggerVirtual("TimeTagger/time_tags_test.ttbin")
tagger.run()
# Set bin width to 5 ns
binwidth = int(5e9)
n_values = 1
# Set up counter channel (assuming channel 1 is used for SPD input)
counter = Counter(tagger, [1], binwidth, n_values)

# --------------------- CLICK HANDLER FOR SCANNER POSITIONING ---------------------
def on_mouse_click(layer, event):
    """
    Handle mouse click events to move the galvo scanner to the clicked position.
    """
    # Get the clicked coordinates in data space
    coords = layer.world_to_data(event.position)
    x_idx, y_idx = int(round(coords[1])), int(round(coords[0]))  # Swap x,y and round to nearest integer
    
    # Convert from pixel coordinates to voltage values
    x_voltage = np.interp(x_idx, [0, x_res-1], [x_range[0], x_range[1]])
    y_voltage = np.interp(y_idx, [0, y_res-1], [y_range[0], y_range[1]])
    
    # Move the galvo scanner to the clicked position
    try:
        output_task.write([x_voltage, y_voltage])
        show_info(f"Moved scanner to: X={x_voltage:.3f}V, Y={y_voltage:.3f}V")
        
        # Convert coordinates to world space for points layer
        world_coords = layer.data_to_world([y_idx, x_idx])
        points_layer.data = [[world_coords[0], world_coords[1]]]  # Use world coordinates
        
    except Exception as e:
        show_info(f"Error moving scanner: {str(e)}")

# Connect the mouse click handler to the image layer
layer.mouse_drag_callbacks.append(on_mouse_click)

# --------------------- MPL WIDGET (SIGNAL LIVE PLOT) ---------------------

# Create and add the MPL widget to the viewer for live signal monitoring.
# 'measure_function' is a lambda function that returns the current APD signal value (voltage).
# 'histogram_range' is the number of data points to plot before overwriting.
# 'dt' is the time between data points in seconds (converted to milliseconds internally).
mpl_widget = live_plot(measure_function=lambda: counter.getData()[0][0]/(binwidth/1e12), histogram_range=100, dt=0.2)
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
    layer.data = image  # update layer
    layer.contrast_limits = contrast_limits
    
    # Perform raster scan
    for y_idx, y in enumerate(y_points):
        for x_idx, x in enumerate(x_points):
            output_task.write([x, y]) # Move galvos to position
            if x_idx == 0:
                time.sleep(0.05) # Wait for galvos to settle
            else:
                time.sleep(0.001) # Settling time for galvos
                
            counts = counter.getData()[0][0]/(binwidth/1e12) # Read SPD signal
            #time.sleep(binwidth/1e12) # Wait for SPD to count
            print(f"{counts}") # Print counts
            image[y_idx, x_idx] = counts # Store in image
            layer.data = image # Update display
    
    # Create a dictionary with image and scan positions
    scan_data = {
        'image': image,
        'x_points': x_points,
        'y_points': y_points
    }
    data_path = data_manager.save_scan_data(scan_data)
    # Adjust contrast and save data
    layer.contrast_limits = (np.min(image), np.max(image))
    scale_um_per_px_x = calculate_scale(x_points[0], x_points[-1], width)
    scale_um_per_px_y = calculate_scale(y_points[0], y_points[-1], height)
    layer.scale = (scale_um_per_px_y, scale_um_per_px_x)
    plot_scan_results(scan_data, data_path)
    return x_points, y_points # Returns for history

@magicgui(call_button="🔬 New Scan")
def new_scan():
    """Initiates a new scan using the original (full-range) scan parameters.
    Runs the scan in a separate thread to prevent UI freezing.
    """
    global original_x_points, original_y_points
    
    def run_new_scan():
        scan_pattern(original_x_points, original_y_points)
        shapes.data = []
    threading.Thread(target=run_new_scan, daemon=True).start()
    show_info("🔬 New scan started")
    

@magicgui(call_button="🎯 Set to Zero")
def close_scanner():
    """Sets the Galvo scanner controller to its zero position.
    Runs in a separate thread.
    """
    def run_close():
        output_task.write([0, 0])
        
        # Calculate the indices corresponding to 0V for both axes
        x_zero_idx = np.interp(0, [x_range[0], x_range[1]], [0, x_res-1])
        y_zero_idx = np.interp(0, [y_range[0], y_range[1]], [0, y_res-1])
        
        # Convert to world coordinates and update point position
        world_coords = layer.data_to_world([y_zero_idx, x_zero_idx])
        points_layer.data = [[world_coords[0], world_coords[1]]]
    
    threading.Thread(target=run_close, daemon=True).start()
    show_info("🎯 Scanner set to zero")

@magicgui(call_button="📷 Save Image")
def save_image():
    """Saves the current view of the Napari canvas as a PNG image.
    The filename is derived from the data_path of the scan.
    """
    viewer.screenshot(path=f"{data_path}.png", canvas_only=True, flash=True)
    show_info("📷 Image saved")

# --------------------- AUTO FOCUS FUNCTION ---------------------
class SignalBridge(QObject):
    """Bridge to safely create and add widgets from background threads"""
    update_focus_plot_signal = pyqtSignal(list, list, str)
    
    def __init__(self):
        super().__init__()
        self.update_focus_plot_signal.connect(self._update_focus_plot)
        self.focus_plot_widget = None
        self.focus_dock_widget = None
    
    def _update_focus_plot(self, positions, counts, name):
        """Update the focus plot widget from the main thread"""
        # Create plot widget if it doesn't exist
        if self.focus_plot_widget is None:
            self.focus_plot_widget = create_focus_plot_widget(positions, counts)
            self.focus_dock_widget = viewer.window.add_dock_widget(
                self.focus_plot_widget, 
                area='right', 
                name=name
            )
        else:
            # Update existing plot
            self.focus_plot_widget.plot_data(
                x_data=positions,
                y_data=counts,
                x_label='Z Position (µm)',
                y_label='Counts',
                title='Auto-Focus Results',
                peak_annotation=f'Optimal: {positions[np.argmax(counts)]:.2f} µm' if len(counts) > 0 else None
            )

# Create a global signal bridge
signal_bridge = SignalBridge()

@magicgui(call_button="🔍 Auto Focus")
def auto_focus():
    """Automatically find the optimal Z position by scanning for maximum signal"""
    def run_auto_focus():
        try:
            show_info('🔍 Starting Z scan...')
            piezo = PiezoController()
            
            if not piezo.connect():
                show_info('❌ Failed to connect to piezo stage')
                return
            
            try:
                # Get count data using the counter
                count_function = lambda: counter.getData()[0][0]/(binwidth/1e12)
                positions, counts, optimal_pos = piezo.perform_auto_focus(count_function)
                
                show_info(f'✅ Focus optimized at Z = {optimal_pos} µm')
                signal_bridge.update_focus_plot_signal.emit(positions, counts, 'Auto-Focus Plot')
                
            finally:
                piezo.disconnect()
            
        except Exception as e:
            show_info(f'❌ Auto-focus error: {str(e)}')
    
    threading.Thread(target=run_auto_focus, daemon=True).start()

# --------------------- AUTO-FOCUS PLOT WIDGET ---------------------
from plot_widgets.single_axis_plot import SingleAxisPlot

def create_focus_plot_widget(positions, counts):
    """
    Creates a plot widget to display auto-focus results using SingleAxisPlot
    
    Parameters
    ----------
    positions : list
        Z positions scanned during auto-focus
    counts : list
        Photon counts measured at each position
    
    Returns
    -------
    SingleAxisPlot
        A widget containing the focus plot
    """
    plot_widget = SingleAxisPlot()
    plot_widget.plot_data(
        x_data=positions,
        y_data=counts,
        x_label='Z Position (µm)',
        y_label='Counts',
        title='Auto-Focus Results',
        peak_annotation=f'Optimal: {positions[np.argmax(counts)]:.2f} µm' if len(counts) > 0 else None
    )
    return plot_widget

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
    x_min={"widget_type": "FloatSpinBox", "value": x_range[0], "min": -10, "max": 10, "step": 0.1, "label": "X Min (V)"},
    x_max={"widget_type": "FloatSpinBox", "value": x_range[1], "min": -10, "max": 10, "step": 0.1, "label": "X Max (V)"},
    y_min={"widget_type": "FloatSpinBox", "value": y_range[0], "min": -10, "max": 10, "step": 0.1, "label": "Y Min (V)"},
    y_max={"widget_type": "FloatSpinBox", "value": y_range[1], "min": -10, "max": 10, "step": 0.1, "label": "Y Max (V)"},
    x_resolution={"widget_type": "SpinBox", "value": x_res, "min": 2, "max": 100, "label": "X Res (px)"},
    y_resolution={"widget_type": "SpinBox", "value": y_res, "min": 2, "max": 100, "label": "Y Res (px)"},
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
        return  # Prevent multiple simultaneous zoom operations.

    if zoom_level >= max_zoom:
        show_info(f"⚠️ Max zoom reached ({max_zoom} levels).")
        return

    if len(shapes.data) == 0:
        return

    # Save current parameters before zooming
    if zoom_level == 0:
        original_scan_params['x_range'] = x_range.copy()
        original_scan_params['y_range'] = y_range.copy()
        original_scan_params['x_res'] = x_res
        original_scan_params['y_res'] = y_res

    # Calculate new scan region from selected rectangle
    rect1 = shapes.data[-1]
    rect = np.array([layer.world_to_data(point) for point in rect1])
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
        print("🔁 You are already in the original view.")
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

# --------------------- CAMERA CONTROL WIDGET ---------------------

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

@magicgui(call_button="🎥 Camera Live")
def camera_live():
    """Start/stop live camera feed in Napari viewer."""
    global camera_layer
    
    # Initialize camera controller if not already done
    if not hasattr(camera_live, 'camera'):
        camera_live.camera = POACameraController()
        camera_live.is_running = False
        camera_live.update_thread = None
    
    def update_layer(frame):
        """Update the Napari layer with new frame"""
        # Reshape frame to 2D if it's 3D with single channel
        if frame.ndim == 3 and frame.shape[2] == 1:
            frame = frame.squeeze()  # Remove single-dimensional entries
        camera_layer.data = frame
        # Add text overlay with settings
        exp_ms = camera_live.camera.get_exposure() / 1000
        gain = camera_live.camera.get_gain()
        camera_layer.name = f"Camera Live (Exp: {exp_ms:.0f}ms, Gain: {gain})"
    
    if not camera_live.is_running:
        # Start camera feed
        if not hasattr(camera_live, 'camera_layer') or camera_live.camera_layer not in viewer.layers:
            # Connect to camera
            if not camera_live.camera.connect(camera_index=0, width=1024, height=1024):  # Set desired resolution
                show_info("❌ Failed to connect to camera")
                return
            
            # Get actual image dimensions from camera
            width, height = camera_live.camera.get_image_dimensions()
            print(f"Camera dimensions: {width}x{height}")
            
            camera_live.camera.set_exposure(50000)  # 50ms initial exposure
            camera_live.camera.set_gain(300)        # Initial gain
            
            # Start the stream
            if not camera_live.camera.start_stream():
                show_info("❌ Failed to start camera stream")
                camera_live.camera.disconnect()
                return
            
            # Create initial frame with correct dimensions
            initial_frame = np.zeros((height, width), dtype=np.uint8)
            camera_layer = viewer.add_image(
                initial_frame,
                name="Camera Live",
                colormap="gray",
                blending="additive",
                visible=True
            )
            camera_live.camera_layer = camera_layer
        else:
            # Reuse existing layer but reconnect camera
            if not camera_live.camera.connect(camera_index=0, width=1024, height=1024):
                show_info("❌ Failed to connect to camera")
                return
            
            if not camera_live.camera.start_stream():
                show_info("❌ Failed to start camera stream")
                camera_live.camera.disconnect()
                return
            
            # Get actual image dimensions from camera
            width, height = camera_live.camera.get_image_dimensions()
            print(f"Camera dimensions: {width}x{height}")
            
            camera_live.camera.set_exposure(50000)  # 50ms initial exposure
            camera_live.camera.set_gain(300)        # Initial gain
        
        # Start update thread
        camera_live.is_running = True
        camera_live.update_thread = CameraUpdateThread(camera_live.camera)
        camera_live.update_thread.frame_ready.connect(update_layer)
        camera_live.update_thread.start()
        show_info("🎥 Camera live view started")
        camera_live.call_button.text = "🛑 Stop Camera"
    else:
        # Stop camera feed
        camera_live.is_running = False
        if camera_live.update_thread:
            camera_live.update_thread.stop()
            camera_live.update_thread = None
        camera_live.camera.stop_stream()
        camera_live.camera.disconnect()
        
        # Keep the layer but clear its data
        if hasattr(camera_live, 'camera_layer') and camera_live.camera_layer in viewer.layers:
            width, height = camera_live.camera_layer.data.shape
            camera_live.camera_layer.data = np.zeros((height, width), dtype=np.uint8)
        
        show_info("🛑 Camera live view stopped")
        camera_live.call_button.text = "🎥Camera Live"

@magicgui(call_button="📸 Single Shot")
def capture_shot():
    """Take a single image from the camera and display it in a new layer."""
    # Initialize camera if needed
    if not hasattr(capture_shot, 'camera'):
        capture_shot.camera = POACameraController()
    
    try:
        # Connect to camera if not already connected
        if not capture_shot.camera.is_connected:
            if not capture_shot.camera.connect(camera_index=0, width=1024, height=1024):
                show_info("❌ Failed to connect to camera")
                return
            
            capture_shot.camera.set_exposure(50000)  # 50ms initial exposure
            capture_shot.camera.set_gain(300)        # Initial gain
        
        # Start stream temporarily
        if not capture_shot.camera.start_stream():
            show_info("❌ Failed to start camera stream")
            capture_shot.camera.disconnect()
            return
        
        # Wait a bit for the camera to settle
        time.sleep(0.1)
        
        # Try to get a frame for up to 1 second
        start_time = time.time()
        frame = None
        while time.time() - start_time < 1.0:
            frame = capture_shot.camera.get_frame()
            if frame is not None:
                break
            time.sleep(0.05)
        
        # Stop stream
        capture_shot.camera.stop_stream()
        
        if frame is not None:
            # Reshape frame if needed
            if frame.ndim == 3 and frame.shape[2] == 1:
                frame = frame.squeeze()
            
            # Generate unique name for the layer
            timestamp = time.strftime("%H-%M-%S")
            layer_name = f"Camera Shot {timestamp}"
            
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
        if not hasattr(camera_live, 'camera') or not camera_live.camera.is_connected:
            capture_shot.camera.disconnect()

# Create camera control widget with exposure and gain sliders
class CameraControlWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QGridLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        
        # First row: Camera buttons (2 columns)
        layout.addWidget(camera_live.native, 0, 0)
        layout.addWidget(capture_shot.native, 0, 1)
        
        # Second row: Sliders
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
        layout.addWidget(exposure_widget, 1, 0)
        
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
        layout.addWidget(gain_widget, 1, 1)
        
        # Set fixed height for better appearance
        self.setFixedHeight(120)
    
    @pyqtSlot(int)
    def update_exposure(self, value):
        if hasattr(camera_live, 'camera'):
            camera_live.camera.set_exposure(value * 1000)  # Convert ms to µs
        if hasattr(capture_shot, 'camera'):
            capture_shot.camera.set_exposure(value * 1000)  # Convert ms to µs
    
    @pyqtSlot(int)
    def update_gain(self, value):
        if hasattr(camera_live, 'camera'):
            camera_live.camera.set_gain(value)
        if hasattr(capture_shot, 'camera'):
            capture_shot.camera.set_gain(value)

# Add camera control widget to viewer
camera_control = CameraControlWidget()
viewer.window.add_dock_widget(camera_control, name="Camera Control", area="right")

# Add buttons to the interface
# Set fixed sizes for widget buttons
new_scan.native.setFixedSize(150, 50)
save_image.native.setFixedSize(150, 50)
reset_zoom.native.setFixedSize(150, 50)
close_scanner.native.setFixedSize(150, 50)
auto_focus.native.setFixedSize(150, 50)

viewer.window.add_dock_widget(new_scan, area="bottom")
viewer.window.add_dock_widget(save_image, area="bottom")
viewer.window.add_dock_widget(reset_zoom, area="bottom")
viewer.window.add_dock_widget(close_scanner, area="bottom")
viewer.window.add_dock_widget(auto_focus, area="bottom")
viewer.window.add_dock_widget(update_scan_parameters, area="left", name="Scan Parameters")

# Initialize empty auto-focus plot
empty_positions = [0, 1]  # Minimal data to create empty plot
empty_counts = [0, 0]
signal_bridge.update_focus_plot_signal.emit(empty_positions, empty_counts, 'Auto-Focus Plot')

# Calculate the indices corresponding to 0V for both axes
x_zero_idx = np.interp(0, [x_range[0], x_range[1]], [0, x_res-1])
y_zero_idx = np.interp(0, [y_range[0], y_range[1]], [0, y_res-1])
        
# Convert to world coordinates and update point position
world_coords = layer.data_to_world([y_zero_idx, x_zero_idx])
points_layer.data = [[world_coords[0], world_coords[1]]]

# --------------------- SINGLE AXIS SCAN WIDGET ---------------------
class SingleAxisScanWidget(QWidget):
    """Widget for performing single axis scans at current cursor position"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QGridLayout()
        layout.setSpacing(5)
        self.setLayout(layout)
        
        # Create buttons for X and Y scans
        self.x_scan_btn = QPushButton("⬌ X-Axis Scan")
        self.y_scan_btn = QPushButton("⬍ Y-Axis Scan")
        
        # Add widgets to layout
        layout.addWidget(self.x_scan_btn, 0, 0)
        layout.addWidget(self.y_scan_btn, 0, 1)
        
        # Connect buttons
        self.x_scan_btn.clicked.connect(lambda: self.start_scan('x'))
        self.y_scan_btn.clicked.connect(lambda: self.start_scan('y'))
        
        # Create plot widget
        self.plot_widget = SingleAxisPlot()
        layout.addWidget(self.plot_widget, 1, 0, 1, 2)
        
        # Initialize plot with zeros
        x_data = np.linspace(x_range[0], x_range[1], x_res)
        y_data = np.zeros(x_res)
        self.plot_widget.plot_data(
            x_data=x_data,
            y_data=y_data,
            x_label='Position (V)',
            y_label='Counts',
            title='Single Axis Scan',
            mark_peak=False
        )
        
        # Set fixed height for better appearance
        self.setFixedHeight(300)
        
    def get_current_position(self):
        """Get the current scanner position from the points layer"""
        if len(points_layer.data) == 0:
            return None, None
        
        world_coords = points_layer.data[0]
        data_coords = layer.world_to_data(world_coords)
        y_idx, x_idx = data_coords
        
        # Convert from pixel indices to voltage values
        x_voltage = np.interp(x_idx, [0, x_res-1], [x_range[0], x_range[1]])
        y_voltage = np.interp(y_idx, [0, y_res-1], [y_range[0], y_range[1]])
        
        return x_voltage, y_voltage
    
    def start_scan(self, axis):
        """Start a single axis scan"""
        x_pos, y_pos = self.get_current_position()
        if x_pos is None or y_pos is None:
            show_info("❌ No current position set")
            return
        
        # Use resolution and range from config
        if axis == 'x':
            scan_points = np.linspace(x_range[0], x_range[1], x_res)
            fixed_pos = y_pos
            axis_label = 'X Position (V)'
        else:  # y-axis
            scan_points = np.linspace(y_range[0], y_range[1], y_res)
            fixed_pos = x_pos
            axis_label = 'Y Position (V)'
        
        # Perform scan in a separate thread
        def run_scan():
            counts = []
            for point in scan_points:
                if axis == 'x':
                    output_task.write([point, fixed_pos])
                else:
                    output_task.write([fixed_pos, point])
                    
                time.sleep(0.001)  # Small delay for settling
                count = counter.getData()[0][0]/(binwidth/1e12)
                counts.append(count)
            
            # Plot results
            self.plot_widget.plot_data(
                x_data=scan_points,
                y_data=counts,
                x_label=axis_label,
                y_label='Counts',
                title=f'Single Axis Scan ({axis.upper()})',
                mark_peak=True
            )
            
            # Return to original position
            output_task.write([x_pos, y_pos])
        
        threading.Thread(target=run_scan, daemon=True).start()
        show_info(f"🔍 Starting {axis.upper()}-axis scan...")

# Add single axis scan widget to viewer
single_axis_scan = SingleAxisScanWidget()
viewer.window.add_dock_widget(single_axis_scan, name="Single Axis Scan", area="right")

napari.run() # Start the Napari event loop
