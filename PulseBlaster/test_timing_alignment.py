#!/usr/bin/env python3
"""
Test script for Pulse Streamer 8 ns timing alignment
Demonstrates proper pulse generation with hardware-aligned timing.

The Pulse Streamer hardware operates with 8 ns chunks, so all timing must be
multiples of 8 ns to avoid unwanted padding and timing errors.
"""

import numpy as np
from swabian_pulse_streamer import SwabianPulseController

def test_timing_alignment():
    """Test and demonstrate proper timing alignment for Pulse Streamer."""
    print("🧪 Testing Pulse Streamer 8 ns Timing Alignment")
    print("=" * 60)
    
    # Create controller
    controller = SwabianPulseController()
    
    if not controller.is_connected:
        print("❌ Cannot run tests - device not connected")
        return
    
    try:
        print("\n1️⃣ Testing Simple Laser Pulses with Alignment")
        print("-" * 50)
        
        # Test various pulse durations
        test_durations = [100, 105, 123, 1000, 1001, 1007]  # Mix of aligned and unaligned
        
        for duration in test_durations:
            print(f"\n📍 Testing {duration} ns pulse:")
            aligned = controller.align_timing(duration)
            is_aligned = controller.validate_timing(duration)
            
            print(f"   Original: {duration} ns")
            print(f"   Aligned:  {aligned} ns")
            print(f"   Valid:    {is_aligned}")
            
            # Create pulse with alignment
            pulse_seq = controller.create_simple_laser_pulse(duration)
            if pulse_seq:
                print(f"   ✅ Pulse sequence created successfully")
            else:
                print(f"   ❌ Failed to create pulse sequence")
        
        print("\n2️⃣ Testing ODMR Sequences with Alignment")
        print("-" * 50)
        
        # Test ODMR with various timing parameters
        test_params = [
            {"laser_duration": 1000, "mw_duration": 100, "detection_duration": 500},
            {"laser_duration": 1005, "mw_duration": 123, "detection_duration": 456},  # Unaligned
            {"laser_duration": 2000, "mw_duration": 200, "detection_duration": 800},
        ]
        
        for i, params in enumerate(test_params):
            print(f"\n📍 ODMR Test {i+1}:")
            for key, value in params.items():
                aligned = controller.align_timing(value)
                print(f"   {key}: {value} ns → {aligned} ns")
            
            odmr_seq = controller.create_odmr_sequence(**params, repetitions=1)
            if odmr_seq:
                print(f"   ✅ ODMR sequence created with aligned timing")
            else:
                print(f"   ❌ Failed to create ODMR sequence")
        
        print("\n3️⃣ Testing Rabi Sequences with Alignment")
        print("-" * 50)
        
        # Test Rabi with various MW durations
        mw_durations = [10, 25, 33, 50, 67, 100, 123, 200]  # Mix of aligned and unaligned
        
        print(f"Original MW durations: {mw_durations}")
        aligned_durations = [controller.align_timing(d) for d in mw_durations]
        print(f"Aligned MW durations:  {aligned_durations}")
        
        rabi_seq = controller.create_rabi_sequence(
            mw_durations=mw_durations,
            laser_duration=1000,
            detection_duration=500
        )
        
        if rabi_seq:
            print(f"✅ Rabi sequence created with {len(mw_durations)} aligned MW durations")
        else:
            print(f"❌ Failed to create Rabi sequence")
        
        print("\n4️⃣ Timing Alignment Guidelines")
        print("-" * 50)
        print("📋 Key Points for Proper Pulse Streamer Operation:")
        print("   • All pulse durations must be multiples of 8 ns")
        print("   • All delays must be multiples of 8 ns")
        print("   • Total sequence duration should be multiple of 8 ns")
        print("   • Use sequence.repeat(8) for continuous operation alignment")
        print("   • Hardware automatically pads non-aligned sequences")
        print("   • Padding can cause timing errors in repetitive sequences")
        
        print("\n5️⃣ Default Parameter Alignment Check")
        print("-" * 50)
        defaults = controller.default_params
        all_aligned = True
        
        for param, value in defaults.items():
            is_aligned = controller.validate_timing(value)
            status = "✅" if is_aligned else "❌"
            print(f"   {param}: {value} ns {status}")
            if not is_aligned:
                all_aligned = False
        
        if all_aligned:
            print("✅ All default parameters are properly aligned!")
        else:
            print("⚠️ Some default parameters need alignment!")
        
        print("\n6️⃣ Practical Examples")
        print("-" * 50)
        
        # Example 1: Short continuous pulse train
        print("\n📍 Example 1: Creating 8 ns aligned pulse train")
        short_pulse = 24  # 3 * 8 ns
        aligned_short = controller.align_timing(short_pulse)
        print(f"   Short pulse: {short_pulse} ns → {aligned_short} ns")
        
        # Example 2: ODMR with realistic NV parameters
        print("\n📍 Example 2: Realistic NV ODMR parameters")
        nv_params = {
            "laser_duration": 3000,    # 3 µs laser (aligned: 3000 ns)
            "mw_duration": 1000,       # 1 µs MW (aligned: 1000 ns)
            "detection_duration": 1000, # 1 µs detection (aligned: 1000 ns)
            "laser_delay": 100,        # 100 ns delay (aligned: 100 ns)
            "mw_delay": 3200,          # After laser + delay (aligned: 3200 ns)
            "detection_delay": 4300    # After MW + delay (aligned: 4304 ns)
        }
        
        for key, value in nv_params.items():
            aligned = controller.align_timing(value)
            print(f"   {key}: {value} ns → {aligned} ns")
        
        nv_odmr_seq = controller.create_odmr_sequence(**nv_params)
        if nv_odmr_seq:
            print("   ✅ Realistic NV ODMR sequence created successfully")
        
        print("\n✅ All timing alignment tests completed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
    
    finally:
        controller.disconnect()

def demonstrate_timing_issues():
    """Demonstrate common timing issues and their solutions."""
    print("\n🔍 Common Timing Issues and Solutions")
    print("=" * 60)
    
    # Issue 1: Non-aligned short pulses
    print("\n❌ Issue 1: Non-aligned short pulses in repetitive sequences")
    print("   Problem: 3 ns high + 2 ns low = 5 ns period")
    print("   Hardware: Padded to 8 ns → 3 ns high + 5 ns low")
    print("   Expected: 200 MHz")
    print("   Actual:   125 MHz")
    print("   Solution: Use 8 ns aligned periods (e.g., 3 ns high + 5 ns low = 8 ns)")
    
    # Issue 2: Sequence duration not aligned
    print("\n❌ Issue 2: Sequence duration not multiple of 8 ns")
    print("   Problem: 12345 ns sequence")
    print("   Hardware: Padded to 12352 ns (1544 × 8 ns)")
    print("   Error:    +7 ns timing drift per repetition")
    print("   Solution: Design sequences with 8 ns aligned total duration")
    
    # Issue 3: MW pulse timing
    print("\n❌ Issue 3: Unaligned MW pulse durations")
    print("   Problem: MW pulses at 13, 27, 41 ns (not 8 ns aligned)")
    print("   Hardware: Padded to 16, 32, 48 ns")
    print("   Effect:   Incorrect Rabi frequency calibration")
    print("   Solution: Use 8, 16, 24, 32, 40, 48 ns etc.")
    
    print("\n✅ Solutions Summary:")
    print("   1. Always use multiples of 8 ns for all timing")
    print("   2. Use align_timing() function for user inputs")
    print("   3. Use sequence.repeat(8) for continuous operation")
    print("   4. Validate timing with validate_timing() function")

if __name__ == "__main__":
    test_timing_alignment()
    demonstrate_timing_issues() 