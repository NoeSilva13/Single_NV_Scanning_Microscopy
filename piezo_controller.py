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
from utils import PIEZO_COARSE_STEP, PIEZO_FINE_STEP, PIEZO_FINE_RANGE

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
                         step_size: float = PIEZO_COARSE_STEP,
                         settling_time: float = 0.1,
                         fine_tune: bool = True,
                         fine_step_size: float = PIEZO_FINE_STEP,
                         fine_range: float = PIEZO_FINE_RANGE,
                         progress_callback: Optional[Callable[[int, int, str, float, int], None]] = None
                         ) -> Tuple[List[float], List[int], float]:
        """Perform auto-focus by scanning the Z axis and measuring counts.
        
        Args:
            counter_function: Function that returns the current count value
            step_size: Step size for Z scanning in µm (default: PIEZO_COARSE_STEP)
            settling_time: Time to wait after each movement in seconds
            fine_tune: Whether to perform fine-tuning after coarse scan
            fine_step_size: Step size for fine-tuning scan in µm (default: PIEZO_FINE_STEP)
            fine_range: Range around peak to scan during fine-tuning in µm (default: PIEZO_FINE_RANGE)
            progress_callback: Optional callback function for progress updates
                             Signature: callback(current_step, total_steps, stage, position, counts)
            
        Returns:
            Tuple containing:
            - List of positions scanned (including fine-tuning if enabled)
            - List of counts measured (including fine-tuning if enabled)
            - Optimal position found
        """
        if not self._is_connected:
            raise RuntimeError("Piezo not connected")

        max_pos = self.get_max_travel()  # Returns float
        positions = []
        counts = []
        current_pos = 0.0

        print("Starting coarse auto-focus scan...")
        
        # Generate position list for coarse scan
        while current_pos <= max_pos:
            positions.append(current_pos)
            current_pos += step_size

        # Calculate total steps for progress tracking
        total_coarse_steps = len(positions)
        total_fine_steps = 0
        if fine_tune:
            # Estimate fine steps
            fine_start = max(0.0, 0.0 - fine_range/2)  # Rough estimate
            fine_end = min(max_pos, 0.0 + fine_range/2)
            total_fine_steps = int((fine_end - fine_start) / fine_step_size) + 1
        
        total_steps = total_coarse_steps + total_fine_steps
        current_step = 0

        # Perform coarse Z sweep
        for i, pos in enumerate(positions):
            self.set_position(pos)  # set_position handles conversion to System.Decimal
            time.sleep(settling_time)
            count = counter_function()
            counts.append(count)
            current_step += 1
            
            if progress_callback:
                progress_callback(current_step, total_steps, "Coarse Scan", pos, count)
            
            print(f'Coarse scan - Position: {pos:.1f} µm, counts: {count}')

        # Find optimal position from coarse scan
        optimal_idx = np.argmax(counts)
        coarse_optimal_pos = positions[optimal_idx]
        print(f"Coarse scan complete. Peak found at {coarse_optimal_pos:.1f} µm")

        if fine_tune:
            print("Starting fine-tuning scan...")
            
            # Define fine scan range around the coarse optimal position
            fine_start = max(0.0, coarse_optimal_pos - fine_range/2)
            fine_end = min(max_pos, coarse_optimal_pos + fine_range/2)
            
            # Generate fine position list
            fine_positions = []
            fine_counts = []
            current_fine_pos = fine_start
            
            while current_fine_pos <= fine_end:
                fine_positions.append(current_fine_pos)
                current_fine_pos += fine_step_size
            
            # Update total steps with actual fine steps
            total_fine_steps = len(fine_positions)
            total_steps = total_coarse_steps + total_fine_steps
            
            # Perform fine Z sweep
            for i, pos in enumerate(fine_positions):
                self.set_position(pos)
                time.sleep(settling_time)
                count = counter_function()
                fine_counts.append(count)
                current_step = total_coarse_steps + i + 1
                
                if progress_callback:
                    progress_callback(current_step, total_steps, "Fine Scan", pos, count)
                
                print(f'Fine scan - Position: {pos:.2f} µm, counts: {count}')
            
            # Find optimal position from fine scan
            fine_optimal_idx = np.argmax(fine_counts)
            optimal_pos = fine_positions[fine_optimal_idx]
            
            # Combine coarse and fine scan results for return
            all_positions = positions + fine_positions
            all_counts = counts + fine_counts
            
            print(f"Fine scan complete. Refined peak found at {optimal_pos:.2f} µm")
        else:
            optimal_pos = coarse_optimal_pos
            all_positions = positions
            all_counts = counts

        # Move to final optimal position
        self.set_position(optimal_pos)
        time.sleep(settling_time)
        
        if progress_callback:
            progress_callback(total_steps, total_steps, "Complete", optimal_pos, max(all_counts))
        
        print(f"Auto-focus complete. Final position: {optimal_pos:.2f} µm")

        return all_positions, all_counts, optimal_pos

