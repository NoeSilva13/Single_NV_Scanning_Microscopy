import os
import time
import ctypes
from ctypes import cdll, c_int, c_float, c_char_p, byref

# Load the Thorlabs Kinesis DLLs
try:
    # Modify these paths according to your Kinesis installation
    kinesis_path = r"C:\Program Files\Thorlabs\Kinesis"
    os.environ['PATH'] = kinesis_path + ";" + os.environ['PATH']
    
    # Load the required DLLs
    lib = cdll.LoadLibrary("Thorlabs.MotionControl.Piezo.dll")
except Exception as e:
    print(f"Error loading Thorlabs Kinesis DLLs: {e}")
    raise

class PFM450E_Controller:
    def __init__(self, serial_number):
        """
        Initialize the PFM450E Piezo Objective Scanner controller.
        
        Args:
            serial_number (str): The serial number of the device (found on the rear panel)
        """
        self.serial_number = c_char_p(serial_number.encode('ascii'))
        self._initialize_device()
        
    def _initialize_device(self):
        """Initialize communication with the device."""
        # Build device list (required before communication)
        if lib.TLI_BuildDeviceList() == 0:
            print("Device list built successfully")
        else:
            raise Exception("Failed to build device list")
        
        # Open the device
        if lib.PCC_Open(self.serial_number) == 0:
            print(f"Device {self.serial_number.value.decode()} opened successfully")
        else:
            raise Exception(f"Failed to open device {self.serial_number.value.decode()}")
        
        # Start polling loop (250ms interval)
        lib.PCC_StartPolling(self.serial_number, c_int(250))
        
        # Wait for settings to initialize
        time.sleep(0.5)
        
        # Enable the channel (if not already enabled)
        lib.PCC_EnableChannel(self.serial_number)
        
        # Get device information
        self._get_device_info()
    
    def _get_device_info(self):
        """Get and print device information."""
        model = ctypes.create_string_buffer(256)
        lib.PCC_GetModel(self.serial_number, model)
        print(f"Model: {model.value.decode()}")
        
        version = ctypes.create_string_buffer(256)
        lib.TLI_GetDeviceInfo(self.serial_number, version)
        print(f"Version: {version.value.decode()}")
        
        min_voltage = c_float()
        max_voltage = c_float()
        lib.PCC_GetOutputVoltageRange(self.serial_number, byref(min_voltage), byref(max_voltage))
        print(f"Voltage range: {min_voltage.value}V to {max_voltage.value}V")
    
    def set_position(self, position, channel=1):
        """
        Set the position of the piezo scanner.
        
        Args:
            position (float): Position in microns (0-450 for PFM450E)
            channel (int): Channel number (default 1)
        """
        position_mm = c_float(position / 1000.0)  # Convert microns to mm
        lib.PCC_SetPosition(self.serial_number, c_int(channel), position_mm)
    
    def get_position(self, channel=1):
        """
        Get the current position of the piezo scanner.
        
        Args:
            channel (int): Channel number (default 1)
            
        Returns:
            float: Position in microns
        """
        position_mm = c_float()
        lib.PCC_GetPosition(self.serial_number, c_int(channel), byref(position_mm))
        return position_mm.value * 1000.0  # Convert mm to microns
    
    def set_output_voltage(self, voltage, channel=1):
        """
        Set the output voltage directly.
        
        Args:
            voltage (float): Voltage in volts (check your device's range)
            channel (int): Channel number (default 1)
        """
        lib.PCC_SetOutputVoltage(self.serial_number, c_int(channel), c_float(voltage))
    
    def get_output_voltage(self, channel=1):
        """
        Get the current output voltage.
        
        Args:
            channel (int): Channel number (default 1)
            
        Returns:
            float: Voltage in volts
        """
        voltage = c_float()
        lib.PCC_GetOutputVoltage(self.serial_number, c_int(channel), byref(voltage))
        return voltage.value
    
    def close(self):
        """Close communication with the device."""
        lib.PCC_StopPolling(self.serial_number)
        lib.PCC_Close(self.serial_number)
        print(f"Device {self.serial_number.value.decode()} closed")

# Example usage
if __name__ == "__main__":
    # Replace with your device's serial number
    DEVICE_SERIAL = "12345678"  # Example serial number
    
    try:
        # Initialize the controller
        controller = PFM450E_Controller(DEVICE_SERIAL)
        
        # Move to 100 microns
        print("Moving to 100 microns...")
        controller.set_position(100)
        time.sleep(1)  # Wait for movement to complete
        print(f"Current position: {controller.get_position()} microns")
        
        # Move to 200 microns
        print("Moving to 200 microns...")
        controller.set_position(200)
        time.sleep(1)
        print(f"Current position: {controller.get_position()} microns")
        
        # Set voltage directly (example)
        print("Setting voltage to 50V...")
        controller.set_output_voltage(50)
        time.sleep(1)
        print(f"Current voltage: {controller.get_output_voltage()}V")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Ensure device is properly closed
        if 'controller' in locals():
            controller.close()