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
from scipy.optimize import curve_fit
import time
import sys
import os
from typing import List, Tuple, Dict, Optional, Callable
# Try relative imports first (when used as package)
try:
    from .swabian_pulse_streamer import SwabianPulseController
    from .rigol_dsg836 import RigolDSG836Controller
except ImportError:
    # Fall back to direct imports (when run as script)
    from swabian_pulse_streamer import SwabianPulseController
    from rigol_dsg836 import RigolDSG836Controller

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
            self.tagger = TimeTagger.createTimeTaggerNetwork("192.168.0.221")
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
        'odmr_contrast':  ('odmr_contrast', 'frequencies'),
        'rabi_contrast':  ('rabi_contrast', 'durations'),
        't1_contrast':    ('t1_contrast', 'delays'),
    }

    def _save_results(self, result_key: str, result: Dict):
        """Save experiment results using ODMRDataManager."""
        dm_type, x_key = self._SAVE_MAP[result_key]
        try:
            extra_columns = None
            count_rates = result.get('count_rates')
            if result_key == 'odmr_contrast':
                sig = np.array(result['mw_on_rates'])
                ref = np.array(result['mw_off_rates'])
                sig_over_ref = np.where(ref > 0, sig / ref, np.nan)
                extra_columns = {
                    'Signal_cps': sig,
                    'Reference_cps': ref,
                    'Signal_over_Reference': sig_over_ref,
                    'Contrast': result['contrasts'],
                }
                count_rates = None
            elif result_key in ('rabi_contrast', 't1_contrast'):
                sig = np.array(result['mw_on_rates'] if result_key == 'rabi_contrast' else result['sig_rates'])
                ref = np.array(result['mw_off_rates'] if result_key == 'rabi_contrast' else result['ref_rates'])
                sig_over_ref = np.where(ref > 0, sig / ref, np.nan)
                extra_columns = {
                    'Signal_cps': sig,
                    'Reference_cps': ref,
                    'Signal_over_Reference': sig_over_ref,
                    'Contrast': result['contrasts'],
                }
                count_rates = None
            saved_file = self.data_manager.save_experiment_data(
                experiment_type=dm_type,
                x_data=result[x_key],
                count_rates=count_rates,
                parameters=result.get('parameters', {}),
                extra_columns=extra_columns
            )
            result['saved_file'] = saved_file
            print(f"Data saved to: {saved_file}")
        except Exception as e:
            print(f"Warning: Could not save data: {e}")

    def odmr_contrast(self,
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
        Perform ODMR contrast measurement.

        This function performs ODMR measurements using the contrast method.
        For each microwave frequency, the sequence alternates between MW off and MW on.
        The ODMR contrast is defined as the differential photoluminescence signal between
        measurements with and without applying microwave radiation: (PL_off - PL_on) / PL_off

        The data array has length repetitions*2 where:
        - Even bins (0,2,4,...): MW off measurements (reference)
        - Odd bins (1,3,5,...): MW on measurements (signal)

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
            Dictionary containing frequencies, contrasts, and MW off/on rates
        """
        print("🔬 Starting ODMR contrast measurement...")

        frequencies = []
        contrasts = []
        mw_off_rates = []
        mw_on_rates = []

        # Each contrast sequence run produces 2 detection windows (MW off then MW on)
        self.counter = TimeTagger.CountBetweenMarkers(
            tagger=self.tagger,
            click_channel=1,
            begin_channel=2,
            end_channel=-2,
            n_values=repetitions * 2
        )

        if self.mw_generator:
            self.mw_generator.prepare_for_odmr(mw_frequencies[0] / 1e9, -10.0)

        for freq in mw_frequencies:
            print(f"📡 Measuring at {freq/1e6:.2f} MHz")

            sequence, total_duration = self.pulse_controller.create_odmr_sequence_contrast(
                laser_duration=laser_duration,
                mw_duration=mw_duration,
                detection_duration=detection_duration,
                laser_delay=laser_delay,
                mw_delay=mw_delay,
                detection_delay=detection_delay,
                sequence_interval=sequence_interval
            )
            #sequence.plot()
            time.sleep(0.2)

            if sequence:
                if self.mw_generator:
                    self.mw_generator.set_odmr_frequency(freq / 1e9)
                    self.mw_generator.set_rf_output(True)

                self.counter.start()
                ready = False
                self.pulse_controller.run_sequence(sequence, repetitions)

                while ready is False:
                    time.sleep(0.2)
                    ready = self.counter.ready()
                    information = self.counter.getBinWidths()
                    print(f"Information: {information}")
                    print(f"Ready: {ready}")
                    counts = self.counter.getData()
                    print(f"Counts: {counts}")

                self.counter.clear()

                counts_arr = np.array(counts)
                info_arr = np.array(information)

                # Even bins → MW off reference; odd bins → MW on signal
                counts_off = counts_arr[0::2]
                counts_on  = counts_arr[1::2]
                info_off   = info_arr[0::2]
                info_on    = info_arr[1::2]

                rate_off = np.mean(counts_off) / (np.mean(info_off) * 1e-12)
                rate_on  = np.mean(counts_on)  / (np.mean(info_on)  * 1e-12)
                contrast = (rate_off - rate_on) / rate_off if rate_off > 0 else 0.0

                print(f"MW off: {rate_off:.2f} Hz | MW on: {rate_on:.2f} Hz | Contrast: {contrast:.4f}")

                frequencies.append(freq)
                contrasts.append(contrast)
                mw_off_rates.append(rate_off)
                mw_on_rates.append(rate_on)

                if progress_callback:
                    progress_callback(frequencies.copy(), contrasts.copy())

                if self.mw_generator:
                    self.mw_generator.set_rf_output(False)

                time.sleep(0.05)

        self.results['odmr_contrast'] = {
            'frequencies': frequencies,
            'contrasts': contrasts,
            'mw_off_rates': mw_off_rates,
            'mw_on_rates': mw_on_rates,
            'count_rates': contrasts,  # alias used by _save_results
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

        self._save_results('odmr_contrast', self.results['odmr_contrast'])
        print(f"Contrasts: {contrasts}")
        print(f"Frequencies: {frequencies}")
        print("✅ ODMR contrast measurement completed")
        return self.results['odmr_contrast']

    def rabi_oscillation_contrast(self,
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
        Perform Rabi oscillation measurement using the contrast method.

        For each MW pulse duration τ, the sequence alternates between two sub-sequences:
          - Reference (even bins): laser + detection, MW off  → bright ms=0 PL
          - Signal   (odd  bins): laser + detection, MW on(τ) → PL after spin rotation

        The contrast (ref − sig) / ref starts near 0 for τ ≈ 0 and oscillates with the
        Rabi frequency. Normalising by the interleaved reference removes common-mode noise
        from laser power drift and APD efficiency changes.

        Args:
            mw_durations: List of MW pulse durations to sweep in ns
            mw_frequency: MW frequency in Hz
            laser_duration: Laser pulse duration in ns
            detection_duration: Detection window duration in ns
            laser_delay: Delay before laser pulse in ns
            mw_delay: Delay before MW pulse in ns
            detection_delay: Delay before detection window in ns
            sequence_interval: Interval between sub-sequences in ns
            repetitions: Number of repetitions per duration point
            progress_callback: Optional callback(durations, contrasts) for live updates

        Returns:
            Dictionary containing durations, contrasts, mw_off_rates, and mw_on_rates
        """
        print("🔬 Starting Rabi contrast measurement...")

        durations = []
        contrasts = []
        mw_off_rates = []
        mw_on_rates = []

        self.counter = TimeTagger.CountBetweenMarkers(
            tagger=self.tagger,
            click_channel=1,
            begin_channel=2,
            end_channel=-2,
            n_values=repetitions * 2
        )

        if self.mw_generator:
            self.mw_generator.set_odmr_frequency(mw_frequency / 1e9)
            self.mw_generator.prepare_for_odmr(mw_frequency / 1e9, -10.0)

        for mw_duration in mw_durations:
            print(f"⏱️ MW duration: {mw_duration} ns")

            local_laser_delay = mw_delay + mw_duration + laser_delay
            local_detection_delay = mw_delay + mw_duration + detection_delay

            sequence, total_duration = self.pulse_controller.create_rabi_sequence_contrast(
                laser_duration=laser_duration,
                mw_duration=mw_duration,
                detection_duration=detection_duration,
                laser_delay=local_laser_delay,
                mw_delay=mw_delay,
                detection_delay=local_detection_delay,
                sequence_interval=sequence_interval
            )
            time.sleep(0.2)
            # sequence.plot()
            if sequence:
                if self.mw_generator:
                    self.mw_generator.set_rf_output(True)

                self.counter.start()
                ready = False
                self.pulse_controller.run_sequence(sequence, repetitions)
                
                while ready is False:
                    time.sleep(0.2)
                    ready = self.counter.ready()
                    information = self.counter.getBinWidths()
                    print(f"Information: {information}")
                    print(f"Ready: {ready}")
                    counts = self.counter.getData()
                    print(f"Counts: {counts}")

                self.counter.clear()

                counts_arr = np.array(counts)
                info_arr = np.array(information)

                # Even bins → MW off (reference); odd bins → MW on (signal)
                counts_off = counts_arr[0::2]
                counts_on  = counts_arr[1::2]
                info_off   = info_arr[0::2]
                info_on    = info_arr[1::2]

                rate_off = np.mean(counts_off) / (np.mean(info_off) * 1e-12)
                rate_on  = np.mean(counts_on)  / (np.mean(info_on)  * 1e-12)
                contrast = (rate_off - rate_on) / rate_off if rate_off > 0 else 0.0

                print(f"MW off: {rate_off:.2f} Hz | MW on: {rate_on:.2f} Hz | Contrast: {contrast:.4f}")

                durations.append(mw_duration)
                contrasts.append(contrast)
                mw_off_rates.append(rate_off)
                mw_on_rates.append(rate_on)

                if progress_callback:
                    progress_callback(durations.copy(), contrasts.copy())

                if self.mw_generator:
                    self.mw_generator.set_rf_output(False)

                time.sleep(0.05)

        self.results['rabi_contrast'] = {
            'durations': durations,
            'contrasts': contrasts,
            'mw_off_rates': mw_off_rates,
            'mw_on_rates': mw_on_rates,
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

        self._save_results('rabi_contrast', self.results['rabi_contrast'])
        print(f"Contrasts: {contrasts}")
        print(f"Durations: {durations}")
        print("✅ Rabi contrast measurement completed")
        return self.results['rabi_contrast']

    def t1_decay_contrast(self,
                          delay_times: List[int],
                          init_laser_duration: int = 1000,
                          readout_laser_duration: int = 1000,
                          detection_duration: int = 500,
                          init_laser_delay: int = 0,
                          detection_delay: int = 0,
                          sequence_interval: int = 10000,
                          repetitions: int = 1000,
                          progress_callback: Optional[Callable] = None) -> Dict:
        """
        Perform T1 decay measurement using the contrast method.

        Each sequence repetition contains a single pulse train with two SPD windows:
          - Reference (even bins): detection at the END of the init laser (NV fully polarised)
          - Signal   (odd  bins): detection at the START of the readout laser after delay τ

          AOM: |──────── init laser ────────| ← delay τ → |── readout laser ──| interval |
          SPD:                     |ref bin|                    |sig bin|       interval |
               ← NV polarising →  ↑ fully init'd               ↑ + detection_delay

        The contrast Signal/Reference starts near 1.0 for short delays and decays
        exponentially toward the thermal-equilibrium value as τ increases.
        Normalising by the reference removes common-mode noise from laser power
        drift, APD efficiency changes, etc. Using the init laser as the reference
        halves the experimental time compared to running a separate reference sequence.

        Args:
            delay_times: List of delay times between init and readout in ns
            init_laser_duration: Duration of initialization laser pulse in ns.
                                 Must be >= detection_duration.
            readout_laser_duration: Duration of readout laser pulse in ns
            detection_duration: Duration of detection window in ns
            init_laser_delay: Delay before initialization laser in ns
            detection_delay: Offset added to the signal SPD gate start relative to the
                             readout laser edge, to compensate for AOM delay response in ns.
                             Only affects the signal window; the reference window is anchored
                             to the trailing end of the init laser.
            sequence_interval: Interval between sequences in ns
            repetitions: Number of repetitions per delay point
            progress_callback: Optional callback(delays, contrasts) for live updates

        Returns:
            Dictionary containing delays, contrasts, signal rates, and reference rates
        """
        print("🔬 Starting T1 contrast measurement...")

        delays = []
        contrasts = []
        sig_rates = []
        ref_rates = []

        self.counter = TimeTagger.CountBetweenMarkers(
            tagger=self.tagger,
            click_channel=1,
            begin_channel=2,
            end_channel=-2,
            n_values=repetitions * 2
        )

        for delay_time in delay_times:
            print(f"⏱️ Delay time: {delay_time} ns")

            sequence, total_duration = self.pulse_controller._create_t1_sequence_contrast(
                init_laser_duration=init_laser_duration,
                readout_laser_duration=readout_laser_duration,
                detection_duration=detection_duration,
                delay_time=delay_time,
                init_laser_delay=init_laser_delay,
                sequence_interval=sequence_interval,
                detection_delay=detection_delay
            )

            time.sleep(0.2)

            if sequence:
                self.counter.start()
                ready = False
                self.pulse_controller.run_sequence(sequence, n_runs=repetitions)

                while ready is False:
                    time.sleep(0.2)
                    ready = self.counter.ready()
                    information = self.counter.getBinWidths()
                    print(f"Information: {information}")
                    print(f"Ready: {ready}")
                    counts = self.counter.getData()
                    print(f"Counts: {counts}")

                self.counter.clear()

                counts_arr = np.array(counts)
                info_arr = np.array(information)

                # Even bins → reference (zero delay); odd bins → signal (delay τ)
                counts_ref = counts_arr[0::2]
                counts_sig = counts_arr[1::2]
                info_ref = info_arr[0::2]
                info_sig = info_arr[1::2]

                rate_ref = np.mean(counts_ref) / (np.mean(info_ref) * 1e-12)
                rate_sig = np.mean(counts_sig) / (np.mean(info_sig) * 1e-12)
                contrast = rate_sig / rate_ref if rate_ref > 0 else 0.0

                print(f"Reference: {rate_ref:.2f} Hz | Signal: {rate_sig:.2f} Hz | Sig/Ref: {contrast:.4f}")

                delays.append(delay_time)
                contrasts.append(contrast)
                ref_rates.append(rate_ref)
                sig_rates.append(rate_sig)

                if progress_callback:
                    progress_callback(delays.copy(), contrasts.copy())

                time.sleep(0.05)

        self.results['t1_contrast'] = {
            'delays': delays,
            'contrasts': contrasts,
            'ref_rates': ref_rates,
            'sig_rates': sig_rates,
            'parameters': {
                'init_laser_duration': init_laser_duration,
                'readout_laser_duration': readout_laser_duration,
                'detection_duration': detection_duration,
                'init_laser_delay': init_laser_delay,
                'detection_delay': detection_delay,
                'sequence_interval': sequence_interval,
                'repetitions': repetitions
            }
        }

        self._save_results('t1_contrast', self.results['t1_contrast'])
        print(f"Contrasts: {contrasts}")
        print(f"Delays: {delays}")
        print("✅ T1 contrast measurement completed")
        return self.results['t1_contrast']

    def plot_results(self, experiment_type: str):
        """Plot the results of a specific experiment"""
        if experiment_type not in self.results:
            print(f"❌ No results found for {experiment_type}")
            return
        
        data = self.results[experiment_type]
        base_path = data.get('saved_file', '').replace('.csv', '')

        plt.figure(figsize=(10, 6))

        if experiment_type == 'odmr_contrast':
            freqs = np.array(data['frequencies']) / 1e9
            sig = np.array(data['mw_on_rates'])
            ref = np.array(data['mw_off_rates'])
            sig_over_ref = np.where(ref > 0, sig / ref, np.nan)
            contrasts_pct = np.array(data['contrasts']) * 100

            fig, axes = plt.gcf(), None
            plt.close(fig)
            fig, axes = plt.subplots(4, 1, figsize=(10, 16), sharex=True)

            axes[0].plot(freqs, ref, 'bo-', label='Reference (MW off)')
            axes[0].set_ylabel('Count Rate (cps)')
            axes[0].set_title('ODMR Contrast')
            axes[0].legend()
            axes[0].grid(True, alpha=0.3)

            axes[1].plot(freqs, sig, 'ro-', label='Signal (MW on)')
            axes[1].set_ylabel('Count Rate (cps)')
            axes[1].legend()
            axes[1].grid(True, alpha=0.3)

            axes[2].plot(freqs, sig_over_ref, 'mo-', label='Signal / Reference')
            axes[2].set_ylabel('Signal / Reference')
            axes[2].legend()
            axes[2].grid(True, alpha=0.3)

            axes[3].plot(freqs, contrasts_pct, 'go-', label='Contrast = (ref − sig) / ref')
            axes[3].set_xlabel('Frequency (GHz)')
            axes[3].set_ylabel('Contrast (%)')
            axes[3].legend()
            axes[3].grid(True, alpha=0.3)

            plt.tight_layout()

            # --- Individual plots ---
            fig_ratio, ax_ratio = plt.subplots(figsize=(10, 6))
            ax_ratio.plot(freqs, sig_over_ref, 'mo-', label='Signal / Reference')
            ax_ratio.set_xlabel('Frequency (GHz)')
            ax_ratio.set_ylabel('Signal / Reference')
            ax_ratio.set_title('ODMR – Signal / Reference')
            ax_ratio.legend()
            ax_ratio.grid(True, alpha=0.3)
            fig_ratio.tight_layout()

            fig_con, ax_con = plt.subplots(figsize=(10, 6))
            ax_con.plot(freqs, contrasts_pct, 'go-', label='Contrast = (ref − sig) / ref')
            ax_con.set_xlabel('Frequency (GHz)')
            ax_con.set_ylabel('Contrast (%)')
            ax_con.set_title('ODMR – Contrast')
            ax_con.legend()
            ax_con.grid(True, alpha=0.3)
            fig_con.tight_layout()

            if base_path:
                fig.savefig(f"{base_path}.pdf", format='pdf', bbox_inches='tight')
                fig_ratio.savefig(f"{base_path}_ratio.pdf", format='pdf', bbox_inches='tight')
                fig_con.savefig(f"{base_path}_con.pdf", format='pdf', bbox_inches='tight')
                print(f"Plots saved to: {base_path}*.pdf")

            plt.show()
            return
            
        elif experiment_type == 'rabi_contrast':
            durs = np.array(data['durations'])
            sig = np.array(data['mw_on_rates'])
            ref = np.array(data['mw_off_rates'])
            sig_over_ref = np.where(ref > 0, sig / ref, np.nan)
            contrasts_pct = np.array(data['contrasts']) * 100

            fig, axes = plt.gcf(), None
            plt.close(fig)
            fig, axes = plt.subplots(3, 1, figsize=(10, 14), sharex=True)

            axes[0].plot(durs, ref, 'bo-', label='Reference (MW off)')
            axes[0].set_ylabel('Count Rate (cps)')
            axes[0].set_title('Rabi Contrast')
            axes[0].legend()
            axes[0].grid(True, alpha=0.3)

            axes[1].plot(durs, sig, 'ro-', label='Signal (MW on)')
            axes[1].set_ylabel('Count Rate (cps)')
            axes[1].legend()
            axes[1].grid(True, alpha=0.3)

            axes[2].plot(durs, contrasts_pct, 'go-', label='Contrast = (ref − sig) / ref')
            axes[2].set_xlabel('MW Duration (ns)')
            axes[2].set_ylabel('Contrast (%)')
            axes[2].legend()
            axes[2].grid(True, alpha=0.3)

            plt.tight_layout()

            fig_con, ax_con = plt.subplots(figsize=(10, 6))
            ax_con.plot(durs, contrasts_pct, 'go-', label='Contrast = (ref − sig) / ref')
            ax_con.set_xlabel('MW Duration (ns)')
            ax_con.set_ylabel('Contrast (%)')
            ax_con.set_title('Rabi – Contrast')
            ax_con.legend()
            ax_con.grid(True, alpha=0.3)
            fig_con.tight_layout()

            if base_path:
                fig.savefig(f"{base_path}.pdf", format='pdf', bbox_inches='tight')
                fig_con.savefig(f"{base_path}_con.pdf", format='pdf', bbox_inches='tight')
                print(f"Plots saved to: {base_path}*.pdf")

            plt.show()
            return

        elif experiment_type == 't1_contrast':
            delays_us = np.array(data['delays']) / 1000  # ns -> µs
            sig = np.array(data['sig_rates'])
            ref = np.array(data['ref_rates'])
            sig_over_ref = np.where(ref > 0, sig / ref, np.nan)
            contrasts = np.array(data['contrasts'])

            diffs = np.diff(delays_us)
            use_log = len(delays_us) > 2 and delays_us[0] > 0 and (diffs.max() / diffs.min() > 5)
            plot_fn_name = 'semilogx' if use_log else 'plot'
            grid_which = 'both' if use_log else 'major'

            fig, axes = plt.gcf(), None
            plt.close(fig)
            fig, axes = plt.subplots(3, 1, figsize=(10, 14), sharex=True)

            getattr(axes[0], plot_fn_name)(delays_us, ref, 'bo-', label='Reference (τ = 0)')
            axes[0].set_ylabel('Count Rate (cps)')
            axes[0].set_title('T1 Contrast')
            axes[0].legend()
            axes[0].grid(True, alpha=0.3, which=grid_which)

            getattr(axes[1], plot_fn_name)(delays_us, sig, 'ro-', label='Signal (τ = delay)')
            axes[1].set_ylabel('Count Rate (cps)')
            axes[1].legend()
            axes[1].grid(True, alpha=0.3, which=grid_which)

            getattr(axes[2], plot_fn_name)(delays_us, sig_over_ref, 'mo', label='Signal / Reference')
            fit_t = None
            try:
                exp_decay = lambda t, A, T1, C: A * np.exp(-t / T1) + C
                p0 = [sig_over_ref[0] - sig_over_ref[-1], delays_us[-1] / 3, sig_over_ref[-1]]
                popt, pcov = curve_fit(exp_decay, delays_us, sig_over_ref, p0=p0, maxfev=10000)
                perr = np.sqrt(np.diag(pcov))
                if use_log:
                    fit_t = np.logspace(np.log10(delays_us[0]), np.log10(delays_us[-1]), 500)
                else:
                    fit_t = np.linspace(delays_us[0], delays_us[-1], 500)
                axes[2].plot(fit_t, exp_decay(fit_t, *popt), 'r-', linewidth=2,
                             label=f'Fit: T1 = {popt[1]:.2f} ± {perr[1]:.2f} µs')
                print(f"T1 fit: A={popt[0]:.4f}, T1={popt[1]:.2f} ± {perr[1]:.2f} µs, C={popt[2]:.4f}")
            except Exception as e:
                print(f"Warning: T1 exponential fit failed: {e}")
            axes[2].set_xlabel('Delay (µs)')
            axes[2].set_ylabel('Signal / Reference')
            axes[2].legend()
            axes[2].grid(True, alpha=0.3, which=grid_which)

            plt.tight_layout()

            fig_ratio, ax_ratio = plt.subplots(figsize=(10, 6))
            getattr(ax_ratio, plot_fn_name)(delays_us, sig_over_ref, 'mo', label='Signal / Reference')
            if fit_t is not None:
                try:
                    ax_ratio.plot(fit_t, exp_decay(fit_t, *popt), 'r-', linewidth=2,
                                  label=f'Fit: T1 = {popt[1]:.2f} ± {perr[1]:.2f} µs')
                except Exception:
                    pass
            ax_ratio.set_xlabel('Delay (µs)')
            ax_ratio.set_ylabel('Signal / Reference')
            ax_ratio.set_title('T1 – Signal / Reference')
            ax_ratio.legend()
            ax_ratio.grid(True, alpha=0.3, which=grid_which)
            fig_ratio.tight_layout()

            if base_path:
                fig.savefig(f"{base_path}.pdf", format='pdf', bbox_inches='tight')
                fig_ratio.savefig(f"{base_path}_ratio.pdf", format='pdf', bbox_inches='tight')
                print(f"Plots saved to: {base_path}*.pdf")

            plt.show()
            return

        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        if base_path:
            plt.savefig(f"{base_path}.pdf", format='pdf', bbox_inches='tight')
            print(f"Plot saved to: {base_path}.pdf")

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
        # 1. ODMR Contrast
        # print("\n" + "="*50)
        # frequencies = np.linspace(2.8e9, 2.95e9, 50)
        # odmr_contrast_result = experiments.odmr_contrast(
        #     mw_frequencies=frequencies,
        #     laser_duration=200000,
        #     mw_duration=200000,
        #     detection_duration=200000,
        #     laser_delay=0,
        #     mw_delay=0,
        #     detection_delay=0,
        #     sequence_interval=2000,
        #     repetitions=5000
        # )
        # experiments.plot_results('odmr_contrast')

        # 2. Rabi oscillation with contrast (signal/reference normalisation)
        # print("\n" + "="*50)
        # mw_durations = np.linspace(0, 10000, 40)
        # rabi_contrast_result = experiments.rabi_oscillation_contrast(
        #     mw_durations=mw_durations,
        #     mw_frequency=2.87e9,
        #     laser_duration=25000,
        #     detection_duration=2000,
        #     laser_delay=0,
        #     mw_delay=0,
        #     detection_delay=1500,
        #     sequence_interval=1000,
        #     repetitions=5000
        # )
        # experiments.plot_results('rabi_contrast')

        # 3. T1 decay with contrast (signal/reference normalisation)
        print("\n" + "="*50)
        delay_times = np.linspace(0, 0.5e6, 50)  # 0-10 µs in 50 steps
        #delay_times = np.logspace(0, np.log10(1e6), 50)
        t1_contrast_result = experiments.t1_decay_contrast(
            delay_times=delay_times,
            init_laser_duration=50000,
            readout_laser_duration=50000,
            detection_duration=3000,
            init_laser_delay=0,
            detection_delay=1500,
            sequence_interval=2000,
            repetitions=500
        )
        experiments.plot_results('t1_contrast')
        
        
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