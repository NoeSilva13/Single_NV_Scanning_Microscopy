import sys
import time
import numpy as np
import napari
import nidaqmx
from nidaqmx.constants import TerminalConfiguration, Edge
from magicgui import magicgui
from magicgui.widgets import create_widget
from qtpy.QtWidgets import QComboBox, QVBoxLayout
from TimeTagger import createTimeTagger, Countrate
from galvo_controller import GalvoScannerController
from data_manager import DataManager
from live_plot_napari_widget import LivePlotNapariWidget

# Initialize controller and data manager
galvo_controller = GalvoScannerController()
data_manager = DataManager()

# Configuration
config = {
    "scan_range": {
        "x": [-1.0, 1.0],
        "y": [-1.0, 1.0]
    },
    "resolution": {
        "x": 12,
        "y": 12
    },
    "dwell_time": 0.1,
    "acquisition_mode": "daq_counter"  # Default mode
}

def create_acquisition_selector():
    """Create a widget for selecting acquisition mode."""
    modes = ['DAQ Counter', 'DAQ Voltage', 'TimeTagger']
    mode_selector = QComboBox()
    mode_selector.addItems(modes)
    mode_selector.currentTextChanged.connect(lambda text: config.update({"acquisition_mode": text.lower().replace(' ', '_')}))
    return mode_selector

def get_signal_function():
    """Return the appropriate signal measurement function based on selected mode."""
    mode = config["acquisition_mode"]
    
    if mode == "daq_counter":
        def measure_function():
            with nidaqmx.Task() as counter_task:
                counter_task.ci_channels.add_ci_count_edges_chan(
                    galvo_controller.spd_counter,
                    edge=Edge.RISING
                )
                counter_task.start()
                time.sleep(config["dwell_time"])
                counts = counter_task.read()
                counter_task.stop()
                return counts / config["dwell_time"]
        return measure_function
    
    elif mode == "daq_voltage":
        def measure_function():
            with nidaqmx.Task() as monitor_task:
                monitor_task.ai_channels.add_ai_voltage_chan(galvo_controller.xout_voltage)
                return monitor_task.read()
        return measure_function
    
    elif mode == "timetagger":
        tagger = createTimeTagger()
        counter = Countrate(tagger, [1])
        def measure_function():
            return counter.getData()
        return measure_function
    
    return None

def scan_pattern(x_points, y_points):
    """Unified scan pattern function that works with all acquisition modes."""
    global image, layer, data_path
    
    height, width = len(y_points), len(x_points)
    image = np.zeros((height, width), dtype=np.float32)
    layer.data = image  # update layer
    layer.contrast_limits = contrast_limits
    
    with nidaqmx.Task() as ao_task:
        ao_task.ao_channels.add_ao_voltage_chan(galvo_controller.xin_control)
        ao_task.ao_channels.add_ao_voltage_chan(galvo_controller.yin_control)
        
        for y_idx, y in enumerate(y_points):
            for x_idx, x in enumerate(x_points):
                ao_task.write([x, y])
                time.sleep(config["dwell_time"])
                
                # Get measurement based on selected mode
                signal_value = get_signal_function()()
                image[y_idx, x_idx] = signal_value
                layer.data = image
    
    layer.contrast_limits = (np.min(image), np.max(image))
    data_path = data_manager.save_scan_data(image)
    return x_points, y_points

# Create Napari viewer
viewer = napari.Viewer()

# Create widgets
contrast_limits = (0, 10000)
layer = viewer.add_image(np.zeros((1, 1)), name="live scan", 
                         colormap="viridis", scale=(1, 1), 
                         contrast_limits=contrast_limits)
shapes = viewer.add_shapes(name="zoom area", shape_type="rectangle", 
                           edge_color='red', face_color='transparent', 
                           edge_width=0)

# Create acquisition mode selector
mode_selector = create_acquisition_selector()

# Create live plot widget
mpl_widget = LivePlotNapariWidget(
    measure_function=get_signal_function(),
    histogram_range=100,
    dt=0.1  # Update every 100ms
)

# Add widgets to viewer
viewer.window.add_dock_widget(mode_selector, area='top', name='Acquisition Mode')
viewer.window.add_dock_widget(mpl_widget, area='right', name='Signal Plot')

# Add scan button
@magicgui(call_button="Start Scan")
def scan():
    x_range = config["scan_range"]["x"]
    y_range = config["scan_range"]["y"]
    x_points = np.linspace(x_range[0], x_range[1], config["resolution"]["x"])
    y_points = np.linspace(y_range[0], y_range[1], config["resolution"]["y"])
    scan_pattern(x_points, y_points)

viewer.window.add_dock_widget(scan, area='bottom', name='Scan Controls')

# Run Napari
if __name__ == "__main__":
    napari.run()
