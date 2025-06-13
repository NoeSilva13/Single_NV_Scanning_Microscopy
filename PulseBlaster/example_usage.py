"""
Example Usage of PulseBlaster Module
-----------------------------------
Simple examples demonstrating how to use the Swabian Pulse Streamer 8/2
for ODMR experiments with NV centers.

Run this script to test basic functionality of the pulse controller.
"""

import time
import numpy as np
from swabian_pulse_streamer import SwabianPulseController

def basic_pulse_test():
    """Test basic pulse generation functionality"""
    print("🧪 Testing Basic Pulse Generation...")
    
    # Initialize the pulse controller
    controller = SwabianPulseController()
    
    if not controller.is_connected:
        print("❌ Device not connected - running simulation")
        return
    
    try:
        # Test 1: Simple laser pulse
        print("\n📍 Test 1: 1 µs laser pulse on AOM channel")
        laser_sequence = controller.create_simple_laser_pulse(1000)  # 1 µs
        
        if laser_sequence:
            controller.run_sequence(laser_sequence)
            time.sleep(2)  # Let it run for 2 seconds
            controller.stop_sequence()
            print("✅ Laser pulse test completed")
        
        # Test 2: Basic ODMR sequence
        print("\n📍 Test 2: Basic ODMR pulse sequence")
        odmr_sequence = controller.create_odmr_sequence(
            laser_duration=1000,      # 1 µs laser
            mw_duration=100,          # 100 ns MW
            detection_duration=500,   # 500 ns detection
            repetitions=5             # 5 repetitions
        )
        
        if odmr_sequence:
            controller.run_sequence(odmr_sequence)
            time.sleep(3)  # Let it run for 3 seconds
            controller.stop_sequence()
            print("✅ ODMR sequence test completed")
        
        # Test 3: Rabi sequence
        print("\n📍 Test 3: Rabi oscillation sequence")
        mw_durations = [10, 25, 50, 75, 100]  # Different MW pulse durations
        rabi_sequence = controller.create_rabi_sequence(
            mw_durations=mw_durations,
            laser_duration=1000,
            detection_duration=500
        )
        
        if rabi_sequence:
            controller.run_sequence(rabi_sequence)
            time.sleep(2)
            controller.stop_sequence()
            print("✅ Rabi sequence test completed")
        
        # Test 4: Device information
        print("\n📍 Test 4: Device information")
        info = controller.get_device_info()
        print(f"Device Info: {info}")
        
        print("\n🎉 All tests completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
    
    finally:
        controller.disconnect()

def channel_test():
    """Test individual channel control"""
    print("\n🔧 Testing Individual Channels...")
    
    controller = SwabianPulseController()
    
    if not controller.is_connected:
        print("❌ Device not connected")
        return
    
    try:
        # Test each channel individually
        channels = [
            (controller.CHANNEL_AOM, "AOM Laser"),
            (controller.CHANNEL_MW, "Microwave"),
            (controller.CHANNEL_SPD, "SPD Gate")
        ]
        
        for channel, name in channels:
            print(f"📡 Testing {name} (Channel {channel})")
            
            # Create a simple pulse on this channel
            from pulsestreamer import Sequence
            sequence = Sequence()
            sequence.setDigital(channel, True)
            sequence.wait(1000000)  # 1 ms pulse
            sequence.setDigital(channel, False)
            
            controller.run_sequence(sequence)
            time.sleep(0.5)
            controller.stop_sequence()
            time.sleep(0.5)
        
        print("✅ Channel tests completed")
        
    except Exception as e:
        print(f"❌ Channel test error: {e}")
    
    finally:
        controller.disconnect()

def custom_odmr_sequence():
    """Create and run a custom ODMR sequence with specific timing"""
    print("\n🔬 Running Custom ODMR Sequence...")
    
    controller = SwabianPulseController()
    
    if not controller.is_connected:
        print("❌ Device not connected")
        return
    
    try:
        # Custom timing parameters
        custom_sequence = controller.create_odmr_sequence(
            laser_duration=2000,      # 2 µs laser for better initialization
            mw_duration=50,           # 50 ns MW pulse (around π/2)
            detection_duration=1000,  # 1 µs detection window
            laser_delay=0,            # Start immediately
            mw_delay=3000,            # MW 3 µs after start (1 µs after laser)
            detection_delay=4000,     # Detection 4 µs after start
            repetitions=10            # 10 repetitions
        )
        
        if custom_sequence:
            print("🚀 Running custom ODMR sequence...")
            controller.run_sequence(custom_sequence)
            time.sleep(5)  # Run for 5 seconds
            controller.stop_sequence()
            print("✅ Custom ODMR sequence completed")
        
    except Exception as e:
        print(f"❌ Custom sequence error: {e}")
    
    finally:
        controller.disconnect()

def main():
    """Main function to run all examples"""
    print("=" * 60)
    print("🎯 PulseBlaster Example Usage")
    print("=" * 60)
    
    # Run basic tests
    basic_pulse_test()
    
    # Test individual channels
    channel_test()
    
    # Run custom sequence
    custom_odmr_sequence()
    
    print("\n" + "=" * 60)
    print("🎉 All examples completed!")
    print("=" * 60)

if __name__ == "__main__":
    main() 