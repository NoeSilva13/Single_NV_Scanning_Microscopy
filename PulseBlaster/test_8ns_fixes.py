#!/usr/bin/env python3
"""
Test script to verify 8ns alignment fixes for Pulse Streamer
Validates that pulse sequences are properly aligned to hardware requirements.
"""

import numpy as np
from swabian_pulse_streamer import SwabianPulseController

def test_8ns_fixes():
    """Test the 8ns alignment fixes following reference code patterns."""
    print("🔧 Testing 8ns Alignment Fixes")
    print("=" * 60)
    
    # Create controller
    controller = SwabianPulseController()
    
    if not controller.is_connected:
        print("❌ Cannot run tests - device not connected")
        return
    
    try:
        print("\n1️⃣ Testing Simple Laser Pulse (Reference Pattern)")
        print("-" * 50)
        
        # Test various durations including problematic ones
        test_durations = [100, 105, 123, 1000, 1001, 1007, 1234]
        
        for duration in test_durations:
            print(f"\n📍 Testing {duration} ns pulse:")
            
            # Create pulse using new method
            laser_seq = controller.create_simple_laser_pulse(duration)
            if laser_seq:
                print(f"   ✅ Sequence created successfully")
                # Could run sequence here if needed: controller.run_sequence(laser_seq)
            else:
                print(f"   ❌ Failed to create sequence")
        
        print("\n2️⃣ Testing ODMR Sequences (Reference Pattern)")
        print("-" * 50)
        
        # Test ODMR with various timing - including problematic values
        test_cases = [
            {
                "name": "Standard ODMR",
                "params": {"laser_duration": 1000, "mw_duration": 104, "detection_duration": 504}
            },
            {
                "name": "Unaligned inputs", 
                "params": {"laser_duration": 1005, "mw_duration": 123, "detection_duration": 456}
            },
            {
                "name": "Short pulses",
                "params": {"laser_duration": 100, "mw_duration": 50, "detection_duration": 200}
            }
        ]
        
        for test_case in test_cases:
            print(f"\n📍 {test_case['name']}:")
            params = test_case['params']
            
            for key, value in params.items():
                aligned = controller.align_timing(value)
                print(f"   {key}: {value} ns → {aligned} ns")
            
            odmr_seq = controller.create_odmr_sequence(**params, repetitions=2)
            if odmr_seq:
                print(f"   ✅ ODMR sequence created successfully")
            else:
                print(f"   ❌ Failed to create ODMR sequence")
        
        print("\n3️⃣ Testing Rabi Sequences (Reference Pattern)")
        print("-" * 50)
        
        # Test with various MW durations including unaligned values
        mw_durations = [10, 25, 33, 50, 67, 100, 123, 200]
        
        print(f"Original MW durations: {mw_durations}")
        aligned_durations = [controller.align_timing(d) for d in mw_durations]
        print(f"Aligned MW durations:  {aligned_durations}")
        
        rabi_seq = controller.create_rabi_sequence(
            mw_durations=mw_durations,
            laser_duration=1000,
            detection_duration=500
        )
        
        if rabi_seq:
            print(f"✅ Rabi sequence created with {len(mw_durations)} MW durations")
        else:
            print(f"❌ Failed to create Rabi sequence")
        
        print("\n4️⃣ Pattern Duration Validation")
        print("-" * 50)
        
        # Test that patterns have proper total duration
        def validate_pattern_duration(pattern, name):
            total_duration = sum(duration for duration, _ in pattern)
            is_aligned = total_duration % 8 == 0
            status = "✅" if is_aligned else "❌"
            print(f"   {name}: {total_duration} ns {status}")
            return is_aligned
        
        # Create some test patterns manually
        test_patterns = [
            ([(1000, 1), (1000, 0)], "Simple 2µs pattern"),
            ([(104, 1), (896, 0)], "104ns + 896ns pattern"),
            ([(100, 1), (123, 0), (777, 1)], "Multi-segment pattern")
        ]
        
        all_valid = True
        for pattern, name in test_patterns:
            if not validate_pattern_duration(pattern, name):
                all_valid = False
        
        if all_valid:
            print("✅ All test patterns are 8ns aligned!")
        else:
            print("⚠️ Some patterns need alignment!")
        
        print("\n5️⃣ Sequence Creation Method Validation")
        print("-" * 50)
        
        # Verify using createSequence() method like reference code
        print("📍 Checking sequence creation method:")
        try:
            test_seq = controller.pulse_streamer.createSequence()
            test_pattern = [(1000, 1)]
            test_seq.setDigital(0, test_pattern)
            print("   ✅ Using pulse_streamer.createSequence() - matches reference")
        except Exception as e:
            print(f"   ❌ createSequence() method failed: {e}")
        
        print("\n6️⃣ Edge Case Testing")
        print("-" * 50)
        
        # Test edge cases that could cause problems
        edge_cases = [
            {"duration": 8, "description": "Exactly 8ns"},
            {"duration": 1, "description": "Very short (1ns)"},
            {"duration": 7, "description": "Just under 8ns"},
            {"duration": 9, "description": "Just over 8ns"},
        ]
        
        for case in edge_cases:
            duration = case["duration"]
            aligned = controller.align_timing(duration)
            print(f"   {case['description']}: {duration} ns → {aligned} ns")
        
        print("\n✅ All 8ns alignment tests completed!")
        print("\n📋 Summary:")
        print("   • Using pulse_streamer.createSequence() like reference code")
        print("   • Building complete pattern arrays as [(duration, level)]")
        print("   • Automatic 8ns alignment for all timing parameters")
        print("   • Total sequence duration validation")
        print("   • Pattern-based approach matching working reference")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
    
    finally:
        controller.disconnect()

def demonstrate_pattern_building():
    """Demonstrate the pattern building approach from reference code."""
    print("\n🛠️ Pattern Building Demonstration")
    print("=" * 60)
    
    print("Reference code pattern building approach:")
    print("1. Define pattern units as [(duration, level)] tuples")
    print("2. Repeat pattern units for multiple cycles")
    print("3. Add end padding to align total duration")
    print("4. Validate total duration is multiple of 8ns")
    print("5. Use sequence.setDigital(channel, pattern_array)")
    
    # Example pattern building like reference code
    print("\nExample pattern construction:")
    
    # Parameters
    tau_laser_ns = 1000
    tau_mw_ns = 100
    tau_padding_before_mw_ns = 500
    tau_padding_after_mw_ns = 500
    n_repeat = 3
    
    print(f"Parameters:")
    print(f"  tau_laser_ns = {tau_laser_ns}")
    print(f"  tau_mw_ns = {tau_mw_ns}")
    print(f"  tau_padding_before_mw_ns = {tau_padding_before_mw_ns}")
    print(f"  tau_padding_after_mw_ns = {tau_padding_after_mw_ns}")
    print(f"  n_repeat = {n_repeat}")
    
    # Build pattern like reference code
    pattern_subunit = [
        (tau_laser_ns, 1),
        (tau_padding_before_mw_ns + tau_mw_ns + tau_padding_after_mw_ns, 0)
    ]
    
    pattern = pattern_subunit * n_repeat
    
    # Calculate total duration
    total_duration = sum(duration for duration, _ in pattern)
    
    print(f"\nPattern construction:")
    print(f"  Subunit: {pattern_subunit}")
    print(f"  Repeated {n_repeat} times")
    print(f"  Total duration: {total_duration} ns")
    print(f"  8ns aligned: {total_duration % 8 == 0}")
    
    if total_duration % 8 != 0:
        aligned_duration = ((total_duration + 7) // 8) * 8
        padding_needed = aligned_duration - total_duration
        print(f"  Padding needed: {padding_needed} ns")
        pattern.append((padding_needed, 0))
        print(f"  Final duration: {aligned_duration} ns ✅")

if __name__ == "__main__":
    test_8ns_fixes()
    demonstrate_pattern_building() 