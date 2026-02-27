"""
ODMR Experiment Examples using Swabian Pulse Streamer 8/2
---------------------------------------------------------
This file contains example experiments for ODMR measurements with NV centers.
Demonstrates various pulse sequences for different types of measurements.

Author: Javier Noé Ramos Silva
Contact: jramossi@uci.edu
Lab: Burke Lab, Department of Electrical Engineering and Computer Science, University of California, Irvine
Date: 2025
"""

import numpy as np
import matplotlib.pyplot as plt
import time
import sys
import os
from typing import List, Tuple, Dict, Optional, Callable
# Try relative imports first (when used as package)
try:
    from .swabian_pulse_streamer import SwabianPulseController
    from .rigol_dsg836 import RigolDSG836Controller
    from pulsestreamer import OutputState
except ImportError:
    # Fall back to direct imports (when run as script)
    from swabian_pulse_streamer import SwabianPulseController
    from rigol_dsg836 import RigolDSG836Controller
    from pulsestreamer import OutputState

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from odmr_data_manager import ODMRDataManager

# TimeTagger imports for real data acquisition
import TimeTagger

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
        self.data_manager = ODMRDataManager()
        
        # Initialize TimeTagger for real data acquisition
        try:
            self.tagger = TimeTagger.createTimeTaggerNetwork("localhost")
            print("✅ Connected to Network TimeTagger device")
        except Exception as e:
            print(f"⚠️ Network TimeTagger not detected: {str(e)}")
            self.tagger = None

        if self.tagger is None:
            try:
                self.tagger = TimeTagger.createTimeTagger()
                self.tagger.reset()
                print("✅ Connected to real TimeTagger device")
            except Exception as e:
                print(f"⚠️ Real TimeTagger not detected: {str(e)}")
                self.tagger = TimeTagger.createTimeTaggerVirtual("TimeTagger/time_tags_test.ttbin")
                self.tagger.run()
                print("✅ Virtual TimeTagger started")
    
    def cleanup(self):
        """
        Clean up TimeTagger resources.
        Call this when done with experiments.
        """
        if hasattr(self, 'tagger'):
            self.tagger.reset()
            print("✅ TimeTagger resources cleaned up")
    
    # Maps internal result keys to ODMRDataManager experiment types and x-data keys
    _SAVE_MAP = {
        'cw_odmr': ('odmr', 'frequencies'),
        'odmr':    ('odmr', 'frequencies'),
        'rabi':    ('rabi', 'durations'),
        't1_decay': ('t1', 'delays'),
    }

    def _save_results(self, result_key: str, result: Dict):
        """Save experiment results using ODMRDataManager."""
        dm_type, x_key = self._SAVE_MAP[result_key]
        try:
            saved_file = self.data_manager.save_experiment_data(
                experiment_type=dm_type,
                x_data=result[x_key],
                count_rates=result['count_rates'],
                parameters=result.get('parameters', {})
            )
            print(f"Data saved to: {saved_file}")
        except Exception as e:
            print(f"Warning: Could not save data: {e}")

    def cw_odmr(self, 
                  mw_frequencies: List[float],
                  acquisition_time: float = 1.0,  # Time per point in seconds
                  mw_power: float = -10.0) -> Dict:  # Power in dBm
        """
        Perform Continuous Wave ODMR measurement.
        
        In CW-ODMR, both laser and microwave are kept on continuously while sweeping frequencies.
        For each frequency point, counts are accumulated for the specified acquisition time.
        No pulse sequence is used - just continuous signals.
        
        Args:
            mw_frequencies: List of microwave frequencies to sweep (Hz)
            acquisition_time: How long to count at each frequency point (seconds)
            mw_power: Microwave power (dBm)
            
        Returns:
            Dictionary containing frequencies and corresponding count rates
        """
        print("🔬 Starting CW-ODMR measurement...")
        
        frequencies = []
        count_rates = []
        
        # Initialize TimeTagger counter
        self.counter = TimeTagger.Counter(tagger=self.tagger, channels=[1], binwidth=acquisition_time*1e12, n_values=1)
        
        # Turn on laser (AOM)
        self.pulse_controller.pulse_streamer.constant(OutputState([0, 1, 2], 0, 0))
        time.sleep(5)  # Let laser stabilize
        print("Laser on")

        # Set initial MW power
        if self.mw_generator:
            self.mw_generator.set_power(mw_power)
            self.mw_generator.set_rf_output(True)
        
        try:
            for freq in mw_frequencies:
                print(f"📡 Measuring at {freq/1e6:.2f} MHz")
                
                # Set MW frequency
                if self.mw_generator:
                    self.mw_generator.set_odmr_frequency(freq / 1e9)  # Convert Hz to GHz
                    
                # Clear counter and wait for acquisition
                self.counter.clear()
                self.counter.startFor(acquisition_time*1e12)
                self.counter.waitUntilFinished(timeout=-1)
                
                counts = self.counter.getDataNormalized()[0][0]
                print(f"Counts: {counts}")
                
                frequencies.append(freq)
                count_rates.append(counts)
                
        finally:
            # Clean up: turn off MW and laser
            if self.mw_generator:
                self.mw_generator.set_rf_output(False)
            self.pulse_controller.pulse_streamer.constant(OutputState.ZERO())  # All off
        
        # Store and return results
        self.results['cw_odmr'] = {
            'frequencies': frequencies,
            'count_rates': count_rates,
            'parameters': {
                'acquisition_time': acquisition_time,
                'mw_power': mw_power
            }
        }
        
        self._save_results('cw_odmr', self.results['cw_odmr'])
        print("✅ CW-ODMR measurement completed")
        return self.results['cw_odmr']
    
    def odmr(self, 
                           mw_frequencies: List[float],
                           laser_duration: int = 2000,
                           mw_duration: int = 2000,
                           detection_duration: int = 1000,
                           laser_delay: int = 0,
                           mw_delay: int = 0,
                           detection_delay: int = 0,
                           sequence_interval: int = 10000,
                           repetitions: int = 100,
                           progress_callback: Optional[Callable] = None) -> Dict:
        """
        Perform ODMR (Optically Detected Magnetic Resonance) measurement.
        
        This function performs ODMR measurements by sweeping through microwave
        frequencies and measuring the fluorescence count rate at each frequency.
        The measurement sequence consists of laser excitation, microwave irradiation,
        and fluorescence detection phases.
        
        Args:
            mw_frequencies: List of microwave frequencies to sweep (Hz)
            laser_duration: Duration of laser excitation pulse in ns
            mw_duration: Duration of microwave pulse in ns
            detection_duration: Duration of fluorescence detection window in ns
            laser_delay: Delay before laser pulse in ns
            mw_delay: Delay before microwave pulse in ns (relative to laser)
            detection_delay: Delay before detection window in ns
            sequence_interval: Interval between measurement sequences in ns
            repetitions: Number of sequence repetitions per frequency point
            
        Returns:
            Dictionary containing frequencies and corresponding count rates
        """
        print("🔬 Starting ODMR measurement...")
        
        frequencies = []
        count_rates = []
        # Set up TimeTagger counter for ODMR measurements
        self.counter = TimeTagger.CountBetweenMarkers(tagger=self.tagger, click_channel=1, begin_channel=2, end_channel=-2, n_values=repetitions)
        
        if self.mw_generator:
            self.mw_generator.prepare_for_odmr(mw_frequencies[0] / 1e9, -10.0)
        
        for freq in mw_frequencies:
            print(f"📡 Measuring at {freq/1e6:.2f} MHz")
            
            # Create ODMR sequence
            sequence, total_duration = self.pulse_controller.create_odmr_sequence(
                laser_duration=laser_duration,
                mw_duration=mw_duration,  # MW on during detection
                detection_duration=detection_duration,
                laser_delay=laser_delay,
                mw_delay=mw_delay,  # MW after laser
                detection_delay=detection_delay,
                sequence_interval=sequence_interval
            )
            # Only plot sequence when running in main thread (not in GUI worker threads)
            #if threading.current_thread() is threading.main_thread():
            #    sequence.plot()
            # Sleep time if not the while loop fails  
            time.sleep(0.2)
            
            if sequence:
                # Enable RF output for this measurement
                if self.mw_generator:
                    self.mw_generator.set_odmr_frequency(freq / 1e9)  # Convert Hz to GHz
                    self.mw_generator.set_rf_output(True)
                    
                self.counter.start()
                ready = False
                self.pulse_controller.run_sequence(sequence, repetitions)
                
                while ready is False:
                    time.sleep(.2)
                    ready = self.counter.ready()
                    information = self.counter.getBinWidths()
                    print(f"Information: {information}")
                    print(f"Ready: {ready}")
                    counts = self.counter.getData()
                    print(f"Counts: {counts}")
                    
                self.counter.clear()
                
                # Get real count rate from TimeTagger
                count_rate = np.mean(counts)/(np.mean(information)*1e-12)
                print(f"Count rate: {count_rate} Hz")
                
                frequencies.append(freq)
                count_rates.append(count_rate)
                
                if progress_callback:
                    progress_callback(frequencies.copy(), count_rates.copy())
                
                # Turn off RF output after measurement
                if self.mw_generator:
                    self.mw_generator.set_rf_output(False)
                    
                time.sleep(0.05)
            
        self.results['odmr'] = {
            'frequencies': frequencies,
            'count_rates': count_rates,
            'parameters': {
                'laser_duration': laser_duration,
                'mw_duration': mw_duration,
                'detection_duration': detection_duration,
                'laser_delay': laser_delay,
                'mw_delay': mw_delay,
                'detection_delay': detection_delay,
                'sequence_interval': sequence_interval,
                'repetitions': repetitions
            }
        }
        self._save_results('odmr', self.results['odmr'])
        print(f"Count rates: {count_rates}")
        print(f"Frequencies: {frequencies}")
        print("✅ ODMR measurement completed")
        return self.results['odmr']
    
    def rabi_oscillation(self,
                        mw_durations: List[int],
                        mw_frequency: float = 2.87e9,
                        laser_duration: int = 1000,
                        detection_duration: int = 500,
                        laser_delay: int = 0,
                        mw_delay: Optional[int] = None,
                        detection_delay: Optional[int] = None,
                        sequence_interval: int = 10000,
                        repetitions: int = 1000,
                        progress_callback: Optional[Callable] = None) -> Dict:
        """
        Perform Rabi oscillation measurement.
        
        Args:
            mw_durations: List of MW pulse durations in ns
            mw_frequency: MW frequency in Hz
            laser_duration: Laser pulse duration in ns
            detection_duration: Detection window duration in ns
            laser_delay: Delay before laser pulse in ns
            mw_delay: Delay before MW pulse in ns
            detection_delay: Delay after MW pulse in ns
            sequence_interval: Interval between sequences in ns
            repetitions: Number of repetitions
            
        Returns:
            Dictionary containing MW durations and count rates
        """
        print("🔬 Starting Rabi oscillation measurement...")

        durations = []
        count_rates = []
        # Set up TimeTagger counter for Rabi measurements
        self.counter = TimeTagger.CountBetweenMarkers(tagger=self.tagger, click_channel=1, begin_channel=2, end_channel=-2, n_values=repetitions)
        # Set MW frequency and power for Rabi oscillation
        if self.mw_generator:
            self.mw_generator.set_odmr_frequency(mw_frequency / 1e9)  # Convert Hz to GHz
            self.mw_generator.prepare_for_odmr(mw_frequency / 1e9, -10.0)

        for mw_duration in mw_durations:
            print(f"⏱️ MW duration: {mw_duration} ns")

            # Calculate default delays for this duration if not provided
            local_mw_delay = mw_delay if mw_delay is not None else laser_duration + 1000
            local_detection_delay = detection_delay if detection_delay is not None else local_mw_delay + mw_duration + 100

            # Create Rabi sequence
            sequence, total_duration = self.pulse_controller.create_odmr_sequence(
                laser_duration=laser_duration,
                mw_duration=mw_duration,
                detection_duration=detection_duration,
                laser_delay=laser_delay,
                mw_delay=local_mw_delay,
                detection_delay=local_detection_delay,
                sequence_interval=sequence_interval
            )
            # Only plot sequence when running in main thread (not in GUI worker threads)
            #if threading.current_thread() is threading.main_thread():
            #    sequence.plot()
            # Sleep time if not the while loop fails  
            time.sleep(0.2)

            if sequence:
                # Enable RF output for this measurement
                if self.mw_generator:
                    self.mw_generator.set_rf_output(True)

                self.counter.start()
                ready = False
                self.pulse_controller.run_sequence(sequence, repetitions)

                while ready is False:
                    time.sleep(.2)
                    ready = self.counter.ready()
                    information = self.counter.getBinWidths()
                    print(f"Information: {information}")
                    print(f"Ready: {ready}")
                    counts = self.counter.getData()
                    print(f"Counts: {counts}")

                self.counter.clear()

                # Get real count rate from TimeTagger
                count_rate = np.mean(counts)/(np.mean(information)*1e-12)
                print(f"Count rate: {count_rate} Hz")

                durations.append(mw_duration)
                count_rates.append(count_rate)

                if progress_callback:
                    progress_callback(durations.copy(), count_rates.copy())

                # Turn off RF output after measurement
                if self.mw_generator:
                    self.mw_generator.set_rf_output(False)

                time.sleep(0.05)
        
        self.results['rabi'] = {
            'durations': durations,
            'count_rates': count_rates,
            'parameters': {
                'mw_frequency': mw_frequency,
                'laser_duration': laser_duration,
                'detection_duration': detection_duration,
                'laser_delay': laser_delay,
                'mw_delay': mw_delay,
                'detection_delay': detection_delay,
                'sequence_interval': sequence_interval,
                'repetitions': repetitions
            }
        }
        self._save_results('rabi', self.results['rabi'])
        print("✅ Rabi oscillation measurement completed")
        return self.results['rabi']
    
        
    def t1_decay(self,
                 delay_times: List[int],
                 init_laser_duration: int = 1000,
                 readout_laser_duration: int = 1000,
                 detection_duration: int = 500,
                 init_laser_delay: int = 0,
                 readout_laser_delay: Optional[int] = None,
                 detection_delay: Optional[int] = None,
                 sequence_interval: int = 10000,
                 repetitions: int = 1000,
                 progress_callback: Optional[Callable] = None) -> Dict:
        """
        Perform T1 decay time measurement.
        
        T1 decay measures the relaxation time from excited state to ground state.
        Sequence: Init laser -> variable delay -> readout laser + detection
        
        Args:
            delay_times: List of delay times between init and readout in ns
            init_laser_duration: Duration of initialization laser pulse in ns
            readout_laser_duration: Duration of readout laser pulse in ns
            detection_duration: Duration of detection window in ns
            init_laser_delay: Delay before initialization laser in ns
            readout_laser_delay: Delay before readout laser in ns (auto-calculated if None)
            detection_delay: Delay before detection in ns (auto-calculated if None)
            sequence_interval: Interval between sequences in ns
            repetitions: Number of repetitions
            
        Returns:
            Dictionary containing delay times and count rates
        """
        print("🔬 Starting T1 decay time measurement...")
        
        delays = []
        count_rates = []
        # Set up TimeTagger counter for T1 decay measurements
        self.counter = TimeTagger.CountBetweenMarkers(tagger=self.tagger, click_channel=1, begin_channel=2, end_channel=-2, n_values=repetitions)

        # Pre-calculate the maximum sequence duration to maintain constant repetition period
        max_delay = max(delay_times)
        max_readout_delay = readout_laser_delay if readout_laser_delay is not None else init_laser_delay + init_laser_duration + max_delay
        max_detection_delay = detection_delay if detection_delay is not None else max_readout_delay
        
        # Calculate maximum sequence duration (aligned to 8ns)
        max_seq_duration = self.pulse_controller.align_timing(
            max(
                init_laser_delay + init_laser_duration,
                max_readout_delay + readout_laser_duration,
                max_detection_delay + detection_duration
            )
        )
        
        # Calculate the constant total period (sequence + interval) that will be used for all delays
        constant_total_period = max_seq_duration + self.pulse_controller.align_timing(sequence_interval)
        
        print(f"📏 Maximum sequence duration: {max_seq_duration} ns (for delay={max_delay} ns)")
        print(f"📏 Constant total period per repetition: {constant_total_period} ns")
        
        for delay_time in delay_times:
            print(f"⏱️ Delay time: {delay_time} ns")
            
            # Calculate readout laser delay if not provided
            local_readout_delay = readout_laser_delay if readout_laser_delay is not None else init_laser_delay + init_laser_duration + delay_time
            local_detection_delay = detection_delay if detection_delay is not None else local_readout_delay

            # For shorter delays, we need to add extra waiting time to maintain constant period
            # The total period = max_seq_duration + adjusted_interval should always be constant
            adjusted_interval = constant_total_period - max_seq_duration
            adjusted_interval = self.pulse_controller.align_timing(adjusted_interval)
            
            print(f"Using fixed seq duration: {max_seq_duration} ns, delay time: {delay_time} ns, Interval: {adjusted_interval} ns, Total period: {max_seq_duration + adjusted_interval} ns")

            # Create T1 decay sequence with fixed sequence duration
            sequence, total_duration = self.pulse_controller._create_t1_sequence(
                init_laser_duration=init_laser_duration,
                readout_laser_duration=readout_laser_duration,
                detection_duration=detection_duration,
                delay_time=delay_time,
                init_laser_delay=init_laser_delay,
                readout_laser_delay=local_readout_delay,
                detection_delay=local_detection_delay,
                sequence_interval=adjusted_interval,
                fixed_seq_duration=max_seq_duration
            )
            # Only plot sequence when running in main thread (not in GUI worker threads)
            #if threading.current_thread() is threading.main_thread():
            #sequence.plot()
            # Sleep time if not the while loop fails  
            time.sleep(0.2)
            
            if sequence:
                
                self.counter.start()
                ready = False
                self.pulse_controller.run_sequence(sequence, n_runs=repetitions)
                
                while ready is False:
                    time.sleep(.2)
                    ready = self.counter.ready()
                    information = self.counter.getBinWidths()
                    print(f"Information: {information}")
                    print(f"Ready: {ready}")
                    counts = self.counter.getData()
                    print(f"Counts: {counts}")
                    
                self.counter.clear()
                
                # Get real count rate from TimeTagger
                count_rate = np.mean(counts)/(np.mean(information)*1e-12)
                print(f"Count rate: {count_rate} Hz")
                
                delays.append(delay_time)
                count_rates.append(count_rate)
                
                if progress_callback:
                    progress_callback(delays.copy(), count_rates.copy())
                
                time.sleep(0.05)
        
        self.results['t1_decay'] = {
            'delays': delays,
            'count_rates': count_rates,
            'parameters': {
                'init_laser_duration': init_laser_duration,
                'readout_laser_duration': readout_laser_duration,
                'detection_duration': detection_duration,
                'init_laser_delay': init_laser_delay,
                'readout_laser_delay': readout_laser_delay,
                'detection_delay': detection_delay,
                'sequence_interval': sequence_interval,
                'repetitions': repetitions
            }
        }
        self._save_results('t1_decay', self.results['t1_decay'])
        print("✅ T1 decay measurement completed")
        return self.results['t1_decay']
    
    def plot_results(self, experiment_type: str):
        """Plot the results of a specific experiment"""
        if experiment_type not in self.results:
            print(f"❌ No results found for {experiment_type}")
            return
        
        data = self.results[experiment_type]
        
        plt.figure(figsize=(10, 6))
        
        if experiment_type == 'odmr' or experiment_type == 'cw_odmr':
            # All frequencies are stored in Hz, convert to GHz for plotting
            freqs = np.array(data['frequencies']) / 1e9  # Convert Hz to GHz
            title = 'ODMR'
            
            plt.plot(freqs, data['count_rates'], 'bo-')
            plt.xlabel('Frequency (GHz)')
            plt.ylabel('Count Rate (cps)')
            plt.title(title)
            
        elif experiment_type == 'rabi':
            plt.plot(data['durations'], data['count_rates'], 'ro-')
            plt.xlabel('MW Duration (ns)')
            plt.ylabel('Count Rate (cps)')
            plt.title('Rabi Oscillation')
            
        elif experiment_type == 't1_decay':
            plt.plot(np.array(data['delays'])/1000, data['count_rates'], 'co-')
            plt.xlabel('Delay (µs)')
            plt.ylabel('Count Rate (cps)')
            plt.title('T1 Decay')
        
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
        rigol = RigolDSG836Controller("192.168.0.223")
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
        #1. Continuous Wave ODMR
        # print("\n" + "="*50)
        # frequencies = np.linspace(2.7e9, 3e9, 100)  # 2.85-2.89 GHz
        # cw_odmr_result = experiments.cw_odmr(
        #     mw_frequencies=frequencies,
        #     acquisition_time=0.5,  # 1 seconds per point
        #     mw_power=0  # -10 dBm
        # )
        
        
        
        # experiments.plot_results('cw_odmr')
        
        # 2. ODMR
        # print("\n" + "="*50)
        # frequencies = np.linspace(1e9, 3e9, 50)  # 2.85-2.89 GHz
        # odmr_result = experiments.odmr(frequencies=frequencies, laser_duration=5000, mw_duration=5000, detection_duration=5000, laser_delay=0, mw_delay=0, detection_delay=0, sequence_interval=5000, repetitions=1000)
        # experiments.plot_results('odmr')
        
        # 2. Rabi oscillation
        # print("\n" + "="*50)
        # mw_durations = np.linspace(0, 10000, 20)  # 0-10000 ns in 500 ns steps
        # rabi_result = experiments.rabi_oscillation(mw_durations=mw_durations, mw_frequency=2.87e9, laser_duration=5000, detection_duration=5000, laser_delay=0, mw_delay=6000, detection_delay=0, sequence_interval=1000, repetitions=1000)
        # experiments.plot_results('rabi')
        
        # 3. T1 decay
        print("\n" + "="*50)
        delay_times = np.linspace(0, 3e6, 50)  # 0-3 microseconds in 50 steps
        # Important: For T1 measurements, readout_laser_delay and detection_delay should be None, this allows to code to calculate the delays automatically otherwise the sequence will not be created correctly. 
        t1_result = experiments.t1_decay(delay_times=delay_times, init_laser_duration=5000, readout_laser_duration=5000, detection_duration=5000, init_laser_delay=0, readout_laser_delay=None, detection_delay=None, sequence_interval=1000, repetitions=1000)
        experiments.plot_results('t1_decay')
        
        
        print("\n✅ All example experiments completed!")
        
    except Exception as e:
        print(f"❌ Error during experiments: {e}")
    
    finally:
        # Clean up connections
        #experiments.cleanup()  # Clean up TimeTagger resources
        if rigol:
            rigol.set_rf_output(False)  # Safety: turn off RF output
            rigol.disconnect()
        controller.disconnect()


if __name__ == "__main__":
    run_example_experiments() 