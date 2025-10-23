"""
Swabian Pulse Streamer 8/2 Controller for ODMR NV Experiments
------------------------------------------------------------
This module provides pulse generation control for ODMR (Optically Detected Magnetic Resonance)
experiments with Nitrogen-Vacancy (NV) centers using the Swabian Pulse Streamer 8/2.

Channel Assignment:
- Channel 0: AOM Laser control
- Channel 1: Microwave (MW) control
- Channel 2: Single Photon Detector (SPD) gate

Author: Javier Noé Ramos Silva
Contact: jramossi@uci.edu
Lab: Burke Lab, Department of Electrical Engineering and Computer Science, University of California, Irvine
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
    CHANNEL_TT = 3      # TimeTagger
    
    # Pulse Streamer timing constants
    TIMING_RESOLUTION = 8  # 8 ns minimum timing resolution
    
    @staticmethod
    def align_timing(duration_ns: int) -> int:
        """
        Align timing to 8 ns boundaries required by Pulse Streamer hardware.
        
        Args:
            duration_ns: Duration in nanoseconds
            
        Returns:
            Duration aligned to nearest 8 ns boundary (rounded up)
        """
        return ((duration_ns + 7) // 8) * 8
    
    @staticmethod
    def round_to_nearest_8ns(value: int) -> int:
        """
        Round value to nearest multiple of 8 ns (matches reference code approach).
        
        Args:
            value: Value in nanoseconds
            
        Returns:
            Value rounded to nearest 8 ns multiple
        """
        return round(value / 8) * 8
    
    @staticmethod
    def validate_timing(duration_ns: int) -> bool:
        """
        Check if timing is aligned to 8 ns boundaries.
        
        Args:
            duration_ns: Duration in nanoseconds
            
        Returns:
            True if aligned, False otherwise
        """
        return duration_ns % 8 == 0
    
    def __init__(self, ip_address: str = "192.168.0.203"):
        """
        Initialize the Pulse Streamer controller.
        
        Args:
            ip_address: IP address of the Pulse Streamer device
        """
        self.ip_address = ip_address
        self.pulse_streamer = None
        self.is_connected = False
        
        # Default timing parameters (in nanoseconds) - All values must be multiples of 8 ns
        self.default_params = {
            'laser_duration': 1000,      # 1 µs laser pulse (125 * 8)
            'mw_duration': 104,          # 104 ns MW pulse (13 * 8)
            'detection_duration': 504,   # 504 ns detection window (63 * 8)
            'laser_delay': 48,           # 48 ns delay before laser (6 * 8)
            'mw_delay': 104,             # 104 ns delay before MW (13 * 8)
            'detection_delay': 200,      # 200 ns delay before detection (25 * 8)
            'sequence_interval': 10000,  # 10 µs between sequences (1250 * 8)
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
            self.pulse_streamer.constant(OutputState([0], 0, 0))
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
                           sequence_interval: int = None,
                           repetitions: int = 1) -> Optional[Sequence]:
        """
        Create an ODMR pulse sequence following proper 8ns pattern building.
        
        Args:
            laser_duration: Duration of laser pulse in ns
            mw_duration: Duration of MW pulse in ns
            detection_duration: Duration of detection window in ns
            laser_delay: Delay before laser pulse in ns
            mw_delay: Delay before MW pulse in ns
            detection_delay: Delay before detection in ns
            sequence_interval: Dead time between sequence repetitions in ns
            repetitions: Number of sequence repetitions
            
        Returns:
            Sequence object or None if error
        """
        if not self.is_connected:
            print("❌ Device not connected")
            return None
        
        # Use default parameters if not specified and align all timing to 8 ns boundaries
        params = self.default_params.copy()
        if laser_duration is not None:
            params['laser_duration'] = self.align_timing(laser_duration)
        if mw_duration is not None:
            params['mw_duration'] = self.align_timing(mw_duration)
        if detection_duration is not None:
            params['detection_duration'] = self.align_timing(detection_duration)
        if laser_delay is not None:
            params['laser_delay'] = self.align_timing(laser_delay)
        if mw_delay is not None:
            params['mw_delay'] = self.align_timing(mw_delay)
        if detection_delay is not None:
            params['detection_delay'] = self.align_timing(detection_delay)
        if sequence_interval is not None:
            params['sequence_interval'] = self.align_timing(sequence_interval)
        
        try:
            # Calculate total sequence duration per repetition
            single_seq_duration = max(
                params['laser_delay'] + params['laser_duration'],
                params['mw_delay'] + params['mw_duration'],
                params['detection_delay'] + params['detection_duration']
            )
            
            # Ensure single sequence duration is 8ns aligned
            single_seq_duration = self.align_timing(single_seq_duration)
            
            # Create pattern arrays following the working approach
            aom_pattern = self._create_laser_pattern(params, single_seq_duration, repetitions)
            mw_pattern = self._create_mw_pattern(params, single_seq_duration, repetitions)
            spd_pattern = self._create_spd_pattern(params, single_seq_duration, repetitions)
            
            # Validate total pattern duration is 8ns aligned
            total_duration = sum(duration for duration, _ in aom_pattern)
            if total_duration % 8 != 0:
                print(f"❌ Error: Total sequence length ({total_duration} ns) not multiple of 8 ns")
                return None
            
            # Calculate actual experiment time including intervals
            sequence_time = single_seq_duration * repetitions + params['sequence_interval'] * (repetitions - 1)
            
            # Create sequence using createSequence method like in working code
            sequence = self.pulse_streamer.createSequence()
            
            # Set patterns for each channel
            sequence.setDigital(self.CHANNEL_AOM, aom_pattern)
            sequence.setDigital(self.CHANNEL_MW, mw_pattern)
            sequence.setDigital(self.CHANNEL_SPD, spd_pattern)
            
            print(f"✅ ODMR sequence created: {repetitions} reps, {total_duration} ns total, {params['sequence_interval']} ns intervals (8ns aligned)")
            return sequence, total_duration
            
        except Exception as e:
            print(f"❌ Error creating ODMR sequence: {e}")
            return None
    
    def _create_laser_pattern(self, params: Dict, seq_duration: int, repetitions: int) -> List[Tuple[int, int]]:
        """Create laser (AOM) pattern array."""
        pattern = []
        
        for rep in range(repetitions):
            # Add inter-sequence delay if not first repetition
            if rep > 0:
                pattern.append((params['sequence_interval'], 0))
            
            # Laser pulse timing
            if params['laser_delay'] > 0:
                pattern.append((params['laser_delay'], 0))
            pattern.append((params['laser_duration'], 1))
            
            # Calculate remaining time to fill sequence duration
            used_time = params['laser_delay'] + params['laser_duration']
            remaining_time = seq_duration - used_time
            if remaining_time > 0:
                pattern.append((remaining_time, 0))
        
        return pattern
    
    def _create_mw_pattern(self, params: Dict, seq_duration: int, repetitions: int) -> List[Tuple[int, int]]:
        """Create microwave pattern array."""
        pattern = []
        
        for rep in range(repetitions):
            # Add inter-sequence delay if not first repetition
            if rep > 0:
                pattern.append((params['sequence_interval'], 0))
            
            # MW pulse timing
            if params['mw_delay'] > 0:
                pattern.append((params['mw_delay'], 0))
            pattern.append((params['mw_duration'], 1))
            
            # Calculate remaining time to fill sequence duration
            used_time = params['mw_delay'] + params['mw_duration']
            remaining_time = seq_duration - used_time
            if remaining_time > 0:
                pattern.append((remaining_time, 0))
        
        return pattern
    
    def _create_spd_pattern(self, params: Dict, seq_duration: int, repetitions: int) -> List[Tuple[int, int]]:
        """Create SPD gate pattern array."""
        pattern = []
        
        for rep in range(repetitions):
            # Add inter-sequence delay if not first repetition
            if rep > 0:
                pattern.append((params['sequence_interval'], 0))
            
            # SPD gate timing
            if params['detection_delay'] > 0:
                pattern.append((params['detection_delay'], 0))
            pattern.append((params['detection_duration'], 1))
            
            # Calculate remaining time to fill sequence duration
            used_time = params['detection_delay'] + params['detection_duration']
            remaining_time = seq_duration - used_time
            if remaining_time > 0:
                pattern.append((remaining_time, 0))
        
        return pattern
    
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
            self.pulse_streamer.constant(OutputState([0], 0, 0))
            print("🛑 Pulse sequence stopped")
        except Exception as e:
            print(f"❌ Error stopping sequence: {e}")
    
    def create_simple_laser_pulse(self, duration_ns: int = 1000) -> Optional[Sequence]:
        """
        Create a simple laser pulse for testing with proper 8 ns timing alignment.
        
        Args:
            duration_ns: Duration of the laser pulse in nanoseconds
            
        Returns:
            Sequence object or None if error
        """
        if not self.is_connected:
            return None
        
        # Align duration to 8 ns boundary
        aligned_duration = self.align_timing(duration_ns)
        
        if aligned_duration != duration_ns:
            print(f"🔧 Pulse duration aligned from {duration_ns} ns to {aligned_duration} ns")
        
        try:
            # Create sequence using createSequence like working code
            sequence = self.pulse_streamer.createSequence()
            
            # Create pattern array: [(duration, level)]
            laser_pattern = [(aligned_duration, 1)]
            
            # Set digital pattern for AOM channel
            sequence.setDigital(self.CHANNEL_AOM, laser_pattern)
            
            print(f"✅ Simple laser pulse created ({aligned_duration} ns, 8 ns aligned)")
            return sequence
        except Exception as e:
            print(f"❌ Error creating laser pulse: {e}")
            return None
    
    def create_rabi_sequence(self, mw_durations: List[int], 
                           laser_duration: int = 1000,
                           detection_duration: int = 500) -> Optional[Sequence]:
        """
        Create a Rabi oscillation measurement sequence with proper 8 ns timing alignment.
        
        Args:
            mw_durations: List of MW pulse durations in ns
            laser_duration: Laser pulse duration in ns
            detection_duration: Detection window duration in ns
            
        Returns:
            Sequence object or None if error
        """
        if not self.is_connected:
            return None
        
        # Align all timing parameters to 8 ns boundaries
        laser_duration = self.align_timing(laser_duration)
        detection_duration = self.align_timing(detection_duration)
        mw_durations = [self.align_timing(d) for d in mw_durations]
        
        try:
            # Create pattern arrays for each channel
            aom_pattern = []
            mw_pattern = []
            spd_pattern = []
            
            # Build patterns for each MW duration
            for i, mw_duration in enumerate(mw_durations):
                # Add inter-sequence delay if not first sequence
                if i > 0:
                    inter_delay = self.align_timing(10000)  # 10 µs aligned
                    aom_pattern.append((inter_delay, 0))
                    mw_pattern.append((inter_delay, 0))
                    spd_pattern.append((inter_delay, 0))
                
                # Timing constants
                wait_time = self.align_timing(1000)  # 1 µs wait time
                
                # AOM pattern: initialization laser -> wait -> off during MW -> off during detection
                aom_pattern.extend([
                    (laser_duration, 1),       # Initialization laser ON
                    (wait_time, 0),            # Wait period
                    (mw_duration, 0),          # MW period (laser OFF)
                    (detection_duration, 0)    # Detection period (laser OFF)
                ])
                
                # MW pattern: off during laser -> off during wait -> MW pulse -> off during detection
                mw_pattern.extend([
                    (laser_duration, 0),       # Laser period (MW OFF)
                    (wait_time, 0),            # Wait period (MW OFF)
                    (mw_duration, 1),          # MW ON
                    (detection_duration, 0)    # Detection period (MW OFF)
                ])
                
                # SPD pattern: off during laser -> off during wait -> off during MW -> detection gate
                spd_pattern.extend([
                    (laser_duration, 0),       # Laser period (SPD OFF)
                    (wait_time, 0),            # Wait period (SPD OFF)
                    (mw_duration, 0),          # MW period (SPD OFF)
                    (detection_duration, 1)    # SPD ON for detection
                ])
            
            # Validate total pattern duration is 8ns aligned
            total_duration = sum(duration for duration, _ in aom_pattern)
            if total_duration % 8 != 0:
                print(f"❌ Error: Rabi sequence length ({total_duration} ns) not multiple of 8 ns")
                return None
            
            # Create sequence using createSequence like working code
            sequence = self.pulse_streamer.createSequence()
            
            # Set patterns for each channel
            sequence.setDigital(self.CHANNEL_AOM, aom_pattern)
            sequence.setDigital(self.CHANNEL_MW, mw_pattern)
            sequence.setDigital(self.CHANNEL_SPD, spd_pattern)
            
            print(f"✅ Rabi sequence created: {len(mw_durations)} MW durations, {total_duration} ns total")
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