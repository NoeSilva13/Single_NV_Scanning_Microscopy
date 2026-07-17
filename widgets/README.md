# Widgets Package for the Confocal Scanning GUI

This package contains all the GUI widgets used by the confocal scanning application ([confocal_main_control.py](../confocal_main_control.py)), organized into logical modules for better maintainability and reusability.

## Module Structure

```
widgets/
├── __init__.py              # Package initialization and exports
├── scan_controls.py         # Scan control widgets (new scan, reset zoom, etc.)
├── camera_controls.py       # Camera control widgets and threads
├── auto_focus.py           # Auto-focus functionality and signal bridge
├── single_axis_scan.py     # Single axis scan widget
├── file_operations.py      # File loading/saving widgets
├── piezo_controls.py      # Manual Z position widget (DAQ ao2 → piezo EXT IN)
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

from widgets.auto_focus import (
    auto_focus,
    SignalBridge
)

from widgets.single_axis_scan import SingleAxisScanWidget
from widgets.file_operations import load_scan
from widgets.piezo_controls import PiezoControlWidget
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
scan_pattern_func = my_scan_function
scan_points_manager = ScanPointsManager(scan_params_manager)
shapes_layer = viewer.layers['shapes']
bridge = GUIBridge()  # from thread_safe_bridge, for thread-safe UI updates

# Create widget
new_scan_widget = new_scan(scan_pattern_func, scan_points_manager, shapes_layer, bridge, scan_in_progress=[False])

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
    """Manages the X/Y voltage linspace grids used for scanning"""
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

- **`new_scan(scan_pattern_func, scan_points_manager, shapes, bridge=None, scan_in_progress=None)`**
  - Creates a "🔬 New Scan" button widget
  - Runs the scan in a background thread; clears the zoom-region shape when done

- **`close_scanner(output_task)`**
  - Creates a "🎯 Set to Zero" button widget
  - Writes [0, 0] V to the galvo AO channels in a background thread

- **`save_image(viewer, data_path_func)`**
  - Creates a "📷 Save Image" button widget
  - Screenshots the current napari canvas, named after the last saved scan's data path

- **`reset_zoom(scan_pattern_func, scan_history, scan_params_manager, scan_points_manager, shapes, update_scan_parameters_func, update_scan_parameters_widget_func, zoom_level_manager, bridge=None, scan_in_progress=None)`**
  - Creates a "🔄 Reset Zoom" button widget
  - Returns to the original (level-0) scan range and resets zoom level to 0

- **`update_scan_parameters(scan_params_manager, scan_points_manager)`**
  - Returns a `ScanParametersWidget` (`QWidget`) with X/Y range, resolution, and dwell-time spinboxes (plus live µm distance labels)
  - Registers itself as the `scan_params_manager`'s widget instance

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

### Auto Focus (`auto_focus.py`)

- **`run_focus_sweep(tagger, z_controller, dwell_time, progress_callback=None, ...)`**
  - Coarse + fine Z sweep that maximizes SPD count rate
  - Each phase is a hardware-timed piezo ramp on `ao2`; photons are counted per point by `CountBetweenMarkers` (via `scanning_core.run_hardware_timed_sweep`)
  - Returns `(coarse_positions, coarse_counts, fine_positions, fine_counts, optimal_pos)`

- **`auto_focus(tagger, scan_params_manager, signal_bridge, z_controller, scan_lock, scan_in_progress, stop_scan_requested, scan_task_ref, cbm_ref)`**
  - Creates "🔍 Auto Focus" button widget
  - Runs `run_focus_sweep` in a background thread (mutually exclusive with the raster/single-axis scans via the shared `scan_lock`/`scan_in_progress`) and updates the focus plot / Z widget

- **`SignalBridge(viewer)`**
  - Thread-safe `QObject` bridge for GUI updates emitted from the auto-focus worker thread
  - Handles focus-plot creation/updates and forwards Z position updates to the piezo control widget (`z_control_widget`)

- **`create_focus_plot_widget(coarse_pos, coarse_counts, fine_pos=None, fine_counts=None)`**
  - Creates a `SingleAxisPlot`-based plot widget (from `plot_widgets`) that shows the coarse and fine sweeps as separate series

### Single Axis Scan (`single_axis_scan.py`)

- **`SingleAxisScanWidget(scan_params_manager, layer, output_task, tagger, galvo_controller, scan_lock, scan_in_progress, stop_scan_requested, scan_task_ref, cbm_ref)`**
  - Complete widget for 1D X/Y line scans at the current galvo position
  - Runs a hardware-timed AO ramp on the scanned galvo axis (holding the other fixed) with per-point photon counting via `CountBetweenMarkers` (`scanning_core.run_hardware_timed_sweep`); mutually exclusive with the raster/auto-focus scans
  - Includes scan buttons, a result plot (`SingleAxisPlot`), and `update_current_position(x, y)` for tracking the galvo's last commanded position

### File Operations (`file_operations.py`)

- **`load_scan(viewer, scan_params_manager=None, scan_points_manager=None, update_widget_func=None)`**
  - Creates a "Load Scan" button widget
  - Opens a file dialog for `.npz` files, adds the loaded scan as a new napari layer at the correct physical scale, and optionally re-applies its saved parameters to the scan-parameters widget

### Piezo Controls (`piezo_controls.py`)

- **`PiezoControlWidget(z_controller)`**
  - Manual Z-axis control via `DAQZController` (DAQ `ao2` → piezo EXT IN)
  - Features:
    - Debounced position spinbox (0–450 µm)
    - Displays last commanded position (no analog readback)
    - Spinbox disabled if the DAQ channel is unavailable at startup
  - Size: 220x60 pixels
  - Moves run in a short background thread so the GUI stays responsive

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