import time
import numpy as np
import nidaqmx
from nidaqmx.constants import (TerminalConfiguration, Edge, CountDirection)

class GalvoScannerController:
    def __init__(self):
        self.spd_counter = "Dev1/ctr0"
        self.spd_edge_source = "/Dev1/PFI8"
        self.xin_control = "Dev1/ao0"
        self.yin_control = "Dev1/ao1"
        self.xout_voltage = "Dev1/ai14"
        self.yout_voltage = "Dev1/ai15"
        self.control_range = (-10.0, 10.0)
        self.output_range = (-3.75, 3.75)
        self.x_calibration = 1.0
        self.y_calibration = 1.0

    def set_voltages(self, x_voltage, y_voltage):
        x_voltage = np.clip(x_voltage, *self.control_range)
        y_voltage = np.clip(y_voltage, *self.control_range)
        with nidaqmx.Task() as ao_task:
            ao_task.ao_channels.add_ao_voltage_chan(self.xin_control)
            ao_task.ao_channels.add_ao_voltage_chan(self.yin_control)
            ao_task.write([x_voltage, y_voltage], auto_start=True)

    def read_voltages(self):
        with nidaqmx.Task() as ai_task:
            ai_task.ai_channels.add_ai_voltage_chan(self.xout_voltage, terminal_config=TerminalConfiguration.RSE)
            ai_task.ai_channels.add_ai_voltage_chan(self.yout_voltage, terminal_config=TerminalConfiguration.RSE)
            voltages = ai_task.read()
            return voltages[0], voltages[1]

    def read_spd_count(self, sampling_time=0.1):
        with nidaqmx.Task() as counter_task:
            counter_task.ci_channels.add_ci_count_edges_chan(
                self.spd_counter, edge=Edge.RISING, initial_count=0
            )
            counter_task.ci_channels[0].ci_count_edges_term = self.spd_edge_source
            counter_task.start()
            time.sleep(sampling_time)
            count = counter_task.read()
            counter_task.stop()
        return count

    def scan_pattern(self, x_points, y_points, dwell_time=0.01):
        scan_data = {'x': [], 'y': [], 'x_act': [], 'y_act': [], 'counts': []}
        for y in y_points:
            for x in x_points:
                self.set_voltages(x, y)
                time.sleep(dwell_time)
                x_act, y_act = self.read_voltages()
                counts = self.read_spd_count(dwell_time)
                scan_data['x'].append(x)
                scan_data['y'].append(y)
                scan_data['x_act'].append(x_act)
                scan_data['y_act'].append(y_act)
                scan_data['counts'].append(counts)
        return scan_data

    def close(self):
        self.set_voltages(0, 0)