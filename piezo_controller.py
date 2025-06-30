"""
Piezo Controller Module for Auto-Focus functionality
-------------------------------------------------
This module handles the control of the Thorlabs Piezo stage and implements
auto-focus functionality for the confocal microscope.
"""

import time
import numpy as np
import clr
from typing import Tuple, List, Optional, Callable
from System import Decimal  # Use .NET's Decimal type

# Add Thorlabs.Kinesis references
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.DeviceManagerCLI.dll")
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.GenericPiezoCLI.dll")
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\ThorLabs.MotionControl.Benchtop.PrecisionPiezoCLI.dll")

from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI
from Thorlabs.MotionControl.GenericPiezoCLI import Piezo
from Thorlabs.MotionControl.Benchtop.PrecisionPiezoCLI import BenchtopPrecisionPiezo

class PiezoController:
    def __init__(self, serial_no: str = "44506104"):
        """Initialize the Piezo Controller.
        
        Args:
            serial_no (str): Serial number of the piezo device
        """
        self.serial_no = serial_no
        self.device = None
        self.channel = None
        self._is_connected = False

    def connect(self) -> bool:
        """Connect to the piezo device.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            DeviceManagerCLI.BuildDeviceList()
            self.device = BenchtopPrecisionPiezo.CreateBenchtopPiezo(self.serial_no)
            self.device.Connect(self.serial_no)
            self.channel = self.device.GetChannel(1)
            
            if not self.channel.IsSettingsInitialized():
                self.channel.WaitForSettingsInitialized(10000)
                if not self.channel.IsSettingsInitialized():
                    return False
            
            self.channel.StartPolling(250)
            time.sleep(0.25)
            self.channel.EnableDevice()
            time.sleep(0.25)
            
            self.channel.SetPositionControlMode(Piezo.PiezoControlModeTypes.CloseLoop)
            time.sleep(0.25)
            
            self._is_connected = True
            return True
            
        except Exception as e:
            print(f"Error connecting to piezo: {str(e)}")
            self._is_connected = False
            return False

    def disconnect(self):
        """Disconnect from the piezo device."""
        if self._is_connected and self.channel:
            try:
                self.channel.StopPolling()
                self.device.Disconnect()
                self._is_connected = False
            except Exception as e:
                print(f"Error disconnecting from piezo: {str(e)}")

    def get_max_travel(self) -> float:
        """Get the maximum travel range of the piezo.
        
        Returns:
            float: Maximum travel range in micrometers
        """
        if self._is_connected and self.channel:
            # Convert .NET Decimal to float using string conversion
            max_travel = self.channel.GetMaxTravel()
            return float(str(max_travel))
        return 0.0

    def set_position(self, position: float) -> bool:
        """Set the piezo position.
        
        Args:
            position (float): Target position in micrometers
            
        Returns:
            bool: True if successful, False otherwise
        """
        if self._is_connected and self.channel:
            try:
                # Convert float to .NET Decimal using string conversion
                decimal_pos = Decimal.Parse(str(position))
                self.channel.SetPosition(decimal_pos)
                return True
            except Exception as e:
                print(f"Error setting position: {str(e)}")
        return False

    def perform_auto_focus(self, 
                         counter_function: Callable[[], int],
                         step_size: float = 5.0,
                         settling_time: float = 0.1
                         ) -> Tuple[List[float], List[int], float]:
        """Perform auto-focus by scanning the Z axis and measuring counts.
        
        Args:
            counter_function: Function that returns the current count value
            step_size: Step size for Z scanning in µm
            settling_time: Time to wait after each movement in seconds
            
        Returns:
            Tuple containing:
            - List of positions scanned
            - List of counts measured
            - Optimal position found
        """
        if not self._is_connected:
            raise RuntimeError("Piezo not connected")

        max_pos = self.get_max_travel()  # Returns float
        positions = []
        counts = []
        current_pos = 0.0

        # Generate position list
        while current_pos <= max_pos:
            positions.append(current_pos)
            current_pos += step_size

        # Perform Z sweep
        for pos in positions:
            self.set_position(pos)  # set_position handles conversion to System.Decimal
            time.sleep(settling_time)
            count = counter_function()
            counts.append(count)
            print(f'Position: {pos}, counts: {count}')

        # Find optimal position
        optimal_idx = np.argmax(counts)
        optimal_pos = positions[optimal_idx]

        # Move to optimal position
        self.set_position(optimal_pos)
        time.sleep(settling_time)

        return positions, counts, optimal_pos

def simulate_auto_focus() -> Tuple[List[float], List[int], float]:
    """Simulate auto-focus for testing purposes.
    
    Returns:
        Tuple containing:
        - List of positions scanned
        - List of counts measured
        - Optimal position found
    """
    max_pos = 100.0
    step_size = 5.0
    positions = np.arange(0, max_pos + step_size, step_size)
    
    # Simulate a Gaussian distribution of counts
    center = np.random.uniform(30, 70)
    width = 15.0
    noise_level = 200
    peak_height = 1000
    
    counts = noise_level + peak_height * np.exp(-((positions - center) ** 2) / (2 * width ** 2))
    counts = counts + np.random.normal(0, noise_level * 0.1, len(positions))
    counts = counts.astype(int)
    
    # Simulate scanning process
    for i, pos in enumerate(positions):
        time.sleep(0.05)
        print(f'Position: {pos}, counts: {counts[i]}')
    
    optimal_pos = positions[np.argmax(counts)]
    
    return positions.tolist(), counts.tolist(), optimal_pos 