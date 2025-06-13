"""
Swabian Pulse Streamer 8/2 Controller for ODMR NV Experiments
------------------------------------------------------------
This module provides pulse generation control for ODMR (Optically Detected Magnetic Resonance)
experiments with Nitrogen-Vacancy (NV) centers using the Swabian Pulse Streamer 8/2.

Channel Assignment:
- Channel 0: AOM Laser control
- Channel 1: Microwave (MW) control
- Channel 2: Single Photon Detector (SPD) gate

Author: NV Lab
Date: 2025
"""

import numpy as np
import time
from typing import List, Tuple, Optional, Dict
try:
    from pulsestreamer import PulseStreamer, OutputState, Sequence
    PULSESTREAMER_AVAILABLE = True
except ImportError:
    print("Warning: PulseStreamer library not found. Install with: pip install pulsestreamer")
    PULSESTREAMER_AVAILABLE = False

class SwabianPulseController:
    """
    Controller class for the Swabian Pulse Streamer 8/2 device.
    Manages pulse generation for ODMR experiments with NV centers.
    """
    
    # Channel definitions
    CHANNEL_AOM = 0      # AOM Laser
    CHANNEL_MW = 1       # Microwave
    CHANNEL_SPD = 2      # SPD Gate
    
    def __init__(self, ip_address: str = "192.168.0.201"):
        """
        Initialize the Pulse Streamer controller.
        
        Args:
            ip_address: IP address of the Pulse Streamer device
        """
        self.ip_address = ip_address
        self.pulse_streamer = None
        self.is_connected = False
        
        # Default timing parameters (in nanoseconds)
        self.default_params = {
            'laser_duration': 1000,      # 1 µs laser pulse
            'mw_duration': 100,          # 100 ns MW pulse
            'detection_duration': 500,   # 500 ns detection window
            'laser_delay': 50,           # 50 ns delay before laser
            'mw_delay': 100,             # 100 ns delay before MW
            'detection_delay': 200,      # 200 ns delay before detection
            'sequence_interval': 10000,  # 10 µs between sequences
        }
        
        self.connect()
    
    def connect(self) -> bool:
        """
        Connect to the Pulse Streamer device.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        if not PULSESTREAMER_AVAILABLE:
            print("PulseStreamer library not available")
            return False
            
        try:
            self.pulse_streamer = PulseStreamer(self.ip_address)
            self.is_connected = True
            print(f"✅ Connected to Pulse Streamer at {self.ip_address}")
            
            # Reset device to known state
            self.reset_device()
            return True
            
        except Exception as e:
            print(f"❌ Failed to connect to Pulse Streamer: {e}")
            self.is_connected = False
            return False
    
    def disconnect(self):
        """Disconnect from the Pulse Streamer device."""
        if self.pulse_streamer:
            try:
                self.reset_device()
                self.pulse_streamer = None
                self.is_connected = False
                print("🔌 Disconnected from Pulse Streamer")
            except Exception as e:
                print(f"❌ Error during disconnect: {e}")
    
    def reset_device(self):
        """Reset the Pulse Streamer to a known state."""
        if not self.is_connected:
            return
            
        try:
            # Turn off all channels
            self.pulse_streamer.constant(OutputState.ZERO())
            print("🔄 Pulse Streamer reset to OFF state")
        except Exception as e:
            print(f"❌ Error resetting device: {e}")
    
    def create_odmr_sequence(self, 
                           laser_duration: int = None,
                           mw_duration: int = None,
                           detection_duration: int = None,
                           laser_delay: int = None,
                           mw_delay: int = None,
                           detection_delay: int = None,
                           repetitions: int = 1) -> Optional[Sequence]:
        """
        Create an ODMR pulse sequence.
        
        Args:
            laser_duration: Duration of laser pulse in ns
            mw_duration: Duration of MW pulse in ns
            detection_duration: Duration of detection window in ns
            laser_delay: Delay before laser pulse in ns
            mw_delay: Delay before MW pulse in ns
            detection_delay: Delay before detection in ns
            repetitions: Number of sequence repetitions
            
        Returns:
            Sequence object or None if error
        """
        if not self.is_connected:
            print("❌ Device not connected")
            return None
        
        # Use default parameters if not specified
        params = self.default_params.copy()
        if laser_duration is not None:
            params['laser_duration'] = laser_duration
        if mw_duration is not None:
            params['mw_duration'] = mw_duration
        if detection_duration is not None:
            params['detection_duration'] = detection_duration
        if laser_delay is not None:
            params['laser_delay'] = laser_delay
        if mw_delay is not None:
            params['mw_delay'] = mw_delay
        if detection_delay is not None:
            params['detection_delay'] = detection_delay
        
        try:
            sequence = Sequence()
            
            for rep in range(repetitions):
                # Calculate timing
                total_duration = max(
                    params['laser_delay'] + params['laser_duration'],
                    params['mw_delay'] + params['mw_duration'],
                    params['detection_delay'] + params['detection_duration']
                )
                
                # Add inter-sequence delay if not first repetition
                if rep > 0:
                    sequence.setDigital(self.CHANNEL_AOM, False)
                    sequence.setDigital(self.CHANNEL_MW, False)
                    sequence.setDigital(self.CHANNEL_SPD, False)
                    sequence.wait(params['sequence_interval'])
                
                # Initialize all channels to OFF
                sequence.setDigital(self.CHANNEL_AOM, False)
                sequence.setDigital(self.CHANNEL_MW, False)
                sequence.setDigital(self.CHANNEL_SPD, False)
                
                # Laser pulse
                if params['laser_delay'] > 0:
                    sequence.wait(params['laser_delay'])
                sequence.setDigital(self.CHANNEL_AOM, True)
                sequence.wait(params['laser_duration'])
                sequence.setDigital(self.CHANNEL_AOM, False)
                
                # MW pulse (relative to start)
                current_time = params['laser_delay'] + params['laser_duration']
                if params['mw_delay'] > current_time:
                    sequence.wait(params['mw_delay'] - current_time)
                    current_time = params['mw_delay']
                elif params['mw_delay'] < current_time:
                    # MW overlaps with laser - need to restart timing
                    sequence = Sequence()  # Restart for overlapping pulses
                    return self._create_overlapping_sequence(params, repetitions)
                
                sequence.setDigital(self.CHANNEL_MW, True)
                sequence.wait(params['mw_duration'])
                sequence.setDigital(self.CHANNEL_MW, False)
                current_time += params['mw_duration']
                
                # Detection window
                if params['detection_delay'] > current_time:
                    sequence.wait(params['detection_delay'] - current_time)
                elif params['detection_delay'] < current_time:
                    # Detection overlaps - handle appropriately
                    pass
                
                sequence.setDigital(self.CHANNEL_SPD, True)
                sequence.wait(params['detection_duration'])
                sequence.setDigital(self.CHANNEL_SPD, False)
            
            print(f"✅ ODMR sequence created with {repetitions} repetitions")
            return sequence
            
        except Exception as e:
            print(f"❌ Error creating ODMR sequence: {e}")
            return None
    
    def _create_overlapping_sequence(self, params: Dict, repetitions: int) -> Optional[Sequence]:
        """Create sequence with overlapping pulses using more complex timing."""
        try:
            sequence = Sequence()
            
            for rep in range(repetitions):
                if rep > 0:
                    sequence.wait(params['sequence_interval'])
                
                # Find the earliest start time
                events = [
                    (params['laser_delay'], 'laser_start'),
                    (params['laser_delay'] + params['laser_duration'], 'laser_end'),
                    (params['mw_delay'], 'mw_start'),
                    (params['mw_delay'] + params['mw_duration'], 'mw_end'),
                    (params['detection_delay'], 'detection_start'),
                    (params['detection_delay'] + params['detection_duration'], 'detection_end')
                ]
                
                # Sort events by time
                events.sort(key=lambda x: x[0])
                
                current_time = 0
                laser_on = False
                mw_on = False
                detection_on = False
                
                for event_time, event_type in events:
                    if event_time > current_time:
                        sequence.wait(event_time - current_time)
                        current_time = event_time
                    
                    if event_type == 'laser_start':
                        laser_on = True
                    elif event_type == 'laser_end':
                        laser_on = False
                    elif event_type == 'mw_start':
                        mw_on = True
                    elif event_type == 'mw_end':
                        mw_on = False
                    elif event_type == 'detection_start':
                        detection_on = True
                    elif event_type == 'detection_end':
                        detection_on = False
                    
                    # Update all channels
                    sequence.setDigital(self.CHANNEL_AOM, laser_on)
                    sequence.setDigital(self.CHANNEL_MW, mw_on)
                    sequence.setDigital(self.CHANNEL_SPD, detection_on)
            
            return sequence
            
        except Exception as e:
            print(f"❌ Error creating overlapping sequence: {e}")
            return None
    
    def run_sequence(self, sequence: Sequence, start_immediately: bool = True):
        """
        Upload and run a pulse sequence.
        
        Args:
            sequence: The pulse sequence to run
            start_immediately: Whether to start the sequence immediately
        """
        if not self.is_connected or sequence is None:
            print("❌ Cannot run sequence: device not connected or sequence is None")
            return
        
        try:
            self.pulse_streamer.stream(sequence, start_immediately)
            print("🚀 Pulse sequence started")
        except Exception as e:
            print(f"❌ Error running sequence: {e}")
    
    def stop_sequence(self):
        """Stop the current pulse sequence."""
        if not self.is_connected:
            return
        
        try:
            self.pulse_streamer.constant(OutputState.ZERO())
            print("🛑 Pulse sequence stopped")
        except Exception as e:
            print(f"❌ Error stopping sequence: {e}")
    
    def create_simple_laser_pulse(self, duration_ns: int = 1000) -> Optional[Sequence]:
        """
        Create a simple laser pulse for testing.
        
        Args:
            duration_ns: Duration of the laser pulse in nanoseconds
            
        Returns:
            Sequence object or None if error
        """
        if not self.is_connected:
            return None
        
        try:
            sequence = Sequence()
            sequence.setDigital(self.CHANNEL_AOM, True)
            sequence.wait(duration_ns)
            sequence.setDigital(self.CHANNEL_AOM, False)
            
            print(f"✅ Simple laser pulse created ({duration_ns} ns)")
            return sequence
        except Exception as e:
            print(f"❌ Error creating laser pulse: {e}")
            return None
    
    def create_rabi_sequence(self, mw_durations: List[int], 
                           laser_duration: int = 1000,
                           detection_duration: int = 500) -> Optional[Sequence]:
        """
        Create a Rabi oscillation measurement sequence.
        
        Args:
            mw_durations: List of MW pulse durations in ns
            laser_duration: Laser pulse duration in ns
            detection_duration: Detection window duration in ns
            
        Returns:
            Sequence object or None if error
        """
        if not self.is_connected:
            return None
        
        try:
            sequence = Sequence()
            
            for mw_duration in mw_durations:
                # Laser pulse for initialization
                sequence.setDigital(self.CHANNEL_AOM, True)
                sequence.wait(laser_duration)
                sequence.setDigital(self.CHANNEL_AOM, False)
                
                # Wait for relaxation
                sequence.wait(1000)  # 1 µs
                
                # MW pulse
                sequence.setDigital(self.CHANNEL_MW, True)
                sequence.wait(mw_duration)
                sequence.setDigital(self.CHANNEL_MW, False)
                
                # Detection
                sequence.setDigital(self.CHANNEL_SPD, True)
                sequence.wait(detection_duration)
                sequence.setDigital(self.CHANNEL_SPD, False)
                
                # Inter-sequence delay
                sequence.wait(10000)  # 10 µs
            
            print(f"✅ Rabi sequence created with {len(mw_durations)} MW durations")
            return sequence
            
        except Exception as e:
            print(f"❌ Error creating Rabi sequence: {e}")
            return None
    
    def get_device_info(self) -> Dict:
        """Get device information and status."""
        if not self.is_connected:
            return {"connected": False, "error": "Device not connected"}
        
        try:
            return {
                "connected": True,
                "ip_address": self.ip_address,
                "channels": {
                    "AOM": self.CHANNEL_AOM,
                    "MW": self.CHANNEL_MW,
                    "SPD": self.CHANNEL_SPD
                },
                "default_params": self.default_params
            }
        except Exception as e:
            return {"connected": False, "error": str(e)}


# Example usage and testing functions
def test_pulse_controller():
    """Test function for the pulse controller."""
    print("🧪 Testing Swabian Pulse Controller...")
    
    # Create controller instance
    controller = SwabianPulseController()
    
    if not controller.is_connected:
        print("❌ Cannot run tests - device not connected")
        return
    
    try:
        # Test 1: Simple laser pulse
        print("\n📍 Test 1: Simple laser pulse")
        laser_seq = controller.create_simple_laser_pulse(1000)
        if laser_seq:
            controller.run_sequence(laser_seq)
            time.sleep(2)
            controller.stop_sequence()
        
        # Test 2: ODMR sequence
        print("\n📍 Test 2: Basic ODMR sequence")
        odmr_seq = controller.create_odmr_sequence(
            laser_duration=1000,
            mw_duration=100,
            detection_duration=500,
            repetitions=3
        )
        if odmr_seq:
            controller.run_sequence(odmr_seq)
            time.sleep(3)
            controller.stop_sequence()
        
        # Test 3: Device info
        print("\n📍 Test 3: Device information")
        info = controller.get_device_info()
        print(f"Device info: {info}")
        
        print("\n✅ All tests completed successfully!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
    
    finally:
        controller.disconnect()


if __name__ == "__main__":
    test_pulse_controller() 