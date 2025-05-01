import time
import numpy as np
import nidaqmx
from nidaqmx.constants import (TerminalConfiguration, Edge, CountDirection)
import pyvisa
import csv


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
        
        # PM400 setup
        self.pm400 = None  # Placeholder for PyVISA resource


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
        
    def read_voltages_2(self):
        with nidaqmx.Task() as ai_task:
            ai_task.ai_channels.add_ai_voltage_chan(self.yout_voltage, terminal_config=TerminalConfiguration.RSE)
            voltage = ai_task.read(number_of_samples_per_channel=1)
            return voltage

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
    

    # def scan_pattern(self, x_points, y_points, dwell_time=0.01):
    #     scan_data = {'x': [], 'y': [], 'x_act': [], 'y_act': [], 'counts': []}
    #     for y in y_points:
    #         for x in x_points:
    #             self.set_voltages(x, y)
    #             time.sleep(dwell_time)
    #             x_act, y_act = self.read_voltages()
    #             counts = self.read_spd_count(dwell_time)
    #             scan_data['x'].append(x)
    #             scan_data['y'].append(y)
    #             scan_data['x_act'].append(x_act)
    #             scan_data['y_act'].append(y_act)
    #             scan_data['counts'].append(counts)
    #     return scan_data
    
    def save_scan_data(self, scan_data, filename="scan_data.csv"):
        with open(filename, mode='w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['x', 'y', 'counts'])  # Header without x_act and y_act

            for x, y, counts in zip(scan_data['x'], scan_data['y'], scan_data['counts']):
                writer.writerow([x, y, counts])
        
        
        
    def save_scan_data_2d(self, scan_data, x_points, y_points, filename="scan_data_2d.csv"):
        # Initialize a 2D list for counts data (rows: y, columns: x)
        # Map counts into a 2D array (row-major by y, then x)
        count_matrix = []
        index = 0
        for _ in y_points:
            row = []
            for _ in x_points:
                row.append(scan_data['counts'][index])
                index += 1
            count_matrix.append(row)

        # Write to CSV
        with open(filename, mode='w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            # Write header: empty cell followed by x_points
            writer.writerow(['y \\ x'] + x_points)
            # Write each row: y_value followed by corresponding row of counts
            for y_val, row in zip(y_points, count_matrix):
                writer.writerow([y_val] + row)
    
    def scan_pattern(self, x_points, y_points, dwell_time=0.01):
        scan_data = {'x': [], 'y': [], 'x_act': [], 'y_act': [], 'counts': []}
        
        with nidaqmx.Task() as ao_task, nidaqmx.Task() as ai_task, nidaqmx.Task() as counter_task:
            # AO: set X/Y voltages
            ao_task.ao_channels.add_ao_voltage_chan(self.xin_control)
            ao_task.ao_channels.add_ao_voltage_chan(self.yin_control)

            # AI: read feedback Xout/Yout
            ai_task.ai_channels.add_ai_voltage_chan(self.xout_voltage, terminal_config=TerminalConfiguration.RSE)
            ai_task.ai_channels.add_ai_voltage_chan(self.yout_voltage, terminal_config=TerminalConfiguration.RSE)

            # Counter: SPD counts
            ci = counter_task.ci_channels.add_ci_count_edges_chan(self.spd_counter, edge=Edge.RISING, initial_count=0)
            ci.ci_count_edges_term = self.spd_edge_source
            

            for y in y_points:
                for x in x_points:
                    ao_task.write([x, y])
                    time.sleep(0.01)
                    
                    #x_act, y_act = ai_task.read()
                    counter_task.start()
                    time.sleep(dwell_time)
                    counts = counter_task.read()
                    counter_task.stop()
                    #counter_task.ci_channels[0].initial_count = 0  # Reset count for next step

                    scan_data['x'].append(x)
                    scan_data['y'].append(y)
                    #scan_data['x_act'].append(x_act)
                    #scan_data['y_act'].append(y_act)
                    scan_data['counts'].append(counts)
                    
        self.save_scan_data(scan_data)
        #self.save_scan_data_2d(scan_data, x_points, y_points)
        return scan_data
    
    def scan_pattern_opm(self, x_points, y_points, dwell_time=0.01):
        scan_data = {'x': [], 'y': [], 'x_act': [], 'y_act': [], 'counts': []}
        for y in y_points:
            for x in x_points:
                self.set_voltages(x, y)
                time.sleep(dwell_time)
                x_act, y_act = self.read_voltages()
                counts = self.read_power(dwell_time)
                scan_data['x'].append(x)
                scan_data['y'].append(y)
                scan_data['x_act'].append(x_act)
                scan_data['y_act'].append(y_act)
                scan_data['counts'].append(counts)
        return scan_data
    
    def scan_pattern_pd(self, x_points, y_points, dwell_time=0.01):
        scan_data = {'x': [], 'y': [], 'counts': []}
        
        with nidaqmx.Task() as ao_task, nidaqmx.Task() as ai_task:
            ao_task.ao_channels.add_ao_voltage_chan(self.xin_control)
            ao_task.ao_channels.add_ao_voltage_chan(self.yin_control)

            ai_task.ai_channels.add_ai_voltage_chan(self.yout_voltage, terminal_config=TerminalConfiguration.RSE)

            for y in y_points:
                for x in x_points:
                    ao_task.write([x, y])
                    time.sleep(dwell_time)
                    voltage = ai_task.read()
                    scan_data['x'].append(x)
                    scan_data['y'].append(y)
                    scan_data['counts'].append(voltage)
                    
        return scan_data

    
    def scan_single_axis(self, axis='x', start=-5.0, end=5.0, points=20, 
                        fixed_voltage=0.0, dwell_time=1):
        
        voltages = np.linspace(start, end, points)
        
        for v in voltages:
            if axis.lower() == 'x':
                self.set_voltages(v, fixed_voltage)
            else:
                self.set_voltages(fixed_voltage, v)
                    
            time.sleep(dwell_time)
                    
        return 
    
    def connect_pm400(self, visa_address=None):
        """Initialize connection to Thorlabs PM400 power meter."""
        rm = pyvisa.ResourceManager()
        self.pm400 = rm.open_resource(visa_address)
        print(f"Connected to PM400: {self.pm400.query('*IDN?')}")

    def read_power(self, wavelength=None, unit='mW'):
        """
        Read optical power from PM400.
        
        Args:
            wavelength (float): Optional - Set wavelength in nm (e.g., 1550.0).
            unit (str): 'mW', 'W', or 'dBm'.
        
        Returns:
            float: Power in specified unit.
        """
        if self.pm400 is None:
            self.connect_pm400('USB0::0x1313::0x8075::P5006633::INSTR')  # Auto-connect if not already done

        if wavelength is not None:
            self.pm400.write(f"SENS:CORR:WAV {wavelength}")  # Set wavelength

        power_w = float(self.pm400.query("MEAS:POW?"))  # Default in Watts

        # Convert units
        if unit.lower() == 'mw':
            return power_w * 1e3
        elif unit.lower() == 'dbm':
            return 10 * np.log10(power_w * 1e3)  # 1 mW reference
        else:
            return power_w


    def close(self):
        self.set_voltages(0, 0)
        
    def set(self, x=0, y=0):
        self.set_voltages(x, y)
        print(f"Scanner safely set to ({x},{y})")