"""
Confocal Single-NV Microscopy Control Software
-------------------------------------------
This software controls a confocal microscope setup for single NV center imaging using:
- Thorlabs LSKGG4 Galvo-Galvo Scanner
- National Instruments USB-6453 DAQ
- Avalanche Photo Diode APD
- Single Photon Detector SPD
- Swabian TimeTagger

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
from TimeTagger import createTimeTagger, Countrate

# --------------------- INITIAL CONFIGURATION ---------------------
# Load scanning parameters from config file
config = json.load(open("config_template.json"))
galvo_controller = GalvoScannerController()  # Initialize galvo scanner control
data_manager = DataManager()  # Initialize data saving system

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

mode = config["acquisition_mode"]
    
if mode == "daq_counter":
    # Initialize DAQ counter task for SPD signal
    counter_task = nidaqmx.Task()
    counter_task.ci_channels.add_ci_count_edges_chan(
        galvo_controller.spd_counter,
        edge=Edge.RISING,
        initial_count=0
    )
    counter_task.ci_channels[0].ci_count_edges_term = galvo_controller.spd_edge_source
    def measure_function():
        counter_task.start()
        time.sleep(config["dwell_time"])
        counts = counter_task.read()
        counter_task.stop()
        return counts / config["dwell_time"]
    
elif mode == "daq_voltage":
    # Initialize DAQ monitoring task for APD signal
    # RSE (Referenced Single-Ended) configuration for voltage reading
    monitor_task = nidaqmx.Task()
    monitor_task.ai_channels.add_ai_voltage_chan(galvo_controller.xout_voltage, terminal_config=TerminalConfiguration.RSE)
    monitor_task.start()
    def measure_function():
        return monitor_task.read()
    
elif mode == "timetagger":
    #Initialize TimeTagger
    tagger = createTimeTagger()
    tagger.reset()
    #Set up counter channel (assuming channel 1 is used for SPD input)
    counter = Countrate(tagger, [1])
    def measure_function():
        return counter.getData()

# Store original parameters for reset functionality
original_scan_params = {
    'x_range': None,
    'y_range': None,
    'x_res': None,
    'y_res': None
}

# --------------------- NAPARI VIEWER SETUP ---------------------
viewer = napari.Viewer(title="BurkeLab Single NV Scanner") # Initialize Napari viewer
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
mpl_widget = live_plot(measure_function=lambda: measure_function(), histogram_range=100, dt=0.1)
viewer.window.add_dock_widget(mpl_widget, area='right', name='Signal Plot')

# ------------------- CONFIGURE ANALOG OUTPUT TASK -------------------
with nidaqmx.Task() as ao_task:
    ao_task.ao_channels.add_ao_voltage_chan(galvo_controller.xin_control)  # X galvo
    ao_task.ao_channels.add_ao_voltage_chan(galvo_controller.yin_control)  # Y galvo

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
    
    # Perform raster scan
    for y_idx, y in enumerate(y_points):
        for x_idx, x in enumerate(x_points):
            ao_task.write([x, y])  # Move galvos to position
            time.sleep(0.001)      # Settling time for galvos
            image[y_idx, x_idx] = measure_function()  # Store in image
            print(image[y_idx, x_idx]) # Print current value
            layer.data = image  # Update display
    
    # Adjust contrast and save data
    layer.contrast_limits = (np.min(image), np.max(image))
    data_path = data_manager.save_scan_data(image)
    return x_points, y_points

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
