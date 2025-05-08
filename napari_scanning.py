import numpy as np
import napari
import time
import json
import nidaqmx
from nidaqmx.constants import (TerminalConfiguration, Edge, CountDirection, AcquisitionType, SampleTimingType)
from nidaqmx.errors import DaqNotFoundError, DaqError
from galvo_controller import GalvoScannerController
import threading

config = json.load(open("config_template.json"))
galvo_controller = GalvoScannerController()

x_range = config['scan_range']['x']
y_range = config['scan_range']['y']
x_res = config['resolution']['x']
y_res = config['resolution']['y']

x_points = np.linspace(x_range[0], x_range[1], x_res)
y_points = np.linspace(y_range[0], y_range[1], y_res)       

# Tamaño de la imagen inicial
width, height = x_res, y_res
image = np.zeros((height, width), dtype=np.float32)

# Crear el visor
viewer = napari.Viewer()
layer = viewer.add_image(image, name="escaneo en vivo", colormap="viridis")

def scan_pattern(x_points, y_points):
    global image, layer

    height, width = len(y_points), len(x_points)
    image = np.zeros((height, width), dtype=np.float32)
    layer.data = image  # <-- CAMBIO: actualiza la capa con nueva imagen vacía

    with nidaqmx.Task() as ao_task, nidaqmx.Task() as counter_task:
        ao_task.ao_channels.add_ao_voltage_chan(galvo_controller.xin_control)
        ao_task.ao_channels.add_ao_voltage_chan(galvo_controller.yin_control)

        counter_task.ci_channels.add_ci_count_edges_chan(
            galvo_controller.spd_counter,
            edge=Edge.RISING,
            initial_count=0
        )
        counter_task.ci_channels[0].ci_count_edges_term = galvo_controller.spd_edge_source

        for y_idx, y in enumerate(y_points):
            for x_idx, x in enumerate(x_points):
                ao_task.write([x, y])
                time.sleep(0.001)

                counter_task.start()
                time.sleep(config['dwell_time'])
                counts = counter_task.read()
                counter_task.stop()

                counts_per_second = counts / config['dwell_time']
                image[y_idx, x_idx] = counts_per_second
                layer.refresh()

# Primer escaneo (completo)
threading.Thread(target=lambda: scan_pattern(x_points, y_points), daemon=True).start()

# Capa de selección
shapes = viewer.add_shapes(name="zoom area", shape_type="rectangle", edge_color='red', face_color='transparent')

@shapes.events.data.connect
def on_shape_added(event):
    if len(shapes.data) > 0:
        rect = shapes.data[-1]
        min_y, min_x = np.floor(np.min(rect, axis=0)).astype(int)
        max_y, max_x = np.ceil(np.max(rect, axis=0)).astype(int)
        print(f"Seleccionado: X={min_x}:{max_x}, Y={min_y}:{max_y}")

        # Limita los índices al tamaño original
        min_x = max(0, min_x)
        max_x = min(width, max_x)
        min_y = max(0, min_y)
        max_y = min(height, max_y)

        # Calcula las nuevas coordenadas físicas (voltajes)
        x_zoom_range = np.linspace(x_points[min_x], x_points[max_x-1], max_x - min_x)
        y_zoom_range = np.linspace(y_points[min_y], y_points[max_y-1], max_y - min_y)

        # Inicia nuevo escaneo con la zona seleccionada
        threading.Thread(target=lambda: scan_pattern(x_zoom_range, y_zoom_range), daemon=True).start()

napari.run() 