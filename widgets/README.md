# Widgets Package for Napari Scanning SPD

This package contains all the GUI widgets extracted from the main `napari_scanning_SPD.py` file, organized into logical modules for better maintainability and reusability.

## Module Structure

```
widgets/
├── __init__.py              # Package initialization and exports
├── scan_controls.py         # Scan control widgets (new scan, reset zoom, etc.)
├── camera_controls.py       # Camera control widgets and threads
├── auto_focus.py           # Auto-focus functionality and signal bridge
├── single_axis_scan.py     # Single axis scan widget
├── file_operations.py      # File loading/saving widgets
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
    update_scan_parameters
)

from widgets.camera_controls import (
    camera_live,
    capture_shot,
    CameraControlWidget
)

from widgets.auto_focus import (
    auto_focus,
    SignalBridge
)

from widgets.single_axis_scan import SingleAxisScanWidget
from widgets.file_operations import load_scan
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
original_x_points = np.linspace(-1, 1, 10)
original_y_points = np.linspace(-1, 1, 10)
shapes_layer = viewer.layers['shapes']

# Create widget
new_scan_widget = new_scan(scan_pattern_func, original_x_points, original_y_points, shapes_layer)

# Add to viewer
viewer.window.add_dock_widget(new_scan_widget, area="bottom")
```

### State Management Classes

The refactored code includes helper classes for managing application state:

```python
class ConfigManager:
    """Manages configuration loading, saving, and updates"""
    def __init__(self, config_file="config_template.json")
    def get_config(self)
    def update_scan_parameters(self, **kwargs)

class ScanPointsManager:
    """Manages scan point generation and updates"""
    def __init__(self, config_manager)
    def update_points(self, **kwargs)
    def get_points(self)

class ZoomLevelManager:
    """Manages zoom level state"""
    def __init__(self, max_zoom=3)
    def get_zoom_level(self)
    def set_zoom_level(self, level)
```

## Widget Reference

### Scan Controls (`scan_controls.py`)

- **`new_scan(scan_pattern_func, original_x_points, original_y_points, shapes)`**
  - Creates a "New Scan" button widget
  - Runs scan in background thread
  
- **`close_scanner(output_task)`**
  - Creates a "Set to Zero" button widget
  - Moves galvo scanner to zero position
  
- **`save_image(viewer, data_path_func)`**
  - Creates a "Save Image" button widget
  - Screenshots current napari view
  
- **`reset_zoom(...)`**
  - Creates a "Reset Zoom" button widget
  - Returns to original scan range
  
- **`update_scan_parameters(config_manager, scan_points_manager)`**
  - Creates scan parameter control widget
  - Float/Int spinboxes for scan range and resolution

### Camera Controls (`camera_controls.py`)

- **`camera_live(viewer)`**
  - Creates a "Camera Live" toggle button
  - Starts/stops live camera feed
  
- **`capture_shot(viewer)`**
  - Creates a "Single Shot" button
  - Captures single camera image
  
- **`CameraControlWidget(camera_live_widget, capture_shot_widget)`**
  - Composite widget with camera controls and sliders
  - Exposure and gain control sliders
  
- **`CameraUpdateThread(camera)`**
  - Background thread for camera updates
  - Emits frames via Qt signals

### Auto Focus (`auto_focus.py`)

- **`auto_focus(counter, binwidth, signal_bridge)`**
  - Creates "Auto Focus" button widget
  - Performs Z-scan optimization
  
- **`SignalBridge(viewer)`**
  - Thread-safe bridge for GUI updates
  - Handles focus plot creation and updates
  
- **`create_focus_plot_widget(positions, counts)`**
  - Creates plot widget for focus results
  - Uses SingleAxisPlot from plot_widgets

### Single Axis Scan (`single_axis_scan.py`)

- **`SingleAxisScanWidget(config_manager, layer, output_task, counter, binwidth)`**
  - Complete widget for X/Y axis scanning
  - Includes scan buttons and result plot
  - Tracks current scanner position internally

### File Operations (`file_operations.py`)

- **`load_scan(viewer)`**
  - Creates "Load Scan" button widget
  - Opens file dialog for .npz files
  - Adds loaded scan as new layer

## Migration from Original Code

To migrate from the original monolithic file:

1. **Replace direct widget usage** with factory function calls
2. **Create state management classes** instead of global variables
3. **Pass dependencies explicitly** to widget factories
4. **Import widgets** from the widgets package

### Before (Original)
```python
@magicgui(call_button="🔬 New Scan")
def new_scan():
    global original_x_points, original_y_points
    # ... implementation
```

### After (Refactored)
```python
from widgets.scan_controls import new_scan as create_new_scan

# Create widget with explicit dependencies
new_scan_widget = create_new_scan(scan_pattern, original_x_points, original_y_points, shapes)
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
    x_points = np.array([1, 2, 3])
    y_points = np.array([4, 5, 6])
    shapes = Mock()
    
    # Create widget
    widget = new_scan(scan_func, x_points, y_points, shapes)
    
    # Test widget properties
    assert widget.call_button.text == "🔬 New Scan"
```

This structure provides a solid foundation for building complex scientific applications with maintainable and testable code. 