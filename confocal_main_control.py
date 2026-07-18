"""
Confocal Single-NV Microscopy Control Software
-------------------------------------------
This software controls a confocal microscope setup for single NV center imaging using:
- Thorlabs LSKGG4 Galvo-Galvo Scanner
- National Instruments USB-6453 DAQ
- Single Photon Detector SPD

The system provides real-time visualization and control through a Napari-based GUI.
"""

# Standard library imports
import threading
import time

# Third-party imports
import numpy as np 
import napari
import nidaqmx
from nidaqmx.constants import TaskMode
from napari.utils.notifications import show_info
from napari._qt.dialogs.qt_notification import NapariQtNotification
NapariQtNotification.DISMISS_AFTER = 1000
from qtpy.QtGui import QGuiApplication
import TimeTagger
from magicgui import magicgui

# Local imports
from galvo_controller import GalvoScannerController
from data_manager import DataManager
from daq_z_controller import DAQZController
from scanning_core import run_hardware_timed_sweep, counts_to_rate
from plot_widgets.live_plot_napari_widget import live_plot
from plot_scan_results import plot_scan_results
from utils import (
    calculate_scale, 
    MAX_ZOOM_LEVEL, 
    BINWIDTH,
    save_tiff_with_imagej_metadata
)
from qtpy.QtWidgets import QWidget
from thread_safe_bridge import GUIBridge

# Import extracted widgets
from widgets.scan_controls import (
    new_scan as create_new_scan,
    close_scanner as create_close_scanner,
    save_image as create_save_image,
    reset_zoom as create_reset_zoom,
    update_scan_parameters as create_update_scan_parameters,
    update_scan_parameters_widget as create_update_scan_parameters_widget,
    stop_scan as create_stop_scan
)
from widgets.camera_controls import (
    create_camera_control_widget
)
from widgets.auto_focus import AutoFocusWidget
from widgets.single_axis_scan import SingleAxisScanWidget
from widgets.file_operations import load_scan as create_load_scan
from widgets.piezo_controls import PiezoControlWidget

# --------------------- SCAN PARAMETERS MANAGER CLASS ---------------------
class ScanParametersManager:
    """Manages scan parameters by getting them from the GUI widget"""
    
    def __init__(self, widget_instance=None):
        self.widget_instance = widget_instance
    
    def set_widget_instance(self, widget_instance):
        """Set the widget instance to get parameters from"""
        self.widget_instance = widget_instance
    
    def get_params(self):
        """Get current scan parameters from the GUI widget"""
        if self.widget_instance and hasattr(self.widget_instance, 'get_parameters'):
            return self.widget_instance.get_parameters()
        else:
            # Fallback default values if widget is not available
            return {
                "scan_range": {"x": [-1.0, 1.0], "y": [-1.0, 1.0]},
                "resolution": {"x": 50, "y": 50},
                "dwell_time": 0.002,
                "z_scan": {"range": [0.0, 450.0], "resolution": 50, "dwell_time": 0.025}
            }
    
    def update_scan_parameters(self, x_range=None, y_range=None, x_res=None, y_res=None, dwell_time=None):
        """Update scan parameters in the GUI widget"""
        if self.widget_instance and hasattr(self.widget_instance, 'update_values'):
            # Get current values first
            current_params = self.get_params()
            
            # Update with new values
            new_x_range = x_range if x_range is not None else current_params['scan_range']['x']
            new_y_range = y_range if y_range is not None else current_params['scan_range']['y']
            new_x_res = x_res if x_res is not None else current_params['resolution']['x']
            new_y_res = y_res if y_res is not None else current_params['resolution']['y']
            new_dwell_time = dwell_time if dwell_time is not None else current_params['dwell_time']
            
            self.widget_instance.update_values(new_x_range, new_y_range, new_x_res, new_y_res, new_dwell_time)

# --------------------- SCAN POINTS MANAGER CLASS ---------------------
class ScanPointsManager:
    """Manages scan point generation and updates"""
    
    def __init__(self, scan_params_manager):
        self.scan_params_manager = scan_params_manager
        self.original_x_points = None
        self.original_y_points = None
        # Initialize with default values
        self._initialize_default_points()
    
    def _initialize_default_points(self):
        """Initialize with default values"""
        # Use same defaults as in the widget
        x_range = [-1.0, 1.0]
        y_range = [-1.0, 1.0]
        x_res = 50
        y_res = 50
        
        self.original_x_points = np.linspace(x_range[0], x_range[1], x_res)
        self.original_y_points = np.linspace(y_range[0], y_range[1], y_res)
    
    def _update_points_from_params(self):
        """Update points from current parameters"""
        params = self.scan_params_manager.get_params()
        x_range = params['scan_range']['x']
        y_range = params['scan_range']['y']
        x_res = params['resolution']['x']
        y_res = params['resolution']['y']
        
        self.original_x_points = np.linspace(x_range[0], x_range[1], x_res)
        self.original_y_points = np.linspace(y_range[0], y_range[1], y_res)
    
    def update_points(self, x_range=None, y_range=None, x_res=None, y_res=None):
        if x_range is not None and x_res is not None:
            self.original_x_points = np.linspace(x_range[0], x_range[1], x_res)
        if y_range is not None and y_res is not None:
            self.original_y_points = np.linspace(y_range[0], y_range[1], y_res)
    
    def get_points(self):
        return self.original_x_points, self.original_y_points

# --------------------- ZOOM LEVEL MANAGER CLASS ---------------------
class ZoomLevelManager:
    """Manages zoom level state"""
    
    def __init__(self, max_zoom=MAX_ZOOM_LEVEL):
        self.zoom_level = 0
        self.max_zoom = max_zoom
    
    def get_zoom_level(self):
        return self.zoom_level
    
    def set_zoom_level(self, level):
        self.zoom_level = level
    
    def can_zoom_in(self):
        return self.zoom_level < self.max_zoom

# --------------------- INITIAL CONFIGURATION ---------------------
# Initialize managers
scan_params_manager = ScanParametersManager()
scan_points_manager = ScanPointsManager(scan_params_manager)
zoom_manager = ZoomLevelManager()

# Initialize hardware controllers
galvo_controller = GalvoScannerController()
data_manager = DataManager()

# Initialize DAQ-based Z (piezo) controller (commands position via Dev1/ao2)
z_controller = DAQZController()
if not z_controller.available:
    show_info("⚠️ Z control via DAQ (ao2) not available")

# Extract scan parameters for initial setup (using defaults)
x_res = 50  # Default resolution
y_res = 50  # Default resolution

# Get initial scanning grids
original_x_points, original_y_points = scan_points_manager.get_points()

# Global state variables
contrast_limits = (0, 10000)
scan_history = []
image = np.zeros((y_res, x_res), dtype=np.float32)
data_path = None
single_axis_widget_ref = None  # Reference to be set later
scan_in_progress = [False]  # Flag to track if scan is running (mutable)
stop_scan_requested = [False]  # Flag to request scan stop (mutable)
scan_task_ref = [None]  # Reference to hardware-timed DAQ scan task (mutable for stop access)
cbm_ref = [None]  # Reference to CountBetweenMarkers measurement (mutable for stop access)

# Initialize DAQ output task for galvo control
output_task = nidaqmx.Task()
output_task.ao_channels.add_ao_voltage_chan(galvo_controller.xin_control)
output_task.ao_channels.add_ao_voltage_chan(galvo_controller.yin_control)
output_task.start()

# --------------------- NAPARI VIEWER SETUP ---------------------
viewer = napari.Viewer(title="NV Scanning Microscopy")
# Set window size to maximum screen size
screen = QGuiApplication.primaryScreen().availableGeometry()
viewer.window.resize(screen.width(), screen.height())

# Thread-safe bridge for GUI updates from background threads
bridge = GUIBridge()
scan_lock = threading.Lock()

# Add an image layer to display the live scan
layer = viewer.add_image(image, name="live scan", colormap="viridis", contrast_limits=contrast_limits)
# Add a shapes layer to display the zoom area
shapes = viewer.add_shapes(name="zoom area", shape_type="rectangle", edge_color='red', face_color='transparent', edge_width=0)

# Configure scale bar (units come from layers in napari >= 0.8)
viewer.scale_bar.visible = True
viewer.scale_bar.position = "bottom_left"

# Calculate scale (in microns/pixel) using defaults initially
x_range = [-1.0, 1.0]  # Default range
y_range = [-1.0, 1.0]  # Default range
scale_um_per_px_x = calculate_scale(x_range[0], x_range[1], x_res)
scale_um_per_px_y = calculate_scale(y_range[0], y_range[1], y_res)
layer.scale = (scale_um_per_px_y, scale_um_per_px_x)
layer.units = ('µm', 'µm')
shapes.units = ('µm', 'µm')

# --------------------- TIMETAGGER SETUP ---------------------
try:
    tagger = TimeTagger.createTimeTagger()
    tagger.reset()
    show_info("✅ Connected to real TimeTagger device")
    tagger.startServer(access_mode = TimeTagger.AccessMode.Control,port=41101) 
    # Start the Server. TimeTagger.AccessMode sets the access rights for clients. Port defines the network port to be used
    # The server keeps running until the command tagger.stopServer() is called or until the program is terminated
    show_info("✅ TimeTagger server started")
except Exception as e:
    show_info("⚠️ Real TimeTagger not detected, using virtual device")
    tagger = TimeTagger.createTimeTaggerVirtual("TimeTagger/time_tags_test.ttbin")
    tagger.run()
    show_info("✅ Virtual TimeTagger started")

# Free-running counter used ONLY by the live signal plot. All DAQ-driven
# acquisitions (2D raster, auto-focus, single-axis) instead count with
# CountBetweenMarkers clocked by the DAQ (see scanning_core.py).
binwidth = BINWIDTH
n_values = 1
counter = TimeTagger.Counter(tagger, [1], binwidth, n_values)

# --------------------- CLICK HANDLER FOR SCANNER POSITIONING ---------------------
def on_mouse_click(layer, event):
    """Handle mouse click events to move the galvo scanner to the clicked position."""
    coords = layer.world_to_data(event.position)
    x_idx, y_idx = int(round(coords[1])), int(round(coords[0]))
    
    # Get current ranges from scan parameters manager
    params = scan_params_manager.get_params()
    x_range = params['scan_range']['x']
    y_range = params['scan_range']['y']
    x_res = params['resolution']['x']
    y_res = params['resolution']['y']
    
    # Convert from pixel coordinates to voltage values
    x_voltage = np.interp(x_idx, [0, x_res-1], [x_range[0], x_range[1]])
    y_voltage = np.interp(y_idx, [0, y_res-1], [y_range[0], y_range[1]])
    
    try:
        output_task.write([x_voltage, y_voltage])
        show_info(f"Moved scanner to: X={x_voltage:.3f}V, Y={y_voltage:.3f}V")
        
        # Update the single axis scan widget's position tracking
        if single_axis_widget_ref is not None:
            single_axis_widget_ref.update_current_position(x_voltage, y_voltage)
        
    except Exception as e:
        show_info(f"Error moving scanner: {str(e)}")

layer.mouse_drag_callbacks.append(on_mouse_click)

# --------------------- LIVE SIGNAL PLOT WIDGET (pyqtgraph) ---------------------
# Function to get count rate and check for overflow
def get_count_with_overflow():
    data = counter.getData()
    count_rate = data[0][0]/(binwidth/1e12)
    # Check if any bins are in overflow mode
    counter_data = counter.getDataObject()
    overflow = counter_data.overflow  # Access as attribute, not as a method
    return count_rate, overflow

def set_live_binwidth(binwidth_ps):
    """Rebuild the live-signal counter with a new integration window (ps)."""
    global binwidth, counter
    binwidth = int(binwidth_ps)
    counter = TimeTagger.Counter(tagger, [1], binwidth, n_values)

# Add a live plot widget to display count rate with overflow detection
signal_plot_widget = live_plot(
    measure_function=get_count_with_overflow, histogram_range=100, dt=0.2,
    binwidth_ps=binwidth, binwidth_callback=set_live_binwidth
)
viewer.window.add_dock_widget(signal_plot_widget, area='right', name='Signal Plot')

def update_contrast_limits(layer, image):
    """Helper function to update contrast limits for an image layer."""
    try:
        if image.size == 0 or np.all(np.isnan(image)):
            show_info('⚠️ Image is empty or contains only NaNs. Contrast not updated.')
            return
        
        min_val = np.nanmin(image)
        max_val = np.nanmax(image)
        if np.isclose(min_val, max_val):
            show_info('⚠️ Image min and max are equal. Contrast not updated.')
            return
            
        layer.contrast_limits = (min_val, max_val)
    except Exception as e:
        show_info(f'❌ Error setting contrast limits: {str(e)}')

# --------------------- WAVEFORM GENERATION ---------------------
GALVO_FLYBACK_TIME = 0.002  # seconds of retrace budget between rows

def generate_scan_waveform(x_points, y_points, n_flyback=0):
    """Pre-compute complete X/Y voltage waveforms for a hardware-timed raster scan.

    Inserts a smooth linear ramp of *n_flyback* samples between consecutive
    rows so the galvo can decelerate, retrace, and settle before the next
    line of data acquisition begins.  Flyback samples are clocked at the
    same rate as imaging samples; their photon counts must be discarded by
    the caller.

    Args:
        x_points: 1D array of X galvo voltages (one per column).
        y_points: 1D array of Y galvo voltages (one per row).
        n_flyback: Number of extra retrace samples inserted between rows.
                   Set to 0 to disable (original behaviour).

    Returns:
        x_waveform: 1D voltage array for AO0.
        y_waveform: 1D voltage array for AO1.
    """
    width = len(x_points)
    height = len(y_points)

    if n_flyback <= 0:
        return np.tile(x_points, height), np.repeat(y_points, width)

    segments_x = []
    segments_y = []

    for i in range(height):
        segments_x.append(x_points)
        segments_y.append(np.full(width, y_points[i]))

        if i < height - 1:
            segments_x.append(np.linspace(x_points[-1], x_points[0], n_flyback))
            segments_y.append(np.linspace(y_points[i], y_points[i + 1], n_flyback))

    return np.concatenate(segments_x), np.concatenate(segments_y)

# --------------------- HARDWARE-TIMED SCANNING FUNCTION ---------------------
def scan_pattern(x_points, y_points):
    """Perform a hardware-timed raster scan using buffered AO and CountBetweenMarkers.

    The full scan waveform is pre-computed, loaded into the DAQ, and clocked
    out by the hardware sample clock.  The same clock is exported to a PFI
    terminal and wired to the Time Tagger, where CountBetweenMarkers counts
    APD photons between successive clock edges for each pixel.
    """
    global image, layer, data_path

    with scan_lock:
        if scan_in_progress[0]:
            bridge.notify("⚠️ A scan is already in progress")
            return None, None
        scan_in_progress[0] = True
        stop_scan_requested[0] = False

    current_scan_params = scan_params_manager.get_params()
    dwell_time = current_scan_params['dwell_time']

    height, width = len(y_points), len(x_points)

    try:
        output_task.write([x_points[0], y_points[0]])
        n_flyback = max(1, int(np.ceil(GALVO_FLYBACK_TIME / dwell_time)))
        x_waveform, y_waveform = generate_scan_waveform(x_points, y_points, n_flyback=n_flyback)
        stride = width + n_flyback
        pixel_rate = 1.0 / dwell_time

        image = np.zeros((height, width), dtype=np.float32)
        scale_um_per_px_x = calculate_scale(x_points[0], x_points[-1], width)
        scale_um_per_px_y = calculate_scale(y_points[0], y_points[-1], height)

        def _setup_layer():
            layer.data = image
            layer.contrast_limits = contrast_limits
            layer.scale = (scale_um_per_px_y, scale_um_per_px_x)
        bridge.run_on_main(_setup_layer)

        # Release AO channels from the persistent on-demand task
        output_task.stop()
        output_task.control(TaskMode.TASK_UNRESERVE)

        start_time = time.time()

        def _refresh_and_update():
            layer.refresh()
            update_contrast_limits(layer, image)

        # Update the live display incrementally as full rows complete.
        progress_state = {'last_completed_row': -1}

        def _on_progress(partial_data, partial_bins):
            rows_updated = False
            for row_idx in range(progress_state['last_completed_row'] + 1, height):
                row_start = row_idx * stride
                row_end = row_start + width
                row_bins = partial_bins[row_start:row_end]
                if len(row_bins) == width and np.all(row_bins > 0):
                    image[row_idx, :] = counts_to_rate(
                        partial_data[row_start:row_end], row_bins
                    )
                    progress_state['last_completed_row'] = row_idx
                    rows_updated = True
                else:
                    break
            if rows_updated:
                bridge.run_on_main(_refresh_and_update)

        # Hardware-timed raster: clock out the waveform on ao0/ao1 while the
        # Time Tagger counts photons between clock edges (one value per sample).
        all_counts, bin_widths = run_hardware_timed_sweep(
            tagger,
            [galvo_controller.xin_control, galvo_controller.yin_control],
            np.array([x_waveform, y_waveform]),
            pixel_rate,
            stop_check=lambda: stop_scan_requested[0],
            on_progress=_on_progress,
            task_ref=scan_task_ref,
            cbm_ref=cbm_ref,
            lock=scan_lock,
        )

        if stop_scan_requested[0]:
            bridge.notify("🛑 Scan stopped by user")
            return None, None

        # Extract final image from completed measurement
        print(f"All counts: {all_counts}")
        print(f"Bin widths: {bin_widths}")

        for row_idx in range(height):
            row_start = row_idx * stride
            row_end = row_start + width
            image[row_idx, :] = counts_to_rate(
                all_counts[row_start:row_end], bin_widths[row_start:row_end]
            )

        def _final_layer_update():
            layer.data = image
            update_contrast_limits(layer, image)
        bridge.run_on_main(_final_layer_update)

        end_time = time.time()
        print(f"Scan time: {end_time - start_time:.2f} seconds, {width}x{height} pixels, "
              f"{n_flyback} flyback samples/row (hardware-timed)")

        current_scan_params['scan_range']['x'] = [float(x_points[0]), float(x_points[-1])]
        current_scan_params['scan_range']['y'] = [float(y_points[0]), float(y_points[-1])]

        save_image = image.copy()
        save_x = x_points.copy()
        save_y = y_points.copy()
        save_params = {
            'scan_range': dict(current_scan_params['scan_range']),
            'resolution': dict(current_scan_params['resolution']),
            'dwell_time': current_scan_params['dwell_time']
        }
        save_scale_x = scale_um_per_px_x
        save_scale_y = scale_um_per_px_y

        def _save_all():
            scan_data = {
                'image': save_image,
                'x_points': save_x,
                'y_points': save_y,
                'scale_x': save_scale_x,
                'scale_y': save_scale_y
            }
            global data_path
            data_path = data_manager.save_scan_data(scan_data, save_params)
            plot_scan_results(scan_data, data_path)

            timestamp_str = time.strftime("%Y%m%d-%H%M%S")
            np.savez(data_path.replace('.csv', '.npz'),
                     image=save_image,
                     scale_x=save_scale_x,
                     scale_y=save_scale_y,
                     x_range=save_params['scan_range']['x'],
                     y_range=save_params['scan_range']['y'],
                     x_resolution=save_params['resolution']['x'],
                     y_resolution=save_params['resolution']['y'],
                     dwell_time=save_params['dwell_time'],
                     x_points=save_x,
                     y_points=save_y,
                     timestamp=timestamp_str)

            save_tiff_with_imagej_metadata(
                image_data=save_image,
                filepath=data_path.replace('.csv', '.tiff'),
                x_points=save_x,
                y_points=save_y,
                scan_config=save_params,
                timestamp=timestamp_str
            )
            bridge.notify("💾 Scan data saved")

        threading.Thread(target=_save_all, daemon=True).start()

    finally:
        # The AO task and CBM lifecycle are owned by run_hardware_timed_sweep;
        # here we only restore the persistent on-demand galvo task.
        try:
            output_task.start()
            output_task.write([0, 0])
        except Exception as e:
            bridge.notify(f"⚠️ Failed to restart galvo control: {e}")

        bridge.notify("🎯 Scanner returned to zero position")
        with scan_lock:
            scan_in_progress[0] = False

    return x_points, y_points

# --------------------- DATA PATH FUNCTION ---------------------
def get_data_path():
    """Helper function to get current data path"""
    return data_path

# --------------------- CREATE WIDGETS USING FACTORIES ---------------------

# Create scan control widgets
new_scan_widget = create_new_scan(scan_pattern, scan_points_manager, shapes, bridge, scan_in_progress)
close_scanner_widget = create_close_scanner(output_task)
save_image_widget = create_save_image(viewer, get_data_path)
update_scan_parameters_widget = create_update_scan_parameters(scan_params_manager)
update_widget_func = create_update_scan_parameters_widget(update_scan_parameters_widget, scan_params_manager, bridge)

# Update scan points manager with initial parameters from the widget
scan_points_manager._update_points_from_params()

# Create stop scan widget
stop_scan_widget = create_stop_scan(scan_in_progress, stop_scan_requested, scan_task_ref, cbm_ref, scan_lock)
stop_scan_widget.native.setFixedSize(150, 50)

reset_zoom_widget = create_reset_zoom(
    scan_pattern, scan_history, scan_params_manager, scan_points_manager,
    shapes, lambda **kwargs: scan_params_manager.update_scan_parameters(**kwargs), 
    update_widget_func,
    zoom_manager,
    bridge,
    scan_in_progress
)

# Create camera control widgets
camera_control_widget = create_camera_control_widget(viewer)

# Create Scan Z widget (button + pyqtgraph plot; Z params from Scan Parameters)
auto_focus_widget = AutoFocusWidget(
    tagger, z_controller, scan_params_manager,
    scan_lock, scan_in_progress, stop_scan_requested, scan_task_ref, cbm_ref
)

# Create single axis scan widget
single_axis_scan_widget = SingleAxisScanWidget(
    scan_params_manager, layer, output_task, tagger, galvo_controller,
    scan_lock, scan_in_progress, stop_scan_requested, scan_task_ref, cbm_ref
)

# Set the global reference for position tracking
single_axis_widget_ref = single_axis_scan_widget

# Embed the Scan Z (auto-focus) panel as a third tab of the single-axis widget
single_axis_scan_widget.add_z_tab(auto_focus_widget, title="Z Axis")

# Create file operation widgets
load_scan_widget = create_load_scan(
    viewer,
    scan_params_manager=scan_params_manager,
    scan_points_manager=scan_points_manager,
    update_widget_func=update_widget_func
)

# Create piezo control widget
piezo_control_widget = PiezoControlWidget(z_controller)

# Let Scan Z refresh the Z control widget after a completed sweep
auto_focus_widget.z_control_widget = piezo_control_widget


# --------------------- ZOOM BY REGION HANDLER ---------------------
zoom_in_progress = False

@shapes.events.data.connect
def on_shape_added(event):
    """Handle zoom region selection in the GUI."""
    global zoom_in_progress

    if zoom_in_progress:
        return

    if not zoom_manager.can_zoom_in():
        show_info(f"⚠️ Max zoom reached ({zoom_manager.max_zoom} levels).")
        return

    if scan_in_progress[0]:
        show_info("⚠️ A scan is already in progress")
        return

    if len(shapes.data) == 0:
        return

    # Calculate new scan region from selected rectangle
    rect1 = shapes.data[-1]
    rect = np.array([layer.world_to_data(point) for point in rect1])
    min_y, min_x = np.floor(np.min(rect, axis=0)).astype(int)
    max_y, max_x = np.ceil(np.max(rect, axis=0)).astype(int)
    
    # Ensure zoom region stays within image bounds
    height, width = layer.data.shape
    min_x = max(0, min_x)
    max_x = min(width - 1, max_x)  # Ensure we don't exceed array bounds
    min_y = max(0, min_y)
    max_y = min(height - 1, max_y)  # Ensure we don't exceed array bounds

    # Save current state for zoom history
    current_x_points, current_y_points = scan_points_manager.get_points()
    scan_history.append((current_x_points, current_y_points))

    # Calculate new scan points maintaining original resolution
    current_params = scan_params_manager.get_params()
    current_x_res = current_params['resolution']['x']
    current_y_res = current_params['resolution']['y']
    # Create new scan points covering the full selected region
    # min_x/max_x are pixel indices, we convert them to voltage values
    x_zoom = np.linspace(current_x_points[min_x], current_x_points[max_x], current_x_res)
    y_zoom = np.linspace(current_y_points[min_y], current_y_points[max_y], current_y_res)

    def run_zoom():
        global zoom_in_progress
        zoom_in_progress = True

        x_range_new = [x_zoom[0], x_zoom[-1]]
        y_range_new = [y_zoom[0], y_zoom[-1]]
        bridge.run_on_main(lambda: scan_params_manager.update_scan_parameters(
            x_range=x_range_new, y_range=y_range_new,
            x_res=current_x_res, y_res=current_y_res
        ))
        scan_points_manager.update_points(
            x_range=x_range_new, y_range=y_range_new,
            x_res=current_x_res, y_res=current_y_res
        )

        bridge.run_on_main(lambda: setattr(shapes, 'data', []))
        scan_pattern(x_zoom, y_zoom)
        zoom_manager.set_zoom_level(zoom_manager.get_zoom_level() + 1)
        update_widget_func()
        zoom_in_progress = False

    threading.Thread(target=run_zoom, daemon=True).start()

# --------------------- ADD WIDGETS TO VIEWER ---------------------

# Set fixed sizes for widget buttons
new_scan_widget.native.setFixedSize(150, 50)
save_image_widget.native.setFixedSize(150, 50)
reset_zoom_widget.native.setFixedSize(150, 50)
close_scanner_widget.native.setFixedSize(150, 50)
load_scan_widget.native.setFixedSize(150, 50)

# Add widgets to viewer
viewer.window.add_dock_widget(new_scan_widget, area="bottom")
viewer.window.add_dock_widget(stop_scan_widget, area="bottom")
viewer.window.add_dock_widget(save_image_widget, area="bottom")
viewer.window.add_dock_widget(reset_zoom_widget, area="bottom")
viewer.window.add_dock_widget(close_scanner_widget, area="bottom")
viewer.window.add_dock_widget(load_scan_widget, area="bottom")
viewer.window.add_dock_widget(piezo_control_widget, area="bottom")
update_scan_parameters_dock = viewer.window.add_dock_widget(update_scan_parameters_widget, area="left", name="Scan Parameters")
camera_control_dock = viewer.window.add_dock_widget(camera_control_widget, name="Camera Control", area="right")
viewer.window.add_dock_widget(single_axis_scan_widget, name="Single Axis Scan", area="right")
viewer.window._qt_window.tabifyDockWidget(update_scan_parameters_dock, camera_control_dock)

# --------------------- CLEANUP ON CLOSE ---------------------
def _on_close():
    """Clean up hardware resources when closing the app"""
    try:
        # Set scanner to zero position before closing
        output_task.write([0, 0])
        show_info("🎯 Scanner set to zero position")

        # Park the piezo at Z = 0 before releasing the controller
        if z_controller and z_controller.available:
            z_controller.set_position(0.0)
            show_info("🎯 Z set to zero position")
        if z_controller:
            z_controller.close()
            show_info("✓ Z controller released")
    except Exception as e:
        show_info(f"❌ Error during app closure: {str(e)}")

# Register cleanup using Qt's destroyed signal
viewer.window._qt_window.destroyed.connect(_on_close)

def main():
    """Main application entry point"""
    napari.run()  # Start the Napari event loop

if __name__ == "__main__":
    main() 