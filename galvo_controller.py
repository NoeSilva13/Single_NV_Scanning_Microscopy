import time
import numpy as np
import nidaqmx
from nidaqmx.constants import (TerminalConfiguration, Edge, CountDirection, AcquisitionType, SampleTimingType)
from nidaqmx.errors import DaqNotFoundError, DaqError
import pyvisa
import csv
from typing import Generator, Tuple, Dict, Any

class GalvoScannerController:
    """
    Controller for galvo mirror scanning system with NI DAQ.
    
    Features:
    - Voltage control for X/Y galvo mirrors
    - Position feedback reading
    - SPD photon counting
    - Real-time scanning with visualization
    - Buffered scanning for improved performance
    """
    def __init__(self):
        """Initialize the controller with default DAQ channels and ranges."""
        try:
            # Test DAQ connection
            with nidaqmx.Task() as test_task:
                test_task.ao_channels.add_ao_voltage_chan("Dev1/ao0")
            
            # DAQ channel configuration
            self.spd_counter = "Dev1/ctr0"
            self.spd_edge_source = "/Dev1/PFI8"
            self.xin_control = "Dev1/ao0"
            self.yin_control = "Dev1/ao1"
            self.xout_voltage = "Dev1/ai14"
            self.yout_voltage = "Dev1/ai15"

            # Voltage ranges
            self.control_range = (-10.0, 10.0)      # Output voltage range
            self.output_range = (-3.75, 3.75)       # Input voltage range

            # Calibration factors
            self.x_calibration = 1.0
            self.y_calibration = 1.0
            
            # Scanning parameters
            self.sample_rate = 1000  # Hz
            self.samples_per_point = 10
            self.settling_time = 0.001  # seconds
            
            self.set_voltages(0, 0)
            print("Successfully initialized DAQ connection")
                        
        except DaqNotFoundError:
            raise RuntimeError(
                "NI-DAQmx not found. Please install NI-DAQmx from National Instruments website: "
                "https://www.ni.com/en/support/downloads/drivers/download.ni-daqmx.html"
            )
        except DaqError as e:
            raise RuntimeError(f"Error initializing DAQ: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error during initialization: {str(e)}")

    # --------------------------
    # Basic Control Methods
    # --------------------------

    def set_voltages(self, x_voltage, y_voltage):
        """
        Set X and Y mirror voltages.
        
        Args:
            x_voltage (float): X-axis voltage (-10 to 10V)
            y_voltage (float): Y-axis voltage (-10 to 10V)
        """
        try:
            x_voltage = np.clip(x_voltage, *self.control_range)
            y_voltage = np.clip(y_voltage, *self.control_range)

            with nidaqmx.Task() as ao_task:
                ao_task.ao_channels.add_ao_voltage_chan(self.xin_control)
                ao_task.ao_channels.add_ao_voltage_chan(self.yin_control)
                ao_task.write([x_voltage, y_voltage], auto_start=True)
        except DaqError as e:
            raise RuntimeError(f"Error setting voltages: {str(e)}")

    def read_voltages(self):
        """
        Read actual mirror positions from feedback signals.
        
        Returns:
            tuple: (x_voltage, y_voltage) in volts
        """
        with nidaqmx.Task() as ai_task:
            ai_task.ai_channels.add_ai_voltage_chan(self.xout_voltage, terminal_config=TerminalConfiguration.RSE)
            ai_task.ai_channels.add_ai_voltage_chan(self.yout_voltage, terminal_config=TerminalConfiguration.RSE)
            voltages = ai_task.read()
            return voltages[0], voltages[1]

    def read_voltage(self):
        """
        Read voltage
        """
        with nidaqmx.Task() as ai_task:
            ai_task.ai_channels.add_ai_voltage_chan(self.xout_voltage, terminal_config=TerminalConfiguration.RSE)
            voltage = ai_task.read()
            return voltage

    def read_spd_count(self, sampling_time=0.1):
        """
        Read photon counts from SPD.
        
        Args:
            sampling_time (float): Time to count photons in seconds
            
        Returns:
            int: Number of counts during sampling period
        """
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
    
    # --------------------------
    # Scanning Methods
    # --------------------------

    def generate_scan_points(self, x_points: np.ndarray, y_points: np.ndarray) -> Generator[Tuple[int, int, float, float], None, None]:
        """
        Generate scan points for real-time scanning.
        
        Args:
            x_points: Array of X-axis voltage points
            y_points: Array of Y-axis voltage points
            
        Yields:
            Tuple of (x_idx, y_idx, x_voltage, y_voltage)
        """
        for y_idx, y in enumerate(y_points):
            for x_idx, x in enumerate(x_points):
                yield x_idx, y_idx, x, y

    def scan_pattern_realtime(self, x_points: np.ndarray, y_points: np.ndarray, 
                            dwell_time: float = 0.01) -> Generator[Tuple[int, int, float], None, None]:
        """
        Perform a 2D raster scan with real-time data acquisition.
        This generator will continuously yield scan points, allowing for continuous scanning.
        Returns counts per second for each point.
        
        Args:
            x_points: X-axis voltage points
            y_points: Y-axis voltage points
            dwell_time: Time at each point in seconds
            
        Yields:
            Tuple of (x_idx, y_idx, counts_per_second) for real-time visualization
        """
        with nidaqmx.Task() as ao_task, nidaqmx.Task() as counter_task:
            # Configure analog output task
            ao_task.ao_channels.add_ao_voltage_chan(self.xin_control)
            ao_task.ao_channels.add_ao_voltage_chan(self.yin_control)
            
            # Configure counter task for SPD
            counter_task.ci_channels.add_ci_count_edges_chan(
                self.spd_counter,
                edge=Edge.RISING,
                initial_count=0
            )
            counter_task.ci_channels[0].ci_count_edges_term = self.spd_edge_source
            
            while True:  # Continuous scanning loop
                # Perform scan
                for x_idx, y_idx, x, y in self.generate_scan_points(x_points, y_points):
                    # Set mirror position
                    ao_task.write([x, y])
                    time.sleep(self.settling_time)
                    
                    # Count photons
                    counter_task.start()
                    time.sleep(dwell_time)
                    counts = counter_task.read()
                    counter_task.stop()
                    
                    # Calculate counts per second
                    counts_per_second = counts / dwell_time
                    
                    yield x_idx, y_idx, counts_per_second

    def scan_pattern_buffered(self, x_points: np.ndarray, y_points: np.ndarray, 
                            dwell_time: float = 0.01) -> Dict[str, Any]:
        """
        Perform a 2D raster scan using point-by-point scanning.
        Returns counts per second for each point.
        
        Args:
            x_points: X-axis voltage points
            y_points: Y-axis voltage points
            dwell_time: Time at each point in seconds
            
        Returns:
            Dictionary containing scan data with counts per second
        """
        n_x = len(x_points)
        n_y = len(y_points)
        counts_grid = np.zeros((n_y, n_x))  # Initialize with correct shape
        
        with nidaqmx.Task() as ao_task, nidaqmx.Task() as counter_task:
            # Configure analog output task
            ao_task.ao_channels.add_ao_voltage_chan(self.xin_control)
            ao_task.ao_channels.add_ao_voltage_chan(self.yin_control)
            
            # Configure counter task
            counter_task.ci_channels.add_ci_count_edges_chan(
                self.spd_counter,
                edge=Edge.RISING,
                initial_count=0
            )
            counter_task.ci_channels[0].ci_count_edges_term = self.spd_edge_source
            
            # Perform scan point by point
            for y_idx, y in enumerate(y_points):
                for x_idx, x in enumerate(x_points):
                    # Set mirror position
                    ao_task.write([x, y])
                    time.sleep(self.settling_time)
                    
                    # Count photons
                    counter_task.start()
                    time.sleep(dwell_time)
                    counts = counter_task.read()
                    counter_task.stop()
                    
                    # Calculate counts per second and store in grid
                    counts_per_second = counts / dwell_time
                    counts_grid[y_idx, x_idx] = counts_per_second
            
            # Return data in the format expected by the visualizer
            return {
                'x': x_points,
                'y': y_points,
                'counts': counts_grid  # This is already a 2D array with shape (n_y, n_x)
            }

    def scan_pattern(self, x_points, y_points, dwell_time=0.01):
        n_x = len(x_points)
        n_y = len(y_points)
        counts_grid = np.zeros((n_y, n_x))  # Initialize with correct shape
        
        with nidaqmx.Task() as ao_task, nidaqmx.Task() as counter_task:
            # Configure analog output task
            ao_task.ao_channels.add_ao_voltage_chan(self.xin_control)
            ao_task.ao_channels.add_ao_voltage_chan(self.yin_control)
            
            # Configure counter task
            counter_task.ci_channels.add_ci_count_edges_chan(
                self.spd_counter,
                edge=Edge.RISING,
                initial_count=0
            )
            counter_task.ci_channels[0].ci_count_edges_term = self.spd_edge_source
            
            # Perform scan point by point
            for y_idx, y in enumerate(y_points):
                for x_idx, x in enumerate(x_points):
                    # Set mirror position
                    ao_task.write([x, y])
                    time.sleep(self.settling_time)
                    
                    # Count photons
                    counter_task.start()
                    time.sleep(dwell_time)
                    counts = counter_task.read()
                    counter_task.stop()
                    
                    # Calculate counts per second and store in grid
                    counts_per_second = counts / dwell_time
                    counts_grid[y_idx, x_idx] = counts_per_second
            
            # Return data in the format expected by the visualizer
            return x_points, y_points, counts_grid

    def scan_pattern_pd(self, x_points, y_points, dwell_time=0.01):
        """
        Perform a 2D raster scan with photodiode voltage readings.
        
        Args:
            x_points (array-like): X-axis voltage points
            y_points (array-like): Y-axis voltage points
            dwell_time (float): Time at each point in seconds
            
        Returns:
            dict: Scan data containing positions and PD voltages
        """
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

    def scan_single_axis(self, axis='x', start=-5.0, end=5.0, points=20, fixed_voltage=0.0, dwell_time=1):
        """
        Perform a 1D scan along either X or Y axis.
        
        Args:
            axis (str): 'x' or 'y' for scan axis
            start (float): Start voltage
            end (float): End voltage
            points (int): Number of points
            fixed_voltage (float): Voltage for fixed axis
            dwell_time (float): Time at each point in seconds
        """
        voltages = np.linspace(start, end, points)
        
        for v in voltages:
            if axis.lower() == 'x':
                self.set_voltages(v, fixed_voltage)
            else:
                self.set_voltages(fixed_voltage, v)
                    
            time.sleep(dwell_time)

    # --------------------------
    # Data Saving Methods
    # --------------------------

    def save_scan_data(self, scan_data, filename="scan_data.csv"):
        """
        Save scan data to CSV file.
        
        Args:
            scan_data (dict): Dictionary containing 'x', 'y', 'counts' arrays
            filename (str): Output filename
        """
        with open(filename, mode='w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['x', 'y', 'counts'])  

            for x, y, counts in zip(scan_data['x'], scan_data['y'], scan_data['counts']):
                writer.writerow([x, y, counts])

    # --------------------------
    # Utility Methods
    # --------------------------
    
    def close(self):
        """Safely close the scanner by setting voltages to zero."""
        try:
            self.set_voltages(0, 0)
        except Exception as e:
            print(f"Warning: Error during shutdown: {str(e)}")
            print("Please ensure the scanner is manually set to a safe position.")
        
    def set(self, x=0, y=0):
        """
        Set scanner to specific position with safety check.
        
        Args:
            x (float): X position voltage
            y (float): Y position voltage
        """
        self.set_voltages(x, y)
        print(f"Scanner safely set to ({x},{y})")