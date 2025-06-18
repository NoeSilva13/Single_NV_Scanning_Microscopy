"""
ODMR Experiment Examples using Swabian Pulse Streamer 8/2
---------------------------------------------------------
This file contains example experiments for ODMR measurements with NV centers.
Demonstrates various pulse sequences for different types of measurements.

Author: NV Lab
Date: 2025
"""

import numpy as np
import matplotlib.pyplot as plt
import time
from typing import List, Tuple, Dict, Optional
from swabian_pulse_streamer import SwabianPulseController
from rigol_dsg836 import RigolDSG836Controller

# TimeTagger imports for real data acquisition
from TimeTagger import createTimeTagger, Counter, createTimeTaggerVirtual, CountBetweenMarkers

class ODMRExperiments:
    """
    Class containing various ODMR experiment implementations.
    """
    
    def __init__(self, pulse_controller: SwabianPulseController, 
                 mw_generator: Optional[RigolDSG836Controller] = None):
        """
        Initialize ODMR experiments with a pulse controller and optional MW generator.
        
        Args:
            pulse_controller: Instance of SwabianPulseController
            mw_generator: Optional instance of RigolDSG836Controller for MW control
        """
        self.pulse_controller = pulse_controller
        self.mw_generator = mw_generator
        self.results = {}
        
        # Initialize TimeTagger for real data acquisition
        try:
            self.tagger = createTimeTagger()
            self.tagger.reset()
            print("✅ Connected to real TimeTagger device")
        except Exception as e:
            print("⚠️ Real TimeTagger not detected, using virtual device")
            self.tagger = createTimeTaggerVirtual("TimeTagger/time_tags_test.ttbin")
            self.tagger.run()
        
        # Set bin width to 5 ns and initialize counter
        #self.binwidth = int(5e9)  # 5 ns in ps
        #n_values = 1
        #self.counter = Counter(self.tagger, [1], self.binwidth, n_values)
    
    def _get_count_rate(self) -> float:
        """
        Get count rate from TimeTagger.
        
        Returns:
            Count rate in Hz
        """
        #counts = self.counter.getData()[0][0]/(self.binwidth/1e12)
        #return counts
        return 0
    
    def cleanup(self):
        """
        Clean up TimeTagger resources.
        Call this when done with experiments.
        """
        if hasattr(self, 'tagger'):
            self.tagger.reset()
            print("✅ TimeTagger resources cleaned up")
    
    def continuous_wave_odmr(self, 
                           mw_frequencies: List[float],
                           laser_duration: int = 2000,
                           mw_duration: int = 2000,
                           detection_duration: int = 1000,
                           laser_delay: int = 0,
                           mw_delay: int = 0,
                           detection_delay: int = 0,
                           sequence_interval: int = 10000,
                           repetitions: int = 100) -> Dict:
        """
        Perform continuous wave ODMR measurement.
        
        Args:
            mw_frequencies: List of microwave frequencies to sweep (Hz)
            laser_duration: Duration of laser pulse in ns
            detection_duration: Duration of detection window in ns
            measurements_per_point: Number of measurements per frequency point
            
        Returns:
            Dictionary containing frequencies and corresponding count rates
        """
        print("🔬 Starting Continuous Wave ODMR measurement...")
        
        frequencies = []
        count_rates = []

        self.counter = CountBetweenMarkers(tagger=self.tagger, click_channel=1, begin_channel=3, end_channel=-3, n_values=repetitions)

        for freq in mw_frequencies:
            print(f"📡 Measuring at {freq/1e6:.2f} MHz")
            
            # Create CW ODMR sequence
            sequence, total_duration = self.pulse_controller.create_odmr_sequence(
                laser_duration=laser_duration,
                mw_duration=mw_duration,  # MW on during detection
                detection_duration=detection_duration,
                laser_delay=laser_delay,
                mw_delay=mw_delay,  # MW after laser
                detection_delay=detection_delay,
                sequence_interval=sequence_interval,
                repetitions=repetitions
            )
            
            if sequence:
                # Set MW frequency on the RIGOL signal generator
                if self.mw_generator:
                    self.mw_generator.set_odmr_frequency(freq / 1e9)  # Convert Hz to GHz
                    self.mw_generator.set_rf_output(True)
                
                
                self.counter.clear()
                print(f"{self.counter.getData()}")
                self.pulse_controller.run_sequence(sequence)
                while self.counter.ready() == False:
                    print("Waiting for sequence to complete")
                    time.sleep(total_duration/1e9)  # Let sequence complete
                    
                self.pulse_controller.stop_sequence()
                print(f"{self.counter.getData()}")
                # Get real count rate from TimeTagger
                count_rate = np.mean(self.counter.getData())
                print(f"Count rate: {count_rate} Hz")
                
                frequencies.append(freq)
                count_rates.append(count_rate)
                
                
                
                # Turn off RF output after measurement
                if self.mw_generator:
                    self.mw_generator.set_rf_output(False)
                
                time.sleep(0.05)
        
        self.results['cw_odmr'] = {
            'frequencies': frequencies,
            'count_rates': count_rates
        }
        
        print("✅ CW ODMR measurement completed")
        return self.results['cw_odmr']
    
    def rabi_oscillation(self,
                        mw_durations: List[int],
                        mw_frequency: float = 2.87e9,
                        laser_duration: int = 1000,
                        detection_duration: int = 500) -> Dict:
        """
        Perform Rabi oscillation measurement.
        
        Args:
            mw_durations: List of MW pulse durations in ns
            mw_frequency: MW frequency in Hz
            laser_duration: Laser pulse duration in ns
            detection_duration: Detection window duration in ns
            
        Returns:
            Dictionary containing MW durations and count rates
        """
        print("🔬 Starting Rabi oscillation measurement...")
        
        durations = []
        count_rates = []
        
        # Set MW frequency and power for Rabi oscillation
        if self.mw_generator:
            self.mw_generator.set_odmr_frequency(mw_frequency / 1e9)  # Convert Hz to GHz
            self.mw_generator.prepare_for_odmr(mw_frequency / 1e9, -10.0)
        
        for mw_duration in mw_durations:
            print(f"⏱️ MW duration: {mw_duration} ns")
            
            # Create Rabi sequence
            sequence = self.pulse_controller.create_odmr_sequence(
                laser_duration=laser_duration,
                mw_duration=mw_duration,
                detection_duration=detection_duration,
                laser_delay=0,
                mw_delay=laser_duration + 1000,  # 1 µs after laser
                detection_delay=laser_duration + 1000 + mw_duration + 100,
                repetitions=1000  # More repetitions for better statistics
            )
            
            if sequence:
                # Enable RF output for this measurement
                if self.mw_generator:
                    self.mw_generator.set_rf_output(True)
                
                self.pulse_controller.run_sequence(sequence)
                time.sleep(0.1)
                
                # Get real count rate from TimeTagger
                count_rate = self._get_count_rate()
                
                durations.append(mw_duration)
                count_rates.append(count_rate)
                
                self.pulse_controller.stop_sequence()
                
                # Turn off RF output after measurement
                if self.mw_generator:
                    self.mw_generator.set_rf_output(False)
                    
                time.sleep(0.05)
        
        self.results['rabi'] = {
            'durations': durations,
            'count_rates': count_rates
        }
        
        print("✅ Rabi oscillation measurement completed")
        return self.results['rabi']
    
    def ramsey_experiment(self,
                         tau_delays: List[int],
                         pi_half_duration: int = 25,
                         mw_frequency: float = 2.87e9,
                         laser_duration: int = 1000,
                         detection_duration: int = 500) -> Dict:
        """
        Perform Ramsey coherence measurement.
        
        Args:
            tau_delays: List of delay times between pi/2 pulses in ns
            pi_half_duration: Duration of pi/2 pulse in ns
            mw_frequency: MW frequency in Hz
            laser_duration: Laser pulse duration in ns
            detection_duration: Detection window duration in ns
            
        Returns:
            Dictionary containing delay times and count rates
        """
        print("🔬 Starting Ramsey coherence measurement...")
        
        delays = []
        count_rates = []
        
        for tau in tau_delays:
            print(f"⏳ Delay time: {tau} ns")
            
            # Create custom Ramsey sequence
            sequence = self._create_ramsey_sequence(
                pi_half_duration, tau, laser_duration, detection_duration
            )
            
            if sequence:
                self.pulse_controller.run_sequence(sequence)
                time.sleep(0.1)
                
                # Get real count rate from TimeTagger
                count_rate = self._get_count_rate()
                
                delays.append(tau)
                count_rates.append(count_rate)
                
                self.pulse_controller.stop_sequence()
                time.sleep(0.05)
        
        self.results['ramsey'] = {
            'delays': delays,
            'count_rates': count_rates
        }
        
        print("✅ Ramsey measurement completed")
        return self.results['ramsey']
    
    def spin_echo(self,
                  tau_delays: List[int],
                  pi_half_duration: int = 25,
                  pi_duration: int = 50,
                  laser_duration: int = 1000,
                  detection_duration: int = 500) -> Dict:
        """
        Perform spin echo (Hahn echo) measurement.
        
        Args:
            tau_delays: List of delay times in ns
            pi_half_duration: Duration of pi/2 pulse in ns
            pi_duration: Duration of pi pulse in ns
            laser_duration: Laser pulse duration in ns
            detection_duration: Detection window duration in ns
            
        Returns:
            Dictionary containing delay times and count rates
        """
        print("🔬 Starting Spin Echo measurement...")
        
        delays = []
        count_rates = []
        
        for tau in tau_delays:
            print(f"⏳ Delay time: {tau} ns")
            
            # Create spin echo sequence
            sequence = self._create_spin_echo_sequence(
                pi_half_duration, pi_duration, tau, laser_duration, detection_duration
            )
            
            if sequence:
                self.pulse_controller.run_sequence(sequence)
                time.sleep(0.1)
                
                # Get real count rate from TimeTagger
                count_rate = self._get_count_rate()
                
                delays.append(tau)
                count_rates.append(count_rate)
                
                self.pulse_controller.stop_sequence()
                time.sleep(0.05)
        
        self.results['spin_echo'] = {
            'delays': delays,
            'count_rates': count_rates
        }
        
        print("✅ Spin Echo measurement completed")
        return self.results['spin_echo']
    
    def automated_odmr_sweep(self,
                           start_freq_ghz: float = 2.8,
                           stop_freq_ghz: float = 2.9,
                           num_points: int = 101,
                           power_dbm: float = -10.0,
                           laser_duration: int = 2000,
                           detection_duration: int = 1000,
                           measurements_per_point: int = 100) -> Dict:
        """
        Perform automated ODMR sweep using RIGOL's internal frequency sweep.
        
        Args:
            start_freq_ghz: Start frequency in GHz
            stop_freq_ghz: Stop frequency in GHz
            num_points: Number of frequency points
            power_dbm: MW power in dBm
            laser_duration: Duration of laser pulse in ns
            detection_duration: Duration of detection window in ns
            measurements_per_point: Number of measurements per frequency point
            
        Returns:
            Dictionary containing frequencies and corresponding count rates
        """
        if not self.mw_generator:
            print("❌ MW generator not available for automated sweep")
            return {}
        
        print(f"🔬 Starting automated ODMR sweep: {start_freq_ghz}-{stop_freq_ghz} GHz")
        
        # Setup frequency sweep on RIGOL
        self.mw_generator.frequency_sweep_setup(
            start_freq_ghz, stop_freq_ghz, num_points, power_dbm
        )
        
        # Create ODMR sequence for each frequency point
        sequence = self.pulse_controller.create_odmr_sequence(
            laser_duration=laser_duration,
            mw_duration=detection_duration,
            detection_duration=detection_duration,
            laser_delay=0,
            mw_delay=laser_duration + 100,
            detection_delay=laser_duration + 100,
            repetitions=measurements_per_point
        )
        
        frequencies = []
        count_rates = []
        
        # Enable RF output
        self.mw_generator.set_rf_output(True)
        
        for i in range(num_points):
            # Trigger next frequency point
            self.mw_generator.trigger_sweep_point()
            
            # Get current frequency for logging
            current_freq = start_freq_ghz + (stop_freq_ghz - start_freq_ghz) * i / (num_points - 1)
            print(f"📡 Point {i+1}/{num_points}: {current_freq:.4f} GHz")
            
            if sequence:
                self.pulse_controller.run_sequence(sequence)
                time.sleep(0.1)
                
                # Get real count rate from TimeTagger
                count_rate = self._get_count_rate()
                
                frequencies.append(current_freq)
                count_rates.append(count_rate)
                
                self.pulse_controller.stop_sequence()
                time.sleep(0.05)
        
        # Turn off RF output
        self.mw_generator.set_rf_output(False)
        
        # Turn off sweep mode
        self.mw_generator.write(":SWE:STAT OFF")
        
        self.results['automated_odmr'] = {
            'frequencies': frequencies,
            'count_rates': count_rates
        }
        
        print("✅ Automated ODMR sweep completed")
        return self.results['automated_odmr']
    
    def _create_ramsey_sequence(self, pi_half_duration: int, tau: int, 
                               laser_duration: int, detection_duration: int):
        """Create a Ramsey pulse sequence: pi/2 - tau - pi/2 - detection"""
        try:
            from pulsestreamer import Sequence
            sequence = Sequence()
            
            # Laser initialization
            sequence.setDigital(self.pulse_controller.CHANNEL_AOM, True)
            sequence.wait(laser_duration)
            sequence.setDigital(self.pulse_controller.CHANNEL_AOM, False)
            
            # Wait for NV to relax
            sequence.wait(1000)  # 1 µs
            
            # First pi/2 pulse
            sequence.setDigital(self.pulse_controller.CHANNEL_MW, True)
            sequence.wait(pi_half_duration)
            sequence.setDigital(self.pulse_controller.CHANNEL_MW, False)
            
            # Free evolution time
            sequence.wait(tau)
            
            # Second pi/2 pulse
            sequence.setDigital(self.pulse_controller.CHANNEL_MW, True)
            sequence.wait(pi_half_duration)
            sequence.setDigital(self.pulse_controller.CHANNEL_MW, False)
            
            # Detection
            sequence.wait(100)  # Small delay
            sequence.setDigital(self.pulse_controller.CHANNEL_SPD, True)
            sequence.wait(detection_duration)
            sequence.setDigital(self.pulse_controller.CHANNEL_SPD, False)
            
            return sequence
        except:
            return None
    
    def _create_spin_echo_sequence(self, pi_half_duration: int, pi_duration: int, 
                                  tau: int, laser_duration: int, detection_duration: int):
        """Create a spin echo sequence: pi/2 - tau - pi - tau - detection"""
        try:
            from pulsestreamer import Sequence
            sequence = Sequence()
            
            # Laser initialization
            sequence.setDigital(self.pulse_controller.CHANNEL_AOM, True)
            sequence.wait(laser_duration)
            sequence.setDigital(self.pulse_controller.CHANNEL_AOM, False)
            
            # Wait for NV to relax
            sequence.wait(1000)  # 1 µs
            
            # First pi/2 pulse
            sequence.setDigital(self.pulse_controller.CHANNEL_MW, True)
            sequence.wait(pi_half_duration)
            sequence.setDigital(self.pulse_controller.CHANNEL_MW, False)
            
            # First tau delay
            sequence.wait(tau)
            
            # Pi pulse (refocusing)
            sequence.setDigital(self.pulse_controller.CHANNEL_MW, True)
            sequence.wait(pi_duration)
            sequence.setDigital(self.pulse_controller.CHANNEL_MW, False)
            
            # Second tau delay
            sequence.wait(tau)
            
            # Detection
            sequence.wait(100)  # Small delay
            sequence.setDigital(self.pulse_controller.CHANNEL_SPD, True)
            sequence.wait(detection_duration)
            sequence.setDigital(self.pulse_controller.CHANNEL_SPD, False)
            
            return sequence
        except:
            return None
    
    # Simulation functions (replace with actual detector readout)
    def _simulate_odmr_signal(self, frequency: float, resonance_freq: float) -> float:
        """Simulate ODMR signal with Lorentzian lineshape"""
        linewidth = 2e6  # 2 MHz linewidth
        contrast = 0.3   # 30% contrast
        baseline = 1000  # baseline counts
        
        signal = baseline * (1 - contrast * linewidth**2 / 
                           ((frequency - resonance_freq)**2 + linewidth**2))
        return signal + np.random.normal(0, np.sqrt(signal))
    
    def _simulate_rabi_signal(self, duration: int, pi_pulse_duration: int) -> float:
        """Simulate Rabi oscillation"""
        baseline = 1000
        contrast = 0.5
        
        # Rabi frequency based on pi pulse duration
        rabi_freq = 1 / (2 * pi_pulse_duration * 1e-9)  # Hz
        
        signal = baseline * (1 - contrast * np.cos(2 * np.pi * rabi_freq * duration * 1e-9))
        return signal + np.random.normal(0, np.sqrt(signal))
    
    def _simulate_ramsey_signal(self, tau: int, t2_star: int) -> float:
        """Simulate Ramsey fringes with T2* decay"""
        baseline = 1000
        contrast = 0.5
        detuning = 1e6  # 1 MHz detuning
        
        decay = np.exp(-tau * 1e-9 / (t2_star * 1e-9))
        oscillation = np.cos(2 * np.pi * detuning * tau * 1e-9)
        
        signal = baseline * (1 - contrast * decay * oscillation)
        return signal + np.random.normal(0, np.sqrt(signal))
    
    def _simulate_spin_echo_signal(self, tau: int, t2: int) -> float:
        """Simulate spin echo decay"""
        baseline = 1000
        contrast = 0.5
        
        decay = np.exp(-2 * tau * 1e-9 / (t2 * 1e-9))  # Total evolution time is 2*tau
        
        signal = baseline * (1 - contrast * decay)
        return signal + np.random.normal(0, np.sqrt(signal))
    
    def plot_results(self, experiment_type: str):
        """Plot the results of a specific experiment"""
        if experiment_type not in self.results:
            print(f"❌ No results found for {experiment_type}")
            return
        
        data = self.results[experiment_type]
        
        plt.figure(figsize=(10, 6))
        
        if experiment_type == 'cw_odmr' or experiment_type == 'automated_odmr':
            if experiment_type == 'cw_odmr':
                freqs = np.array(data['frequencies'])/1e6  # Convert Hz to MHz
                title = 'Continuous Wave ODMR'
            else:
                freqs = np.array(data['frequencies']) * 1000  # Convert GHz to MHz
                title = 'Automated ODMR Sweep (RIGOL)'
            
            plt.plot(freqs, data['count_rates'], 'bo-')
            plt.xlabel('Frequency (MHz)')
            plt.ylabel('Count Rate (Hz)')
            plt.title(title)
            
        elif experiment_type == 'rabi':
            plt.plot(data['durations'], data['count_rates'], 'ro-')
            plt.xlabel('MW Duration (ns)')
            plt.ylabel('Count Rate (Hz)')
            plt.title('Rabi Oscillation')
            
        elif experiment_type == 'ramsey':
            plt.plot(np.array(data['delays'])/1000, data['count_rates'], 'go-')
            plt.xlabel('Delay (µs)')
            plt.ylabel('Count Rate (Hz)')
            plt.title('Ramsey Coherence')
            
        elif experiment_type == 'spin_echo':
            plt.plot(np.array(data['delays'])/1000, data['count_rates'], 'mo-')
            plt.xlabel('Delay (µs)')
            plt.ylabel('Count Rate (Hz)')
            plt.title('Spin Echo')
        
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()


def run_example_experiments():
    """Run example ODMR experiments with RIGOL integration"""
    print("🚀 Starting ODMR Experiment Examples with RIGOL DSG836...")
    
    # Initialize pulse controller
    controller = SwabianPulseController()
    
    if not controller.is_connected:
        print("❌ Pulse controller not connected. Running in simulation mode.")
        return
    
    # Initialize RIGOL signal generator
    try:
        rigol = RigolDSG836Controller("192.168.0.222")
        if rigol.connect():
            print("✅ RIGOL DSG836 connected successfully")
        else:
            print("⚠️  RIGOL DSG836 not connected. Running without MW control.")
            rigol = None
    except Exception as e:
        print(f"⚠️  RIGOL DSG836 connection failed: {e}. Running without MW control.")
        rigol = None
    
    # Initialize experiments with both controllers
    experiments = ODMRExperiments(controller, rigol)
    
    try:
        # 1. CW ODMR
        print("\n" + "="*50)
        frequencies = np.linspace(2.85e9, 2.89e9, 50)  # 2.85-2.89 GHz
        cw_result = experiments.continuous_wave_odmr(frequencies, laser_duration=5000, mw_duration=5000, mw_delay=5000, detection_duration=5000, repetitions=5000)
        experiments.plot_results('cw_odmr')
        
        # 2. Rabi oscillation
        #print("\n" + "="*50)
        #mw_durations = np.arange(0, 200, 5)  # 0-200 ns in 5 ns steps
        #rabi_result = experiments.rabi_oscillation(mw_durations)
        #experiments.plot_results('rabi')
        
        # 3. Ramsey experiment
        #print("\n" + "="*50)
        #tau_delays = np.arange(0, 2000, 50)  # 0-2 µs in 50 ns steps
        #ramsey_result = experiments.ramsey_experiment(tau_delays)
        #experiments.plot_results('ramsey')
        
        # 4. Spin echo
        #print("\n" + "="*50)
        #tau_delays = np.arange(100, 10000, 200)  # 100 ns - 10 µs
        #echo_result = experiments.spin_echo(tau_delays)
        #experiments.plot_results('spin_echo')
        
        print("\n✅ All example experiments completed!")
        
    except Exception as e:
        print(f"❌ Error during experiments: {e}")
    
    finally:
        # Clean up connections
        experiments.cleanup()  # Clean up TimeTagger resources
        if rigol:
            rigol.set_rf_output(False)  # Safety: turn off RF output
            rigol.disconnect()
        controller.disconnect()


if __name__ == "__main__":
    run_example_experiments() 