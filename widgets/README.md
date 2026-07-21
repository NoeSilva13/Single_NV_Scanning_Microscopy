# Widgets Package for the Confocal Scanning GUI

This package contains all the GUI widgets used by the confocal scanning application ([confocal_main_control.py](../confocal_main_control.py)), organized into logical modules for better maintainability and reusability.

## Module Structure

```
widgets/
├── __init__.py              # Package initialization and exports
├── scan_controls.py         # Scan control widgets (new scan, reset zoom, etc.)
├── camera_controls.py       # Camera control widgets and threads
├── auto_focus.py           # Scan Z tab (pyqtgraph plot + button) & linear Z-sweep logic
├── single_axis_scan.py     # Single axis scan widget
├── file_operations.py      # File loading/saving widgets
├── axis_controls.py       # Manual X/Y/Z position widget (galvo ao0/ao1 + piezo ao2)
└── README.md               # This file
```

## Usage

### Importing Widgets

```python
from widgets.scan_controls import (
    new_scan,
    close_scanner,
    save_image,
    reset_zoom,
    update_scan_parameters,
    update_scan_parameters_widget,
    stop_scan
)

from widgets.camera_controls import (
    camera_live,
    capture_shot,
    CameraControlWidget,
    CameraUpdateThread,
    create_camera_control_widget
)

from widgets.auto_focus import AutoFocusWidget

from widgets.single_axis_scan import SingleAxisScanWidget
from widgets.file_operations import load_scan
from widgets.axis_controls import AxisControlWidget
```

### Widget Factory Functions

Most widgets are implemented as factory functions that take dependencies as parameters. This design pattern provides several benefits:

1. **Dependency Injection**: Clear dependencies are required at creation time
2. **Testability**: Easy to mock dependencies for testing
3. **Flexibility**: Same widget can be used with different configurations
4. **Decoupling**: Widgets don't depend on global variables

#### Example: Creating a New Scan Widget

```python
# Dependencies
run_scan_func = run_selected_scan  # mode-aware dispatch (XY/XZ/YZ/XYZ)
shapes_layer = viewer.layers['shapes']
bridge = GUIBridge()  # from thread_safe_bridge, for thread-safe UI updates

# Create widget
new_scan_widget = new_scan(run_scan_func, shapes_layer, bridge, scan_in_progress=[False])

# Add to viewer
viewer.window.add_dock_widget(new_scan_widget, area="bottom")
```

### State Management Classes

`confocal_main_control.py` defines three helper classes for managing application state, which are passed into the widget factories above as dependencies:

```python
class ScanParametersManager:
    """Reads/writes scan range, resolution, and dwell time from the
    ScanParametersWidget instance created by widgets.scan_controls.update_scan_parameters"""
    def __init__(self, widget_instance=None)
    def set_widget_instance(self, widget_instance)
    def get_params(self)
    def update_scan_parameters(self, x_range=None, y_range=None, x_res=None, y_res=None, dwell_time=None)

class ScanPointsManager:
    """Manages the X/Y micrometer linspace grids used for scanning"""
    def __init__(self, scan_params_manager)
    def update_points(self, x_range=None, y_range=None, x_res=None, y_res=None)
    def get_points(self)

class ZoomLevelManager:
    """Tracks nested zoom-region depth (default max: utils.MAX_ZOOM_LEVEL = 9)"""
    def __init__(self, max_zoom=MAX_ZOOM_LEVEL)
    def get_zoom_level(self)
    def set_zoom_level(self, level)
    def can_zoom_in(self)
```

## Widget Reference

### Scan Controls (`scan_controls.py`)

- **`new_scan(run_scan_func, shapes, bridge=None, scan_in_progress=None)`**
  - Creates a "🔬 New Scan" button widget
  - Calls `run_scan_func()` (mode-aware dispatch, e.g. `run_selected_scan` for XY/XZ/YZ/XYZ) in a background thread; clears the zoom-region shape when done

- **`close_scanner(output_task)`**
  - Creates a "🎯 Set to Zero" button widget
  - Writes [0, 0] V to the galvo AO channels in a background thread

- **`save_image(viewer, data_path_func)`**
  - Creates a "📷 Save Image" button widget
  - Screenshots the current napari canvas, named after the last saved scan's data path

- **`reset_zoom(scan_pattern_func, scan_history, scan_params_manager, scan_points_manager, shapes, update_scan_parameters_func, update_scan_parameters_widget_func, zoom_level_manager, bridge=None, scan_in_progress=None)`**
  - Creates a "🔄 Reset Zoom" button widget
  - Returns to the original (level-0) scan range and resets zoom level to 0

- **`update_scan_parameters(scan_params_manager)`**
  - Returns a `ScanParametersWidget` (`QWidget`) with a **Scan Mode** selector (XY/XZ/YZ/XYZ), X/Y/Z range and resolution spinboxes (all in µm), and XY/Z dwell-time fields; Z fields are exposed via `get_parameters()['z_scan']` and the mode via `get_parameters()['scan_mode']`
  - All positions are returned in micrometers (canonical unit); the µm↔V conversion is deferred to the DAQ boundary
  - Registers itself as the `scan_params_manager`'s widget instance; values are applied live (New Scan syncs XY points from the spinboxes at start; no Apply button)

- **`update_scan_parameters_widget(widget_instance, scan_params_manager, bridge=None)`**
  - Returns a callback that refreshes the parameter widget's displayed values from the manager; marshals to the main thread via `bridge` if provided

- **`stop_scan(scan_in_progress, stop_scan_requested, scan_task_ref=None, cbm_ref=None, scan_lock=None)`**
  - Creates a "🛑 Stop Scan" button widget
  - Signals an in-progress scan to abort and stops the active DAQ task / TimeTagger `CountBetweenMarkers` measurement

### Camera Controls (`camera_controls.py`)

- **`camera_live(viewer, get_camera_type_func=None)`**
  - Creates a "🎥 Camera Live" toggle button
  - Starts/stops a live camera feed as a napari image layer; supports POA, ZWO, and USB webcam backends via `get_camera_type_func`

- **`capture_shot(viewer, settings_callback=None, get_camera_type_func=None)`**
  - Creates a "📸 Single Shot" button
  - Captures a single frame from the selected camera backend and adds it as a new napari layer

- **`CameraControlWidget(camera_live_widget, capture_shot_widget, parent=None)`**
  - Composite `QWidget` with a camera-type dropdown (POA / ZWO / USB), the live/capture buttons, and exposure & gain sliders whose ranges adapt per camera type

- **`CameraUpdateThread(camera)`**
  - Background `QThread` polling the active camera at ~30 FPS, emitting frames via a Qt signal

- **`create_camera_control_widget(viewer)`**
  - Factory that wires `camera_live`, `capture_shot`, and `CameraControlWidget` together into one ready-to-dock widget (this is what `confocal_main_control.py` actually imports)

### Scan Z / Auto Focus (`auto_focus.py`)

- **`run_z_sweep(tagger, z_controller, positions, dwell_time, plot_callback=None, ...)`**
  - Single linear Z sweep over the given positions (µm)
  - Hardware-timed piezo ramp on `ao2`; photons are counted per point by `CountBetweenMarkers` (via `scanning_core.run_hardware_timed_sweep`)
  - `plot_callback(stage, positions, rates)` is invoked during the sweep with the accumulated data for real-time plotting
  - Returns `(positions, count_rates)`; does **not** move the piezo to the peak

- **`AutoFocusWidget(tagger, z_controller, scan_params_manager, scan_lock, scan_in_progress, stop_scan_requested, scan_task_ref, cbm_ref)`**
  - Compact `QWidget` with a **"🔍 Scan Z"** button and a **pyqtgraph** result plot (single green curve + red peak marker)
  - Reads Z Min / Z Max / Z Resolution / Z Dwell from `scan_params_manager` (Scan Parameters panel), builds `np.linspace(z_min, z_max, z_res)`, and runs `run_z_sweep` in a background thread
  - Mutually exclusive with the raster/single-axis scans via the shared `scan_lock`/`scan_in_progress`; uses internal Qt signals for thread-safe UI updates
  - Leaves the piezo at the end of the ramp (Z max); notifies the detected peak without moving to it
  - Set `.z_control_widget` to have the axis control widget's Z position refreshed after a completed sweep

### Single Axis Scan (`single_axis_scan.py`)

- **`SingleAxisScanWidget(scan_params_manager, layer, output_task, tagger, galvo_controller, scan_lock, scan_in_progress, stop_scan_requested, scan_task_ref, cbm_ref)`**
  - Complete widget for 1D X/Y line scans at the current galvo position
  - Runs a hardware-timed AO ramp on the scanned galvo axis (holding the other fixed) with per-point photon counting via `CountBetweenMarkers` (`scanning_core.run_hardware_timed_sweep`); mutually exclusive with the raster/Scan Z scans
  - Uses a `QTabWidget` with separate **X Axis** and **Y Axis** tabs; each tab holds its own scan button and a `pyqtgraph` result plot (with a red peak marker), and `update_current_position(x, y)` tracks the galvo's last commanded position
  - `add_z_tab(widget, title='Z Axis')` embeds an external panel (the `AutoFocusWidget`, whose button is labelled **"Scan Z"**) as a third tab so X/Y/Z line scans share one dock

### File Operations (`file_operations.py`)

- **`load_scan(viewer, scan_params_manager=None, scan_points_manager=None, update_widget_func=None)`**
  - Creates a "Load Scan" button widget
  - Opens a file dialog for `.npz` files, adds the loaded scan as a new napari layer at the correct physical scale, and optionally re-applies its saved parameters to the scan-parameters widget

### Axis Controls (`axis_controls.py`)

- **`AxisControlWidget(axis_x, axis_y, z_controller, output_task, scan_in_progress, move_callback=None)`**
  - Manual control for all three axes: galvo X/Y (written together through the persistent `output_task`) and piezo Z (via `DAQZController`, DAQ `ao2` → piezo EXT IN)
  - Each axis has a synced slider (coarse drag) + spinbox (fine, 3 decimals / 0.001 µm); X/Y ranges come from the axes' `travel_um`, Z spans 0–450 µm
  - Debounced (150 ms) moves run in a short background thread; refused while a scan owns the DAQ (`scan_in_progress`)
  - Tracks the last commanded position (no analog readback); `refresh_positions(x, y, z)` updates the display without moving hardware (used on click-to-move and at end of a scan), and `move_callback(x, y, z)` lets the app mirror the new position into its own state
  - `z_value()` returns the current Z spinbox value; `_update_ui_with_current_position()` refreshes Z after a Scan Z sweep

## Design Pattern: Factory Functions Over Globals

This package was originally extracted from a monolithic script that used `@magicgui`-decorated functions reading/writing module-level globals. The widgets here instead follow a factory pattern:

### Anti-pattern (globals)
```python
@magicgui(call_button="🔬 New Scan")
def new_scan():
    global original_x_points, original_y_points
    # ... implementation
```

### Current pattern (explicit dependencies)
```python
from widgets.scan_controls import new_scan as create_new_scan

# Create widget with explicit dependencies (see confocal_main_control.py for the real wiring)
new_scan_widget = create_new_scan(scan_pattern, scan_points_manager, shapes, bridge, scan_in_progress)
```

## Benefits of This Structure

1. **Modularity**: Each widget type is in its own file
2. **Testability**: Widgets can be tested independently
3. **Reusability**: Widgets can be used in other applications
4. **Maintainability**: Easier to find and modify specific functionality
5. **Scalability**: Easy to add new widgets without cluttering main file
6. **Dependency Management**: Clear dependencies and interfaces

## Testing

Each widget module can be tested independently:

```python
import pytest
from unittest.mock import Mock
from widgets.scan_controls import new_scan

def test_new_scan_widget():
    # Mock dependencies
    scan_func = Mock()
    scan_points_manager = Mock()
    shapes = Mock()
    
    # Create widget
    widget = new_scan(scan_func, scan_points_manager, shapes)
    
    # Test widget properties
    assert widget.call_button.text == "🔬 New Scan"
```

This structure provides a solid foundation for building complex scientific applications with maintainable and testable code. 