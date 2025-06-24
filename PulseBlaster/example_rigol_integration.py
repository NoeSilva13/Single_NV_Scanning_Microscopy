"""
Example Usage: RIGOL DSG836 Integration with ODMR Experiments
------------------------------------------------------------
This example demonstrates how to use the RIGOL DSG836 signal generator
with the Swabian Pulse Streamer for ODMR experiments.

Author: AI Assistant
Date: 2024
"""

import numpy as np
import time
from .swabian_pulse_streamer import SwabianPulseController
from .rigol_dsg836 import RigolDSG836Controller
from .odmr_experiments import ODMRExperiments


def test_rigol_connection():
    """Test connection to RIGOL DSG836 signal generator."""
    print("🔧 Testing RIGOL DSG836 Connection...")
    
    # Initialize RIGOL controller
    rigol = RigolDSG836Controller("192.168.0.222")
    
    try:
        if rigol.connect():
            print("✅ Successfully connected to RIGOL DSG836")
            
            # Get instrument status
            status = rigol.get_status()
            print(f"📊 Instrument Status: {status}")
            
            # Test basic commands
            print("\n🧪 Testing basic commands...")
            
            # Set frequency and power
            rigol.set_odmr_frequency(2.87)  # 2.87 GHz
            rigol.set_odmr_power(-15.0)     # -15 dBm
            
            # Read back settings
            freq = rigol.get_frequency() / 1e9
            power = rigol.get_power()
            print(f"📡 Frequency: {freq:.6f} GHz")
            print(f"⚡ Power: {power:.1f} dBm")
            
            # Test RF output control
            print("\n🔄 Testing RF output control...")
            rigol.set_rf_output(True)
            print("RF output enabled")
            time.sleep(1)
            
            rigol.set_rf_output(False)
            print("RF output disabled")
            
            print("✅ RIGOL test completed successfully")
            return True
            
    except Exception as e:
        print(f"❌ RIGOL test failed: {e}")
        return False
    finally:
        rigol.disconnect()


def test_combined_system():
    """Test the combined Pulse Streamer + RIGOL system."""
    print("\n🔬 Testing Combined Pulse Streamer + RIGOL System...")
    
    # Initialize controllers
    pulse_controller = SwabianPulseController("192.168.0.201")
    rigol = RigolDSG836Controller("192.168.0.222")
    
    try:
        # Connect to both instruments
        pulse_connected = pulse_controller.connect()
        rigol_connected = rigol.connect()
        
        if not pulse_connected:
            print("❌ Failed to connect to Pulse Streamer")
            return False
            
        if not rigol_connected:
            print("❌ Failed to connect to RIGOL DSG836")
            return False
        
        print("✅ Both instruments connected successfully")
        
        # Initialize ODMR experiments with both controllers
        experiments = ODMRExperiments(pulse_controller, rigol)
        
        # Test simple ODMR sequence with MW control
        print("\n🧪 Testing ODMR sequence with MW control...")
        
        # Prepare RIGOL for ODMR
        rigol.prepare_for_odmr(frequency_ghz=2.87, power_dbm=-15.0)
        
        # Create and run a simple ODMR sequence
        sequence = pulse_controller.create_odmr_sequence(
            laser_duration=1000,   # 1 µs laser
            mw_duration=500,       # 500 ns MW
            detection_duration=500, # 500 ns detection
            repetitions=10
        )
        
        if sequence:
            print("📡 Enabling MW output...")
            rigol.set_rf_output(True)
            
            print("🔄 Running pulse sequence...")
            pulse_controller.run_sequence(sequence)
            time.sleep(0.5)  # Let sequence run
            
            pulse_controller.stop_sequence()
            
            print("📡 Disabling MW output...")
            rigol.set_rf_output(False)
            
            print("✅ Combined system test successful")
            return True
        else:
            print("❌ Failed to create pulse sequence")
            return False
            
    except Exception as e:
        print(f"❌ Combined system test failed: {e}")
        return False
    finally:
        # Clean up
        if rigol.connected:
            rigol.set_rf_output(False)
            rigol.disconnect()
        if pulse_controller.is_connected:
            pulse_controller.disconnect()


def run_odmr_with_rigol():
    """Run a complete ODMR experiment with RIGOL frequency control."""
    print("\n🔬 Running ODMR Experiment with RIGOL Frequency Control...")
    
    # Initialize controllers
    pulse_controller = SwabianPulseController("192.168.0.201")
    rigol = RigolDSG836Controller("192.168.0.222")
    
    try:
        # Connect to instruments
        if not pulse_controller.connect():
            print("❌ Failed to connect to Pulse Streamer")
            return
            
        if not rigol.connect():
            print("❌ Failed to connect to RIGOL DSG836")
            return
        
        # Initialize experiments
        experiments = ODMRExperiments(pulse_controller, rigol)
        
        # Define frequency sweep parameters
        start_freq = 2.8e9  # 2.8 GHz
        stop_freq = 2.9e9   # 2.9 GHz
        num_points = 21     # 21 frequency points
        
        frequencies = np.linspace(start_freq, stop_freq, num_points)
        
        print(f"📡 Frequency sweep: {start_freq/1e9:.2f} - {stop_freq/1e9:.2f} GHz")
        print(f"📊 Number of points: {num_points}")
        
        # Run CW ODMR experiment
        results = experiments.continuous_wave_odmr(
            mw_frequencies=list(frequencies),
            laser_duration=2000,
            detection_duration=1000,
            measurements_per_point=50
        )
        
        if results:
            print("\n📊 ODMR Results Summary:")
            print(f"Number of frequency points: {len(results['frequencies'])}")
            print(f"Frequency range: {min(results['frequencies'])/1e9:.3f} - {max(results['frequencies'])/1e9:.3f} GHz")
            print(f"Count rate range: {min(results['count_rates']):.0f} - {max(results['count_rates']):.0f} Hz")
            
            # Plot results
            experiments.plot_results('cw_odmr')
            
            print("✅ ODMR experiment completed successfully")
        else:
            print("❌ ODMR experiment failed")
            
    except Exception as e:
        print(f"❌ ODMR experiment failed: {e}")
    finally:
        # Clean up
        if rigol.connected:
            rigol.set_rf_output(False)
            rigol.disconnect()
        if pulse_controller.is_connected:
            pulse_controller.disconnect()


def run_automated_odmr_sweep():
    """Run automated ODMR sweep using RIGOL's internal frequency sweep."""
    print("\n🚀 Running Automated ODMR Sweep with RIGOL Internal Sweep...")
    
    # Initialize controllers
    pulse_controller = SwabianPulseController("192.168.0.201")
    rigol = RigolDSG836Controller("192.168.0.222")
    
    try:
        # Connect to instruments
        if not pulse_controller.connect():
            print("❌ Failed to connect to Pulse Streamer")
            return
            
        if not rigol.connect():
            print("❌ Failed to connect to RIGOL DSG836")
            return
        
        # Initialize experiments
        experiments = ODMRExperiments(pulse_controller, rigol)
        
        # Run automated ODMR sweep
        results = experiments.automated_odmr_sweep(
            start_freq_ghz=2.8,
            stop_freq_ghz=2.9,
            num_points=51,
            power_dbm=-12.0,
            laser_duration=1500,
            detection_duration=800,
            measurements_per_point=30
        )
        
        if results:
            print("\n📊 Automated ODMR Results Summary:")
            print(f"Number of frequency points: {len(results['frequencies'])}")
            print(f"Frequency range: {min(results['frequencies']):.3f} - {max(results['frequencies']):.3f} GHz")
            print(f"Count rate range: {min(results['count_rates']):.0f} - {max(results['count_rates']):.0f} Hz")
            
            # Plot results
            experiments.plot_results('automated_odmr')
            
            print("✅ Automated ODMR sweep completed successfully")
        else:
            print("❌ Automated ODMR sweep failed")
            
    except Exception as e:
        print(f"❌ Automated ODMR sweep failed: {e}")
    finally:
        # Clean up
        if rigol.connected:
            rigol.set_rf_output(False)
            rigol.disconnect()
        if pulse_controller.is_connected:
            pulse_controller.disconnect()


def run_rabi_with_rigol():
    """Run Rabi oscillation experiment with RIGOL MW control."""
    print("\n💫 Running Rabi Oscillation with RIGOL MW Control...")
    
    # Initialize controllers
    pulse_controller = SwabianPulseController("192.168.0.201")
    rigol = RigolDSG836Controller("192.168.0.222")
    
    try:
        # Connect to instruments
        if not pulse_controller.connect():
            print("❌ Failed to connect to Pulse Streamer")
            return
            
        if not rigol.connect():
            print("❌ Failed to connect to RIGOL DSG836")
            return
        
        # Initialize experiments
        experiments = ODMRExperiments(pulse_controller, rigol)
        
        # Define Rabi parameters
        mw_durations = np.arange(10, 201, 10)  # 10-200 ns in 10 ns steps
        mw_frequency = 2.87e9  # 2.87 GHz
        
        print(f"📡 MW frequency: {mw_frequency/1e9:.3f} GHz")
        print(f"⏱️ MW duration range: {min(mw_durations)} - {max(mw_durations)} ns")
        
        # Run Rabi oscillation
        results = experiments.rabi_oscillation(
            mw_durations=list(mw_durations),
            mw_frequency=mw_frequency,
            laser_duration=1000,
            detection_duration=500
        )
        
        if results:
            print("\n📊 Rabi Results Summary:")
            print(f"Number of duration points: {len(results['durations'])}")
            print(f"Duration range: {min(results['durations'])} - {max(results['durations'])} ns")
            print(f"Count rate range: {min(results['count_rates']):.0f} - {max(results['count_rates']):.0f} Hz")
            
            # Plot results
            experiments.plot_results('rabi')
            
            print("✅ Rabi oscillation completed successfully")
        else:
            print("❌ Rabi oscillation failed")
            
    except Exception as e:
        print(f"❌ Rabi oscillation failed: {e}")
    finally:
        # Clean up
        if rigol.connected:
            rigol.set_rf_output(False)
            rigol.disconnect()
        if pulse_controller.is_connected:
            pulse_controller.disconnect()


def main():
    """Main function to run all examples."""
    print("🚀 RIGOL DSG836 + Swabian Pulse Streamer Integration Examples")
    print("=" * 60)
    
    # Test individual instruments
    print("\n1. Testing RIGOL DSG836 Connection...")
    rigol_ok = test_rigol_connection()
    
    if not rigol_ok:
        print("❌ RIGOL test failed. Please check connection and try again.")
        return
    
    # Test combined system
    print("\n2. Testing Combined System...")
    combined_ok = test_combined_system()
    
    if not combined_ok:
        print("❌ Combined system test failed. Please check both instruments.")
        return
    
    # Run ODMR experiments
    print("\n3. Running ODMR Experiments...")
    
    # Standard ODMR with manual frequency control
    run_odmr_with_rigol()
    
    # Automated ODMR sweep
    run_automated_odmr_sweep()
    
    # Rabi oscillation
    run_rabi_with_rigol()
    
    print("\n🎉 All RIGOL integration examples completed!")
    print("Your ODMR setup with RIGOL DSG836 is ready for experiments.")


if __name__ == "__main__":
    main() 