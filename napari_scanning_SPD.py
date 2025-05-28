"""
Confocal Single-NV Microscopy Control Software
-------------------------------------------
This software controls a confocal microscope setup for single NV center imaging using:
- Thorlabs LSKGG4 Galvo-Galvo Scanner
- National Instruments USB-6453 DAQ
- Single Photon Detector SPD

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
from TimeTagger import createTimeTagger, Countrate, Counter, createTimeTaggerVirtual  # Swabian TimeTagger API
from plot_scan_results import plot_scan_results
import clr
import sys
from System import Decimal
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt5.QtCore import QObject, pyqtSignal, QThread

# Add Thorlabs.Kinesis references
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.DeviceManagerCLI.dll")
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.GenericPiezoCLI.dll")
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\ThorLabs.MotionControl.Benchtop.PrecisionPiezoCLI.dll")
from Thorlabs.MotionControl.DeviceManagerCLI import *
from Thorlabs.MotionControl.GenericPiezoCLI import *
from Thorlabs.MotionControl.GenericPiezoCLI import Piezo
from Thorlabs.MotionControl.Benchtop.PrecisionPiezoCLI import *

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
tagger = createTimeTaggerVirtual("TimeTagger/time_tags.ttbin")
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
    except Exception as e:
        show_info(f"Error moving scanner: {str(e)}")

# Connect the mouse click handler to the image layer
layer.mouse_drag_callbacks.append(on_mouse_click)

# --------------------- MPL WIDGET (SIGNAL LIVE PLOT) ---------------------

# Create and add the MPL widget to the viewer for live signal monitoring.
# 'measure_function' is a lambda function that returns the current APD signal value (voltage).
# 'histogram_range' is the number of data points to plot before overwriting.
# 'dt' is the time between data points in seconds (converted to milliseconds internally).
mpl_widget = live_plot(measure_function=lambda: counter.getData(), histogram_range=100, dt=0.2)
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
            time.sleep(binwidth/1e12) # Wait for SPD to count
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
    create_focus_plot_signal = pyqtSignal(list, list, str)
    
    def __init__(self):
        super().__init__()
        self.create_focus_plot_signal.connect(self._create_and_add_focus_plot)
        self.current_focus_widget = None
    
    def _create_and_add_focus_plot(self, positions, counts, name):
        """Create and add the focus plot widget from the main thread"""
        # Remove previous focus plot widget if it exists
        if self.current_focus_widget is not None:
            viewer.window.remove_dock_widget(self.current_focus_widget)
        
        # Create new focus plot widget
        focus_plot_widget = create_focus_plot_widget(positions, counts)
        
        # Add the widget to the viewer
        self.current_focus_widget = viewer.window.add_dock_widget(
            focus_plot_widget, 
            area='right', 
            name=name
        )

# Create a global signal bridge
signal_bridge = SignalBridge()

@magicgui(call_button="🔍 Auto Focus", test_mode={"widget_type": "CheckBox", "text": "Test Mode"})
def auto_focus(test_mode=False):
    """Automatically find the optimal Z position by scanning for maximum signal"""
    def run_auto_focus():
        try:
            if test_mode:
                # Mock implementation for testing
                show_info('🔍 Starting Z scan in TEST MODE...')
                
                # Create simulated data
                max_pos = 100.0
                step_size = 5.0
                positions = np.arange(0, max_pos + step_size, step_size)
                
                # Simulate a Gaussian distribution of counts centered at a random position
                center = np.random.uniform(30, 70)  # Random center between 30-70
                width = 15.0  # Width of the Gaussian
                noise_level = 200  # Base noise level
                peak_height = 1000  # Peak signal above noise
                
                # Generate simulated counts with noise
                counts = noise_level + peak_height * np.exp(-((positions - center) ** 2) / (2 * width ** 2))
                counts = counts + np.random.normal(0, noise_level * 0.1, len(positions))  # Add random noise
                counts = counts.astype(int)  # Convert to integers like real counts
                
                # Simulate the scanning process
                for i, pos in enumerate(positions):
                    time.sleep(0.05)  # Simulate shorter delay for testing
                    print(f'Position: {pos}, counts: {counts[i]}')
                
                # Find position with maximum counts
                optimal_pos = positions[np.argmax(counts)]
                
                show_info(f'✅ Focus optimized at Z = {optimal_pos} µm (TEST MODE)')
                
                # Use signal to create and add widget from main thread
                signal_bridge.create_focus_plot_signal.emit(positions.tolist(), counts.tolist(), 'Auto-Focus Plot (TEST)')
                
            else:
                # Real implementation with actual hardware
                # Initialize piezo controller
                DeviceManagerCLI.BuildDeviceList()
                serial_no = "44506104"  # Your piezo serial number
                
                # Connect to device
                device = BenchtopPrecisionPiezo.CreateBenchtopPiezo(serial_no)
                device.Connect(serial_no)
                channel = device.GetChannel(1)
                
                # Initialize device
                if not channel.IsSettingsInitialized():
                    channel.WaitForSettingsInitialized(10000)
                    assert channel.IsSettingsInitialized() is True
                
                channel.StartPolling(250)
                time.sleep(0.25)
                channel.EnableDevice()
                time.sleep(0.25)
                
                # Set to closed loop mode
                channel.SetPositionControlMode(Piezo.PiezoControlModeTypes.CloseLoop)
                time.sleep(0.25)
                
                # Get max travel range
                max_pos = channel.GetMaxTravel()
                print(f"{max_pos}")
                # Parameters for Z sweep
                step_size = Decimal(10)  # 0.1 µm steps
                positions = []
                counts = []
                current = Decimal(0)
                
                while current <= max_pos:
                    positions.append(current)
                    current += step_size
                
                show_info('🔍 Starting Z scan...')
                # Perform Z sweep
                for pos in positions:
                    channel.SetPosition(pos)
                    time.sleep(0.1)  # Wait for movement and settling
                    counts.append(counter.getData())
                    print(f'Position: {pos}, counts: {counts[-1]}')
                
                # Find position with maximum counts
                optimal_pos = positions[np.argmax(counts)]

                # Move to optimal position
                channel.SetPosition(optimal_pos)
                time.sleep(0.1)
                
                show_info(f'✅ Focus optimized at Z = {optimal_pos} µm')
                
                # Convert Decimal to float for plotting
                positions_float = [float(pos) for pos in positions]
                
                # Use signal to create and add widget from main thread
                signal_bridge.create_focus_plot_signal.emit(positions_float, counts, 'Auto-Focus Plot')
                
                # Clean up
                channel.StopPolling()
                channel.Disconnect()
                
        except Exception as e:
            show_info(f'❌ Auto-focus error: {str(e)}')
    
    threading.Thread(target=run_auto_focus, daemon=True).start()

# --------------------- AUTO-FOCUS PLOT WIDGET ---------------------
def create_focus_plot_widget(positions, counts):
    """
    Creates a static plot widget to display auto-focus results
    
    Parameters
    ----------
    positions : list
        Z positions scanned during auto-focus
    counts : list
        Photon counts measured at each position
    
    Returns
    -------
    QWidget
        A Qt widget containing the matplotlib plot
    """
    # Create a widget to hold the plot
    widget = QWidget()
    layout = QVBoxLayout()
    widget.setFixedHeight(300)
    widget.setLayout(layout)
    
    # Create the figure and canvas
    fig = Figure(figsize=(4, 2), facecolor='#262930')
    canvas = FigureCanvas(fig)
    ax = fig.add_subplot(111)
    
    # Style the plot to match napari's dark theme
    ax.set_facecolor('#262930')
    ax.tick_params(colors='white')
    for spine in ax.spines.values():
        spine.set_color('white')
    
    # Plot the data
    ax.plot(positions, counts, 'o-', color='#00ff00')
    
    # Mark the optimal position
    optimal_idx = np.argmax(counts)
    optimal_pos = positions[optimal_idx]
    optimal_counts = counts[optimal_idx]
    ax.plot(optimal_pos, optimal_counts, 'ro', markersize=8)
    ax.annotate(f'Optimal: {optimal_pos} µm', 
                xy=(optimal_pos, optimal_counts),
                xytext=(10, -20),
                textcoords='offset points',
                color='white',
                arrowprops=dict(arrowstyle='->', color='white'))
    
    # Set labels and grid
    ax.set_xlabel('Z Position (µm)', color='white')
    ax.set_ylabel('Counts', color='white')
    ax.set_title('Auto-Focus Results', color='white')
    ax.grid(True, color='gray', alpha=0.3)
    
    # Add the canvas to the layout
    layout.addWidget(canvas)
    
    # Draw the canvas
    fig.tight_layout()
    canvas.draw()
    
    return widget

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

# Add buttons to the interface
viewer.window.add_dock_widget(new_scan, area="bottom")
viewer.window.add_dock_widget(save_image, area="bottom")
viewer.window.add_dock_widget(reset_zoom, area="bottom")
viewer.window.add_dock_widget(close_scanner, area="bottom")
viewer.window.add_dock_widget(auto_focus, area="bottom")
viewer.window.add_dock_widget(update_scan_parameters, area="right", name="Scan Parameters")

napari.run() # Start the Napari event loop
