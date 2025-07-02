"""
Confocal Single-NV Microscopy Control Software (Refactored)
-------------------------------------------
This software controls a confocal microscope setup for single NV center imaging using:
- Thorlabs LSKGG4 Galvo-Galvo Scanner
- National Instruments USB-6453 DAQ
- Single Photon Detector SPD

The system provides real-time visualization and control through a Napari-based GUI.

This is a refactored version showing how the widgets are extracted to separate modules.
"""

# Standard library imports
import json
import threading
import time

# Third-party imports
import numpy as np 
import napari
import nidaqmx
from napari.utils.notifications import show_info
from PyQt5.QtWidgets import QDesktopWidget
from TimeTagger import createTimeTagger, Counter, createTimeTaggerVirtual
from magicgui import magicgui

# Local imports
from galvo_controller import GalvoScannerController
from data_manager import DataManager
from plot_widgets.live_plot_napari_widget import live_plot
from plot_scan_results import plot_scan_results
from utils import calculate_scale, MICRONS_PER_VOLT
from qtpy.QtWidgets import QWidget

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
from widgets.auto_focus import (
    auto_focus as create_auto_focus,
    SignalBridge
)
from widgets.single_axis_scan import SingleAxisScanWidget
from widgets.file_operations import load_scan as create_load_scan
from widgets.odmr_controls import launch_odmr_gui as create_launch_odmr_gui

# --------------------- CONFIGURATION MANAGER CLASS ---------------------
class ConfigManager:
    """Manages configuration loading, saving, and updates"""
    
    def __init__(self, config_file="config_template.json"):
        self.config_file = config_file
        self.config = self._load_config()
    
    def _load_config(self):
        with open(self.config_file, 'r') as f:
            return json.load(f)
    
    def get_config(self):
        return self.config
    
    def update_scan_parameters(self, x_range=None, y_range=None, x_res=None, y_res=None):
        if x_range is not None:
            self.config['scan_range']['x'] = x_range
        if y_range is not None:
            self.config['scan_range']['y'] = y_range
        if x_res is not None:
            self.config['resolution']['x'] = x_res
        if y_res is not None:
            self.config['resolution']['y'] = y_res
        
        self._save_config()
    
    def _save_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=4)

# --------------------- SCAN POINTS MANAGER CLASS ---------------------
class ScanPointsManager:
    """Manages scan point generation and updates"""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.original_x_points = None
        self.original_y_points = None
        self._update_points_from_config()
    
    def _update_points_from_config(self):
        config = self.config_manager.get_config()
        x_range = config['scan_range']['x']
        y_range = config['scan_range']['y']
        x_res = config['resolution']['x']
        y_res = config['resolution']['y']
        
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
    
    def __init__(self, max_zoom=6):
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
config_manager = ConfigManager()
scan_points_manager = ScanPointsManager(config_manager)
zoom_manager = ZoomLevelManager()

# Initialize hardware controllers
galvo_controller = GalvoScannerController()
data_manager = DataManager()

# Extract scan parameters from config for initial setup
config = config_manager.get_config()
x_res = config['resolution']['x']
y_res = config['resolution']['y']

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

# Initialize DAQ output task for galvo control
output_task = nidaqmx.Task()
output_task.ao_channels.add_ao_voltage_chan(galvo_controller.xin_control)
output_task.ao_channels.add_ao_voltage_chan(galvo_controller.yin_control)
output_task.start()

# --------------------- SCALE FUNCTION (imported from utils) ---------------------

# --------------------- NAPARI VIEWER SETUP ---------------------
viewer = napari.Viewer(title="NV Scanning Microscopy")
# Set window size to maximum screen size
screen = QDesktopWidget().screenGeometry()
viewer.window.resize(screen.width(), screen.height())

# Add an image layer to display the live scan
layer = viewer.add_image(image, name="live scan", colormap="viridis", scale=(1, 1), contrast_limits=contrast_limits)
# Add a shapes layer to display the zoom area
shapes = viewer.add_shapes(name="zoom area", shape_type="rectangle", edge_color='red', face_color='transparent', edge_width=0)

# Configure scale bar
viewer.scale_bar.visible = True
viewer.scale_bar.unit = "µm"
viewer.scale_bar.position = "bottom_left"

# Calculate scale (in microns/pixel)
x_range = config['scan_range']['x']
y_range = config['scan_range']['y']
scale_um_per_px_x = calculate_scale(x_range[0], x_range[1], x_res)
scale_um_per_px_y = calculate_scale(y_range[0], y_range[1], y_res)
layer.scale = (scale_um_per_px_y, scale_um_per_px_x)

# --------------------- TIMETAGGER SETUP ---------------------
try:
    tagger = createTimeTagger()
    tagger.reset()
    show_info("✅ Connected to real TimeTagger device")
except Exception as e:
    show_info("⚠️ Real TimeTagger not detected, using virtual device")
    tagger = createTimeTaggerVirtual("TimeTagger/time_tags_test.ttbin")
    tagger.run()

# Set bin width to 5 ns
binwidth = int(5e9)
n_values = 1
counter = Counter(tagger, [1], binwidth, n_values)

# --------------------- CLICK HANDLER FOR SCANNER POSITIONING ---------------------
def on_mouse_click(layer, event):
    """Handle mouse click events to move the galvo scanner to the clicked position."""
    coords = layer.world_to_data(event.position)
    x_idx, y_idx = int(round(coords[1])), int(round(coords[0]))
    
    # Get current ranges from config manager
    config = config_manager.get_config()
    x_range = config['scan_range']['x']
    y_range = config['scan_range']['y']
    x_res = config['resolution']['x']
    y_res = config['resolution']['y']
    
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

# --------------------- MPL WIDGET (SIGNAL LIVE PLOT) ---------------------
mpl_widget = live_plot(measure_function=lambda: counter.getData()[0][0]/(binwidth/1e12), histogram_range=100, dt=0.2)
viewer.window.add_dock_widget(mpl_widget, area='right', name='Signal Plot')

# --------------------- SCANNING FUNCTION ---------------------
def scan_pattern(x_points, y_points):
    """Perform a raster scan pattern using the galvo mirrors and collect APD counts."""
    global image, layer, data_path
    
    scan_in_progress[0] = True
    stop_scan_requested[0] = False
    
    try:
        height, width = len(y_points), len(x_points)
        image = np.zeros((height, width), dtype=np.float32)
        layer.data = image
        layer.contrast_limits = contrast_limits
        
        for y_idx, y in enumerate(y_points):
            for x_idx, x in enumerate(x_points):
                if stop_scan_requested[0]:
                    show_info("🛑 Scan stopped by user")
                    output_task.write([0, 0])  # Return to zero position
                    scan_in_progress[0] = False
                    return None, None
                    
                output_task.write([x, y])
                if x_idx == 0:
                    time.sleep(0.05)
                else:
                    time.sleep(0.001)
                    
                counts = counter.getData()[0][0]/(binwidth/1e12)
                print(f"{counts}")
                image[y_idx, x_idx] = counts
                layer.data = image
        
        # Adjust contrast and save data
        try:
            if image.size == 0 or np.all(np.isnan(image)):
                show_info('⚠️ Image is empty or contains only NaNs. Contrast not updated.')
            else:
                min_val = np.nanmin(image)
                max_val = np.nanmax(image)
                if np.isclose(min_val, max_val):
                    show_info('⚠️ Image min and max are equal. Contrast not updated.')
                else:
                    layer.contrast_limits = (min_val, max_val)
        except Exception as e:
            show_info(f'❌ Error setting contrast limits: {str(e)}')
        
        scale_um_per_px_x = calculate_scale(x_points[0], x_points[-1], width)
        scale_um_per_px_y = calculate_scale(y_points[0], y_points[-1], height)
        layer.scale = (scale_um_per_px_y, scale_um_per_px_x)
        
        # Create a dictionary with image and scan positions
        scan_data = {
            'image': image,
            'x_points': x_points,
            'y_points': y_points,
            'scale_x': scale_um_per_px_x,
            'scale_y': scale_um_per_px_y
        }
        data_path = data_manager.save_scan_data(scan_data)
        plot_scan_results(scan_data, data_path)
        
        # Save image with scale information
        np.savez(data_path.replace('.csv', '.npz'), 
                 image=image,
                 scale_x=scale_um_per_px_x,
                 scale_y=scale_um_per_px_y)
        layer.save(data_path.replace('.csv', '.tiff'))
        
    finally:
        # Return scanner to zero position after scan
        output_task.write([0, 0])
        show_info("🎯 Scanner returned to zero position")
        scan_in_progress[0] = False
        
    return x_points, y_points

# --------------------- DATA PATH FUNCTION ---------------------
def get_data_path():
    """Helper function to get current data path"""
    return data_path

# --------------------- CREATE WIDGETS USING FACTORIES ---------------------

# Create scan control widgets
new_scan_widget = create_new_scan(scan_pattern, scan_points_manager, shapes)
close_scanner_widget = create_close_scanner(output_task)
save_image_widget = create_save_image(viewer, get_data_path)
update_scan_parameters_widget = create_update_scan_parameters(config_manager, scan_points_manager)
update_widget_func = create_update_scan_parameters_widget(update_scan_parameters_widget, config_manager)

# Create stop scan widget
stop_scan_widget = create_stop_scan(scan_in_progress, stop_scan_requested)
stop_scan_widget.native.setFixedSize(150, 50)

reset_zoom_widget = create_reset_zoom(
    scan_pattern, scan_history, config_manager, scan_points_manager,
    shapes, lambda **kwargs: config_manager.update_scan_parameters(**kwargs), 
    update_widget_func,
    zoom_manager
)

# Create camera control widgets
camera_control_widget = create_camera_control_widget(viewer)

# Create auto-focus widgets
signal_bridge = SignalBridge(viewer)
auto_focus_widget = create_auto_focus(counter, binwidth, signal_bridge)

# Create single axis scan widget
single_axis_scan_widget = SingleAxisScanWidget(
    config_manager, layer, output_task, counter, binwidth
)

# Set the global reference for position tracking
single_axis_widget_ref = single_axis_scan_widget

# Create file operation widgets
load_scan_widget = create_load_scan(viewer)

# Create ODMR control widgets
launch_odmr_widget = create_launch_odmr_gui(tagger=tagger, counter=counter, binwidth=binwidth)

# Store reference globally or in a persistent place
_plot_profile_dock = None

@magicgui(call_button="📈 Plot Profile")
def _add_plot_profile():
    global _plot_profile_dock

    try:
        if _plot_profile_dock is None or not isinstance(_plot_profile_dock, QWidget):
            _plot_profile_dock, _ = viewer.window.add_plugin_dock_widget(
                plugin_name='napari-plot-profile',
            )
            _plot_profile_dock.setFloating(True)
        else:
            # If already added once, just re-show it
            _plot_profile_dock.show()
            _plot_profile_dock.raise_()
    except Exception as e:
        show_info(f'❌ Could not add plot profile widget: {str(e)}')

plot_profile_widget = _add_plot_profile

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
    max_x = min(width, max_x)
    min_y = max(0, min_y)
    max_y = min(height, max_y)

    # Save current state for zoom history
    current_x_points, current_y_points = scan_points_manager.get_points()
    scan_history.append((current_x_points, current_y_points))

    # Calculate new scan points maintaining original resolution
    current_config = config_manager.get_config()
    current_x_res = current_config['resolution']['x']
    current_y_res = current_config['resolution']['y']
    x_zoom = np.linspace(current_x_points[min_x], current_x_points[max_x - 1], current_x_res)
    y_zoom = np.linspace(current_y_points[min_y], current_y_points[max_y - 1], current_y_res)

    def run_zoom():
        global zoom_in_progress
        zoom_in_progress = True
        
        config_manager.update_scan_parameters(
            x_range=[x_zoom[0], x_zoom[-1]],
            y_range=[y_zoom[0], y_zoom[-1]],
            x_res=current_x_res,
            y_res=current_y_res
        )
        scan_points_manager.update_points(
            x_range=[x_zoom[0], x_zoom[-1]],
            y_range=[y_zoom[0], y_zoom[-1]],
            x_res=current_x_res,
            y_res=current_y_res
        )
        
        shapes.data = []
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
auto_focus_widget.native.setFixedSize(150, 50)
load_scan_widget.native.setFixedSize(150, 50)
launch_odmr_widget.native.setFixedSize(150, 50)
plot_profile_widget.native.setFixedSize(150, 50)

# Add widgets to viewer
viewer.window.add_dock_widget(new_scan_widget, area="bottom")
viewer.window.add_dock_widget(stop_scan_widget, area="bottom")
viewer.window.add_dock_widget(save_image_widget, area="bottom")
viewer.window.add_dock_widget(reset_zoom_widget, area="bottom")
viewer.window.add_dock_widget(close_scanner_widget, area="bottom")
viewer.window.add_dock_widget(auto_focus_widget, area="bottom")
viewer.window.add_dock_widget(load_scan_widget, area="bottom")
viewer.window.add_dock_widget(launch_odmr_widget, area="bottom")
viewer.window.add_dock_widget(plot_profile_widget, area="bottom")
update_scan_parameters_dock = viewer.window.add_dock_widget(update_scan_parameters_widget, area="left", name="Scan Parameters")
camera_control_dock = viewer.window.add_dock_widget(camera_control_widget, name="Camera Control", area="right")
viewer.window.add_dock_widget(single_axis_scan_widget, name="Single Axis Scan", area="right")
viewer.window._qt_window.tabifyDockWidget(update_scan_parameters_dock, camera_control_dock)


# Initialize empty auto-focus plot
empty_positions = [0, 1]
empty_counts = [0, 0]
signal_bridge.update_focus_plot_signal.emit(empty_positions, empty_counts, 'Auto-Focus Plot')

# --------------------- CLEANUP ON CLOSE ---------------------
default_config = {
    "scan_range": {
        "x": [-1.0, 1.0],
        "y": [-1.0, 1.0]
    },
    "resolution": {
        "x": 10,
        "y": 10
    },
    "dwell_time": 0.1
}

def _on_close():
    """Reset config file to default values and set scanner to zero when closing the app"""
    try:
        # Set scanner to zero position before closing
        output_task.write([0, 0])
        show_info("🎯 Scanner set to zero position")
        
        # Reset config file to default values
        with open("config_template.json", 'w') as f:
            json.dump(default_config, f, indent=4)
        show_info("✨ Config reset to default values")
    except Exception as e:
        show_info(f"❌ Error during app closure: {str(e)}")

# Register cleanup using Qt's destroyed signal
viewer.window._qt_window.destroyed.connect(_on_close)

def main():
    """Main application entry point"""
    napari.run()  # Start the Napari event loop

if __name__ == "__main__":
    main() 