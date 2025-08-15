"""
RIGOL DSG836 Signal Generator Controller

This module provides a Python interface to control the RIGOL DSG836 RF signal generator
via Ethernet for ODMR experiments with NV centers.

Author: Javier Noé Ramos Silva
Contact: jramossi@uci.edu
Lab: Burke Lab, Department of Electrical Engineering and Computer Science, University of California, Irvine
Date: 2025
"""

import time
import logging
from typing import Optional, Union
import re

try:
    import pyvisa
    PYVISA_AVAILABLE = True
except ImportError:
    PYVISA_AVAILABLE = False
    pyvisa = None

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RigolDSG836Controller:
    """
    Controller for RIGOL DSG836 RF Signal Generator
    
    This class provides methods to control the RIGOL DSG836 signal generator
    over Ethernet using SCPI commands for ODMR experiments.
    """
    
    def __init__(self, ip_address: str = "192.168.0.224", timeout: float = 10.0):
        """
        Initialize the RIGOL DSG836 controller.
        
        Args:
            ip_address: IP address of the signal generator
            timeout: Connection timeout in seconds
        """
        if not PYVISA_AVAILABLE:
            raise ImportError("PyVISA is required for RIGOL DSG836 control. Install with: pip install pyvisa")
        
        self.ip_address = ip_address
        self.timeout = timeout
        self.resource_string = f"TCPIP0::{ip_address}::inst0::INSTR"
        self.instrument = None
        self.connected = False
        self.rm = None
        
        # Default ODMR parameters
        self.default_frequency = 2.87e9  # 2.87 GHz for NV centers
        self.default_power = -10.0       # -10 dBm
        
    def connect(self) -> bool:
        """
        Connect to the RIGOL DSG836 signal generator using VISA.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            # Initialize VISA resource manager
            self.rm = pyvisa.ResourceManager()
            
            # Connect to instrument
            self.instrument = self.rm.open_resource(self.resource_string)
            self.instrument.timeout = self.timeout * 1000  # Convert to milliseconds
            self.connected = True
            
            logger.info(f"Attempting connection to RIGOL DSG836 at {self.ip_address}")
            
            # Test connection with identification query
            idn = self.instrument.query("*IDN?")
            logger.info(f"Connected to: {idn.strip()}")
            
            if "RIGOL" in idn.upper():
                # Initialize instrument to known state
                self._initialize_instrument()
                return True
            else:
                logger.error(f"Unexpected instrument identification: {idn}")
                self.disconnect()
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to RIGOL DSG836 at {self.resource_string} - {e}")
            self.connected = False
            if self.rm:
                try:
                    self.rm.close()
                except:
                    pass
                self.rm = None
            return False
    
    def disconnect(self):
        """Disconnect from the signal generator."""
        if self.instrument:
            try:
                self.instrument.close()
            except:
                pass
            self.instrument = None
        
        if self.rm:
            try:
                self.rm.close()
            except:
                pass
            self.rm = None
            
        self.connected = False
        logger.info("Disconnected from RIGOL DSG836")
    
    def _initialize_instrument(self):
        """Initialize the instrument to a known state for ODMR experiments."""
        try:
            # Start with basic commands only
            logger.info("Initializing RIGOL DSG836...")
            
            # Turn off RF output initially (safety first)
            self.set_rf_output(False)
            
            # Set default frequency and power
            self.set_frequency(self.default_frequency)
            self.set_power(self.default_power)
            
            logger.info("RIGOL DSG836 initialized for ODMR experiments")
            
        except Exception as e:
            logger.error(f"Failed to initialize RIGOL DSG836: {e}")
            # Don't raise exception during initialization - allow connection to succeed
    
    def write(self, command: str):
        """
        Send a SCPI command to the instrument.
        
        Args:
            command: SCPI command string
        """
        if not self.connected or not self.instrument:
            raise RuntimeError("Not connected to instrument")
        
        try:
            self.instrument.write(command)
            time.sleep(0.01)  # Small delay for command processing
            
        except Exception as e:
            logger.error(f"Failed to send command '{command.strip()}': {e}")
            raise
    
    def query(self, command: str) -> str:
        """
        Send a query command and return the response.
        
        Args:
            command: SCPI query command
            
        Returns:
            str: Response from instrument
        """
        if not self.connected or not self.instrument:
            raise RuntimeError("Not connected to instrument")
        
        try:
            response = self.instrument.query(command)
            return response.strip()
            
        except Exception as e:
            logger.error(f"Failed to query '{command.strip()}': {e}")
            raise
    
    def set_frequency(self, frequency: float):
        """
        Set the RF output frequency.
        
        Args:
            frequency: Frequency in Hz (e.g., 2.87e9 for 2.87 GHz)
        """
        try:
            self.write(f":FREQ {frequency}")
            self._last_frequency = frequency  # Cache the value
            logger.info(f"Set frequency to {frequency/1e9:.6f} GHz")
        except Exception as e:
            logger.error(f"Failed to set frequency: {e}")
            raise
    
    def get_frequency(self) -> float:
        """
        Get the current RF output frequency.
        
        Returns:
            float: Frequency in Hz
        """
        try:
            response = self.query(":FREQ?")
            frequency = float(response)
            return frequency
        except Exception as e:
            logger.warning(f"Failed to get frequency, returning cached value: {e}")
            return getattr(self, '_last_frequency', self.default_frequency)
    
    def set_power(self, power_dbm: float):
        """
        Set the RF output power.
        
        Args:
            power_dbm: Power in dBm
        """
        try:
            self.write(f":POW {power_dbm}")
            self._last_power = power_dbm  # Cache the value
            logger.info(f"Set power to {power_dbm} dBm")
        except Exception as e:
            logger.error(f"Failed to set power: {e}")
            raise
    
    def get_power(self) -> float:
        """
        Get the current RF output power.
        
        Returns:
            float: Power in dBm
        """
        try:
            response = self.query(":POW?")
            power = float(response)
            return power
        except Exception as e:
            logger.warning(f"Failed to get power, returning cached value: {e}")
            return getattr(self, '_last_power', self.default_power)
    
    def set_rf_output(self, enabled: bool):
        """
        Enable or disable RF output.
        
        Args:
            enabled: True to enable RF output, False to disable
        """
        try:
            state = "ON" if enabled else "OFF"
            self.write(f":OUTP {state}")
            self._last_rf_output = enabled  # Cache the value
            logger.info(f"RF output {'enabled' if enabled else 'disabled'}")
        except Exception as e:
            logger.error(f"Failed to set RF output state: {e}")
            raise
    
    def get_rf_output(self) -> bool:
        """
        Get the current RF output state.
        
        Returns:
            bool: True if RF output is enabled, False otherwise
        """
        try:
            response = self.query(":OUTP?")
            return response.strip() == "1" or response.strip().upper() == "ON"
        except Exception as e:
            logger.warning(f"Failed to get RF output state, returning cached value: {e}")
            return getattr(self, '_last_rf_output', False)
    
    def set_odmr_frequency(self, frequency_ghz: float):
        """
        Convenience method to set frequency for ODMR experiments.
        
        Args:
            frequency_ghz: Frequency in GHz (e.g., 2.87 for 2.87 GHz)
        """
        frequency_hz = frequency_ghz * 1e9
        self.set_frequency(frequency_hz)
    
    def set_odmr_power(self, power_dbm: float):
        """
        Convenience method to set power for ODMR experiments.
        
        Args:
            power_dbm: Power in dBm (typically -20 to +10 dBm for ODMR)
        """
        if power_dbm > 20:
            logger.warning(f"Power {power_dbm} dBm is very high for ODMR experiments")
        
        self.set_power(power_dbm)
    
    def prepare_for_odmr(self, frequency_ghz: float = 2.87, power_dbm: float = -10.0):
        """
        Prepare the signal generator for ODMR measurements.
        
        Args:
            frequency_ghz: MW frequency in GHz
            power_dbm: MW power in dBm
        """
        try:
            # Set frequency and power
            self.set_odmr_frequency(frequency_ghz)
            self.set_odmr_power(power_dbm)
            
            # Turn off any modulation
            self.write(":SOUR:PULM:STAT OFF")
            self.write(":SOUR:AM:STAT OFF")
            self.write(":SOUR:FM:STAT OFF")
            
            logger.info(f"RIGOL DSG836 prepared for ODMR: {frequency_ghz} GHz, {power_dbm} dBm")
            
        except Exception as e:
            logger.error(f"Failed to prepare for ODMR: {e}")
            raise
    
    def frequency_sweep_setup(self, start_freq_ghz: float, stop_freq_ghz: float, 
                             num_points: int, power_dbm: float = -10.0):
        """
        Setup for frequency sweep measurements.
        
        Args:
            start_freq_ghz: Start frequency in GHz
            stop_freq_ghz: Stop frequency in GHz
            num_points: Number of frequency points
            power_dbm: MW power in dBm
        """
        try:
            # Set sweep parameters based on your working code
            self.write(f":SWE:STEP:STAR:FREQ {start_freq_ghz}GHz")
            self.write(f":SWE:STEP:STOP:FREQ {stop_freq_ghz}GHz")
            self.write(f":SWE:STEP:DWEL 1")  # Dwell time
            self.write(":SWE:MODE CONT")     # Continuous sweep mode
            self.write(":SWE:TYPE STEP")     # Step sweep
            
            # Set power
            self.set_power(power_dbm)
            
            logger.info(f"Frequency sweep setup: {start_freq_ghz}-{stop_freq_ghz} GHz, {num_points} points")
            
        except Exception as e:
            logger.error(f"Failed to setup frequency sweep: {e}")
            raise
    
    def trigger_sweep_point(self):
        """Trigger the next point in a frequency sweep."""
        try:
            self.write("*TRG")
        except Exception as e:
            logger.error(f"Failed to trigger sweep point: {e}")
            raise
    
    def get_error(self) -> str:
        """
        Query instrument for any errors.
        
        Returns:
            str: Error message or "No error"
        """
        try:
            response = self.query(":SYSTEM:ERROR?")
            return response
        except Exception as e:
            return f"Failed to query error: {e}"
    
    def get_status(self) -> dict:
        """
        Get instrument status information.
        
        Returns:
            dict: Status information
        """
        status = {
            'connected': self.connected,
            'ip_address': self.ip_address,
            'resource_string': self.resource_string
        }
        
        if self.connected:
            try:
                status['frequency_ghz'] = self.get_frequency() / 1e9
                status['power_dbm'] = self.get_power()
                status['rf_output'] = self.get_rf_output()
                status['note'] = "Connected via VISA"
            except Exception as e:
                status['error'] = f"Failed to get status: {e}"
        
        return status
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        # Turn off RF output before disconnecting
        if self.connected:
            try:
                self.set_rf_output(False)
            except:
                pass
        self.disconnect()


# Example usage
if __name__ == "__main__":
    # Test the RIGOL DSG836 controller
    rigol = RigolDSG836Controller("192.168.0.222")
    
    try:
        # Connect to instrument
        if rigol.connect():
            print("Connected successfully!")
            
            # Get status
            status = rigol.get_status()
            print(f"Status: {status}")
            
            # Prepare for ODMR
            rigol.prepare_for_odmr(frequency_ghz=2.87, power_dbm=-15.0)
            
            # Enable RF output
            rigol.set_rf_output(True)
            print("RF output enabled")
            
            # Wait a bit
            time.sleep(2)
            
            # Disable RF output
            rigol.set_rf_output(False)
            print("RF output disabled")
            
    finally:
        rigol.disconnect() 