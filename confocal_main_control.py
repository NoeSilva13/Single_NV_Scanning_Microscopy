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
from daq_axis import DAQAxis
import raster_engine
from plot_widgets.live_plot_napari_widget import live_plot
from plot_scan_results import plot_scan_results
from utils import (
    um_scale,
    MAX_ZOOM_LEVEL, 
    BINWIDTH,
    MICRONS_PER_VOLT,
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
            # Fallback default values if widget is not available (µm canonical).
            return {
                "scan_range": {"x": [-MICRONS_PER_VOLT, MICRONS_PER_VOLT],
                               "y": [-MICRONS_PER_VOLT, MICRONS_PER_VOLT]},
                "resolution": {"x": 50, "y": 50},
                "dwell_time": 0.002,
                "z_scan": {"range": [0.0, 450.0], "resolution": 50, "dwell_time": 0.025},
                "scan_mode": "XY"
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
        """Initialize with default values (µm canonical)."""
        # Use same defaults as in the widget
        x_range = [-MICRONS_PER_VOLT, MICRONS_PER_VOLT]
        y_range = [-MICRONS_PER_VOLT, MICRONS_PER_VOLT]
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

# Axis abstraction (µm <-> V) for every DAQ analog-output axis. Galvo X/Y are
# not validated here because GalvoScannerController already reserves ao0/ao1;
# the piezo axis is the z_controller itself (a DAQAxis subclass).
_GALVO_TRAVEL_UM = (-10.0 * MICRONS_PER_VOLT, 10.0 * MICRONS_PER_VOLT)
axis_x = DAQAxis("x", galvo_controller.xin_control, MICRONS_PER_VOLT,
                 (-10.0, 10.0), _GALVO_TRAVEL_UM, validate=False)
axis_y = DAQAxis("y", galvo_controller.yin_control, MICRONS_PER_VOLT,
                 (-10.0, 10.0), _GALVO_TRAVEL_UM, validate=False)
axis_z = z_controller
AXES = {"x": axis_x, "y": axis_y, "z": axis_z}

# Last commanded position of each axis, in micrometers. Used to hold axes that
# are not part of a given scan mode at their current location.
current_position_um = {"x": 0.0, "y": 0.0, "z": 0.0}

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


def run_on_main_sync(func, timeout=15.0):
    """Run *func* on the main GUI thread and block until it returns a value.

    Used when a background scan thread must create/fetch a napari layer and
    needs the resulting reference before continuing.
    """
    result = {}
    done = threading.Event()

    def _wrapper():
        try:
            result['value'] = func()
        except Exception as e:
            result['error'] = e
        finally:
            done.set()

    bridge.run_on_main(_wrapper)
    done.wait(timeout)
    if 'error' in result:
        raise result['error']
    return result.get('value')

# Add an image layer to display the live XY scan
layer = viewer.add_image(image, name="XY scan", colormap="viridis", contrast_limits=contrast_limits)
# Add a shapes layer to display the zoom area
shapes = viewer.add_shapes(name="zoom area", shape_type="rectangle", edge_color='red', face_color='transparent', edge_width=0)

# Configure scale bar (units come from layers in napari >= 0.8)
viewer.scale_bar.visible = True
viewer.scale_bar.position = "bottom_left"

# Calculate scale (in microns/pixel) using defaults initially (µm canonical)
x_range = [-MICRONS_PER_VOLT, MICRONS_PER_VOLT]  # Default range in µm
y_range = [-MICRONS_PER_VOLT, MICRONS_PER_VOLT]  # Default range in µm
scale_um_per_px_x = um_scale(x_range[0], x_range[1], x_res)
scale_um_per_px_y = um_scale(y_range[0], y_range[1], y_res)
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
    
    # Get current ranges from scan parameters manager (µm canonical)
    params = scan_params_manager.get_params()
    x_range = params['scan_range']['x']
    y_range = params['scan_range']['y']
    x_res = params['resolution']['x']
    y_res = params['resolution']['y']
    
    # Convert from pixel coordinates to positions in micrometers
    x_um = float(np.interp(x_idx, [0, x_res-1], [x_range[0], x_range[1]]))
    y_um = float(np.interp(y_idx, [0, y_res-1], [y_range[0], y_range[1]]))

    try:
        # Convert µm -> volts at the DAQ boundary via the axis calibration
        output_task.write([axis_x.position_to_voltage(x_um),
                           axis_y.position_to_voltage(y_um)])
        current_position_um['x'] = x_um
        current_position_um['y'] = y_um
        show_info(f"Moved scanner to: X={x_um:.3f} µm, Y={y_um:.3f} µm")
        
        # Update the single axis scan widget's position tracking (µm)
        if single_axis_widget_ref is not None:
            single_axis_widget_ref.update_current_position(x_um, y_um)
        
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

# --------------------- SCAN GEOMETRY / MODES ---------------------
GALVO_FLYBACK_TIME = 0.002  # seconds of retrace budget between fast lines

# Fast..slow axis order for each scan mode. Z (piezo) is always the slowest
# stepping axis, so it steps at most once per fast line and gets a flyback
# window sized by the configurable Z dwell (not a hardcoded value).
MODE_AXES = {
    'XY': ['x', 'y'],
    'XZ': ['x', 'z'],
    'YZ': ['y', 'z'],
    'XYZ': ['x', 'y', 'z'],
}

_MODE_LAYER_NAMES = {'XZ': 'XZ scan', 'YZ': 'YZ scan', 'XYZ': 'XYZ volume'}


def _flyback_samples(dwell, z_dwell, scanned):
    """Retrace/settle samples between fast lines.

    Galvo retrace budget (``GALVO_FLYBACK_TIME``) always applies. When the piezo
    Z is a stepping axis, the window is widened so the retrace duration covers
    the user-configured Z settling time (``z_dwell``).
    """
    n = max(1, int(np.ceil(GALVO_FLYBACK_TIME / dwell)))
    if 'z' in scanned:
        n = max(n, int(np.ceil(z_dwell / dwell)))
    return n


def _prepare_scan_layer(mode, data, scales, units):
    """Create or update the napari layer for *mode* on the main thread."""
    if mode == 'XY':
        def _p():
            layer.data = data
            layer.contrast_limits = contrast_limits
            layer.scale = scales
            layer.units = units
            return layer
        return run_on_main_sync(_p)

    name = _MODE_LAYER_NAMES.get(mode, f'{mode} scan')

    def _p():
        if name in viewer.layers:
            lyr = viewer.layers[name]
            lyr.data = data
            lyr.scale = scales
            lyr.units = units
        else:
            lyr = viewer.add_image(
                data, name=name, colormap='viridis', scale=scales, units=units
            )
        return lyr
    return run_on_main_sync(_p)


def _save_scan(mode, axis_names, points_list, result, scales, dwell, z_dwell, scan_time):
    """Persist a completed scan (npz for all modes; CSV/TIFF/plot for 2D)."""
    global data_path
    timestamp_str = time.strftime("%Y%m%d-%H%M%S")

    # Per-axis metadata (µm canonical).
    npz_kwargs = dict(
        image=result,
        scan_mode=mode,
        axis_names=np.array(axis_names),
        dwell_time=float(dwell),
        z_dwell_time=float(z_dwell),
        microns_per_volt=MICRONS_PER_VOLT,
        z_um_per_volt=z_controller.um_per_volt,
        units='um',
        format_version=2,
        timestamp=timestamp_str,
    )
    for name, pts in zip(axis_names, points_list):
        npz_kwargs[f'{name}_points'] = pts
        npz_kwargs[f'{name}_range'] = [float(pts[0]), float(pts[-1])]
        npz_kwargs[f'{name}_resolution'] = len(pts)
        npz_kwargs[f'{name}_scale'] = um_scale(pts[0], pts[-1], len(pts))

    if result.ndim == 3:
        # (Z, Y, X): store scales in napari order for the loader.
        npz_kwargs['scale_z'] = scales[0]
        npz_kwargs['scale_y'] = scales[1]
        npz_kwargs['scale_x'] = scales[2]
        path = data_manager.next_base_path('.npz')
        np.savez(path, **npz_kwargs)
        data_path = path
        bridge.notify("💾 3D scan data saved")
        return

    # 2D modes: keep the legacy CSV/TIFF/plot pipeline. Fast axis -> columns
    # (x_points), slow axis -> rows (y_points).
    fast_pts = points_list[0]
    slow_pts = points_list[1]
    scale_fast = scales[1]
    scale_slow = scales[0]
    npz_kwargs['scale_x'] = scale_fast
    npz_kwargs['scale_y'] = scale_slow

    scan_data = {
        'image': result,
        'x_points': fast_pts,
        'y_points': slow_pts,
        'scale_x': scale_fast,
        'scale_y': scale_slow,
    }
    save_params = {
        'scan_range': {
            'x': [float(fast_pts[0]), float(fast_pts[-1])],
            'y': [float(slow_pts[0]), float(slow_pts[-1])],
        },
        'resolution': {'x': len(fast_pts), 'y': len(slow_pts)},
        'dwell_time': float(dwell),
        'scan_time': scan_time,
    }

    data_path = data_manager.save_scan_data(scan_data, save_params)
    plot_scan_results(scan_data, data_path,
                      axis_labels=(axis_names[0], axis_names[1]))
    np.savez(data_path.replace('.csv', '.npz'), **npz_kwargs)
    save_tiff_with_imagej_metadata(
        image_data=result,
        filepath=data_path.replace('.csv', '.tiff'),
        x_points=fast_pts,
        y_points=slow_pts,
        scan_config=save_params,
        timestamp=timestamp_str,
    )
    bridge.notify("💾 Scan data saved")


# --------------------- HARDWARE-TIMED SCANNING FUNCTION ---------------------
def _run_raster_scan(mode, axis_names, axes_list, points_list, dwell, z_dwell, save=True):
    """Run a hardware-timed raster over the given axes (fast..slow), in µm.

    Builds the multi-channel waveform through ``raster_engine``, drives it with
    ``scanning_core.run_hardware_timed_sweep`` (AO clock exported to the Time
    Tagger for CountBetweenMarkers), and reconstructs a 2D image or 3D volume.
    """
    global image

    with scan_lock:
        if scan_in_progress[0]:
            bridge.notify("⚠️ A scan is already in progress")
            return None
        scan_in_progress[0] = True
        stop_scan_requested[0] = False

    scanned = set(axis_names)
    points_list = [np.asarray(p, dtype=float) for p in points_list]

    # Z position to restore after a Z-involving scan (the user's focus plane
    # from the Z-Control spinbox). None for modes that don't move Z.
    z_return = None

    try:
        n_flyback = _flyback_samples(dwell, z_dwell, scanned)
        shape, stride, width, n_lines = raster_engine.raster_geometry(points_list, n_flyback)
        result = np.zeros(shape, dtype=np.float32)

        # Scales in acquisition order (slow..fast).
        scales = tuple(um_scale(p[0], p[-1], len(p)) for p in reversed(points_list))
        units = tuple('µm' for _ in shape)

        # Pre-position: scanned galvo axes go to their start, fixed galvo axes
        # hold their current position; scanned Z pre-moves and settles.
        x_um = points_list[axis_names.index('x')][0] if 'x' in scanned else current_position_um['x']
        y_um = points_list[axis_names.index('y')][0] if 'y' in scanned else current_position_um['y']
        output_task.write([axis_x.position_to_voltage(x_um),
                           axis_y.position_to_voltage(y_um)])
        current_position_um['x'], current_position_um['y'] = x_um, y_um

        if 'z' in scanned and z_controller.available:
            # Remember the user's focus plane (Z-Control spinbox) so we can
            # return there after the sweep leaves Z at z_max.
            try:
                z_return = float(piezo_control_widget.pos_spinbox.value())
            except Exception:
                z_return = z_controller.position
            z_start = float(points_list[axis_names.index('z')][0])
            z_controller.set_position(z_start)
            current_position_um['z'] = z_start
            time.sleep(z_dwell)  # initial settle before the sweep begins

        target_layer = _prepare_scan_layer(mode, result, scales, units)

        # Release AO channels from the persistent on-demand task so the
        # hardware-timed task can reserve them.
        output_task.stop()
        output_task.control(TaskMode.TASK_UNRESERVE)

        start_time = time.time()

        def _on_progress(counts, bins):
            arr = raster_engine.reconstruct(counts, bins, shape, stride, width)
            def _upd():
                target_layer.data = arr
                update_contrast_limits(target_layer, arr)
                target_layer.refresh()
            bridge.run_on_main(_upd)

        counts, bins, _sh, _st, _w = raster_engine.run_raster(
            tagger, axes_list, points_list, dwell, n_flyback,
            on_progress=_on_progress,
            stop_check=lambda: stop_scan_requested[0],
            task_ref=scan_task_ref, cbm_ref=cbm_ref, lock=scan_lock,
        )

        if stop_scan_requested[0]:
            bridge.notify("🛑 Scan stopped by user")
            return None

        result = raster_engine.reconstruct(counts, bins, shape, stride, width)
        end_time = time.time()

        def _final():
            target_layer.data = result
            update_contrast_limits(target_layer, result)
        bridge.run_on_main(_final)

        if mode == 'XY':
            image = result

        print(f"Scan[{mode}] time: {end_time - start_time:.2f}s shape={shape} "
              f"flyback={n_flyback} (hardware-timed)")

        if save:
            save_result = result.copy()
            save_points = [p.copy() for p in points_list]
            scan_time = end_time - start_time
            threading.Thread(
                target=_save_scan,
                args=(mode, list(axis_names), save_points, save_result,
                      scales, dwell, z_dwell, scan_time),
                daemon=True,
            ).start()

    finally:
        # Restore the persistent on-demand galvo task and park at zero.
        try:
            output_task.start()
            output_task.write([0, 0])
            current_position_um['x'], current_position_um['y'] = 0.0, 0.0
        except Exception as e:
            bridge.notify(f"⚠️ Failed to restart galvo control: {e}")
        bridge.notify("🎯 Scanner returned to zero position")

        # For Z-involving scans, return the piezo to the user's focus plane
        # (Z-Control spinbox) instead of leaving it at the sweep's z_max. The
        # scan task that reserved ao2 is already closed here, so the ephemeral
        # set_position write is safe.
        if z_return is not None and z_controller.available:
            try:
                z_controller.set_position(z_return)
                current_position_um['z'] = z_return
                piezo_control_widget._update_position_signal.emit(z_return)
                bridge.notify(f"🎯 Z returned to {z_return:.2f} µm")
            except Exception as e:
                bridge.notify(f"⚠️ Failed to restore Z position: {e}")

        with scan_lock:
            scan_in_progress[0] = False

    return points_list


def scan_pattern(x_points, y_points):
    """XY raster entry point (used by zoom / reset zoom), in micrometers."""
    params = scan_params_manager.get_params()
    dwell = params['dwell_time']
    z_dwell = params['z_scan']['dwell_time']
    _run_raster_scan('XY', ['x', 'y'], [axis_x, axis_y],
                     [np.asarray(x_points, float), np.asarray(y_points, float)],
                     dwell, z_dwell)
    return x_points, y_points


def _build_axis_points(params):
    xr = params['scan_range']['x']
    yr = params['scan_range']['y']
    zr = params['z_scan']['range']
    return {
        'x': np.linspace(xr[0], xr[1], params['resolution']['x']),
        'y': np.linspace(yr[0], yr[1], params['resolution']['y']),
        'z': np.linspace(zr[0], zr[1], params['z_scan']['resolution']),
    }


def run_selected_scan():
    """Mode-aware New Scan dispatch based on the Scan Parameters selector."""
    params = scan_params_manager.get_params()
    mode = params.get('scan_mode', 'XY')
    all_pts = _build_axis_points(params)
    dwell = params['dwell_time']
    z_dwell = params['z_scan']['dwell_time']
    axis_names = MODE_AXES.get(mode, ['x', 'y'])

    if mode == 'XY':
        # Keep XY going through the manager so zoom history stays consistent.
        scan_points_manager.update_points(
            x_range=[all_pts['x'][0], all_pts['x'][-1]],
            y_range=[all_pts['y'][0], all_pts['y'][-1]],
            x_res=len(all_pts['x']), y_res=len(all_pts['y']),
        )
        scan_pattern(all_pts['x'], all_pts['y'])
        return

    axes_list = [AXES[n] for n in axis_names]
    points_list = [all_pts[n] for n in axis_names]
    _run_raster_scan(mode, axis_names, axes_list, points_list, dwell, z_dwell)

# --------------------- DATA PATH FUNCTION ---------------------
def get_data_path():
    """Helper function to get current data path"""
    return data_path

# --------------------- CREATE WIDGETS USING FACTORIES ---------------------

# Create scan control widgets (New Scan is mode-aware via run_selected_scan)
new_scan_widget = create_new_scan(run_selected_scan, shapes, bridge, scan_in_progress)
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
piezo_control_widget = PiezoControlWidget(z_controller, scan_in_progress)

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