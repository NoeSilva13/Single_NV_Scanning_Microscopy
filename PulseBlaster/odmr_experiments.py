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
from scipy.special import gamma as gamma_func
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
from common.odmr_data_manager import ODMRDataManager

# TimeTagger imports for real data acquisition
import TimeTagger

class _LiveContrastPlot:
    """
    Interactive single-panel plot refreshed after every sweep point.

    Any failure (non-interactive backend, closed window) disables the plot instead
    of interrupting the measurement.
    """

    def __init__(self, xlabel: str, ylabel: str, title: str,
                 x_scale: float = 1.0, marker: str = 'o-'):
        self.x_scale = x_scale
        self.enabled = False
        self._was_interactive = plt.isinteractive()
        try:
            plt.ion()
            self.fig, self.ax = plt.subplots(figsize=(10, 6))
            self.line, = self.ax.plot([], [], marker, color='green')
            self.ax.set_xlabel(xlabel)
            self.ax.set_ylabel(ylabel)
            self.ax.set_title(title)
            self.ax.grid(True, alpha=0.3)
            self.fig.tight_layout()
            self.fig.show()
            self.fig.canvas.flush_events()
            self.enabled = True
        except Exception as e:
            print(f"Warning: live plot disabled ({e})")
            if not self._was_interactive:
                plt.ioff()

    def update(self, x_values, y_values):
        if not self.enabled:
            return
        try:
            self.line.set_data(np.asarray(x_values, dtype=float) / self.x_scale,
                               np.asarray(y_values, dtype=float))
            self.ax.relim()
            self.ax.autoscale_view()
            self.fig.canvas.draw_idle()
            self.fig.canvas.flush_events()
        except Exception as e:
            print(f"Warning: live plot update failed ({e})")
            self.enabled = False

    def close(self):
        try:
            plt.close(self.fig)
        except Exception:
            pass
        self.enabled = False
        if not self._was_interactive:
            plt.ioff()


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
        from common.utils import TIMETAGGER_NETWORK_HOST, timetagger_virtual_path

        self.tagger = None
        if TIMETAGGER_NETWORK_HOST:
            try:
                self.tagger = TimeTagger.createTimeTaggerNetwork(TIMETAGGER_NETWORK_HOST)
                print(f"✅ Connected to Network TimeTagger at {TIMETAGGER_NETWORK_HOST}")
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
                self.tagger = TimeTagger.createTimeTaggerVirtual(timetagger_virtual_path())
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
        'odmr_contrast':        ('odmr_contrast', 'frequencies'),
        'pulsed_odmr_contrast': ('pulsed_odmr_contrast', 'frequencies'),
        'rabi_contrast':        ('rabi_contrast', 'durations'),
        't1_contrast':          ('t1_contrast', 'delays'),
        'readout_transient':    ('readout_transient', 'times'),
    }

    def _save_results(self, result_key: str, result: Dict):
        """Save experiment results using ODMRDataManager."""
        dm_type, x_key = self._SAVE_MAP[result_key]
        try:
            extra_columns = None
            count_rates = result.get('count_rates')
            if result_key in ('odmr_contrast', 'pulsed_odmr_contrast'):
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
            elif result_key == 'readout_transient':
                extra_columns = {
                    'Reference_counts': result['ref_counts'],
                    'Signal_counts': result['sig_counts'],
                    'Difference_counts': result['difference'],
                    'Contrast': result['contrast_per_bin'],
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
                      plot_sequence: bool = False,
                      live_plot: bool = True,
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
            plot_sequence: If True, call sequence.plot() at each sweep point (blocks until closed)
            live_plot: If True, show a contrast plot that refreshes after each frequency point

        Returns:
            Dictionary containing frequencies, contrasts, and MW off/on rates
        """
        print("🔬 Starting ODMR contrast measurement...")

        frequencies = []
        contrasts = []
        mw_off_rates = []
        mw_on_rates = []

        live = None
        if live_plot and progress_callback is None:
            live = _LiveContrastPlot(xlabel='Frequency (MHz)', ylabel='Contrast (%)',
                                     title='ODMR Contrast (live)', x_scale=1e6)

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
            if plot_sequence and sequence:
                sequence.plot()
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
                if live:
                    live.update(frequencies, np.array(contrasts) * 100)

                if self.mw_generator:
                    self.mw_generator.set_rf_output(False)

                time.sleep(0.05)

        if live:
            live.close()

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
                                   init_laser_duration: int = 3000,
                                   readout_laser_duration: int = 3000,
                                   detection_duration: int = 1500,
                                   init_laser_delay: int = 0,
                                   mw_gap: int = 200,
                                   readout_gap: int = 200,
                                   detection_delay: int = 1500,
                                   sequence_interval: int = 5000,
                                   repetitions: int = 1000,
                                   plot_sequence: bool = False,
                                   live_plot: bool = True,
                                   progress_callback: Optional[Callable] = None) -> Dict:
        """
        Perform Rabi oscillation measurement using the contrast method.

        For each MW pulse duration τ, the sequence alternates between two sub-sequences
        that share identical optical and detection timing:

          AOM: |── init ──| ← mw_gap → [MW slot τ] ← readout_gap → |── readout ──|
          SPD:                                                   |detect|

          - Reference (even bins): MW off  → bright ms=0 PL at readout
          - Signal   (odd  bins): MW on(τ) → PL after spin rotation

        The contrast (ref − sig) / ref starts near 0 for τ ≈ 0 and oscillates with the
        Rabi frequency. Normalising by the interleaved reference removes common-mode noise
        from laser power drift and APD efficiency changes.

        Args:
            mw_durations: List of MW pulse durations to sweep in ns
            mw_frequency: MW frequency in Hz (use the ODMR resonance of your NV)
            init_laser_duration: Initialization laser pulse duration in ns
            readout_laser_duration: Readout laser pulse duration in ns
            detection_duration: Detection window duration in ns
            init_laser_delay: Delay before initialization laser in ns
            mw_gap: Dark time between init laser and MW pulse in ns
            readout_gap: Dark time between MW pulse and readout laser in ns
            detection_delay: SPD gate offset relative to readout edge (AOM compensation) in ns
            sequence_interval: Interval between sub-sequences in ns
            repetitions: Number of repetitions per duration point
            plot_sequence: If True, call sequence.plot() at each sweep point (blocks until closed)
            live_plot: If True, show a contrast plot that refreshes after each duration point
            progress_callback: Optional callback(durations, contrasts) for live updates

        Returns:
            Dictionary containing durations, contrasts, mw_off_rates, and mw_on_rates
        """
        print("🔬 Starting Rabi contrast measurement...")

        durations = []
        contrasts = []
        mw_off_rates = []
        mw_on_rates = []

        live = None
        if live_plot and progress_callback is None:
            live = _LiveContrastPlot(xlabel='MW Duration (ns)', ylabel='Contrast (%)',
                                     title='Rabi Contrast (live)')

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

            sequence, total_duration = self.pulse_controller.create_rabi_sequence_contrast(
                init_laser_duration=init_laser_duration,
                readout_laser_duration=readout_laser_duration,
                mw_duration=int(mw_duration),
                detection_duration=detection_duration,
                init_laser_delay=init_laser_delay,
                mw_gap=mw_gap,
                readout_gap=readout_gap,
                detection_delay=detection_delay,
                sequence_interval=sequence_interval
            )
            if plot_sequence and sequence:
                sequence.plot()
            time.sleep(0.2)
            if sequence:
                if self.mw_generator:
                    self.mw_generator.set_rf_output(True)
                time.sleep(0.2)
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
                if live:
                    live.update(durations, np.array(contrasts) * 100)

                if self.mw_generator:
                    self.mw_generator.set_rf_output(False)

                time.sleep(0.05)

        if live:
            live.close()

        self.results['rabi_contrast'] = {
            'durations': durations,
            'contrasts': contrasts,
            'mw_off_rates': mw_off_rates,
            'mw_on_rates': mw_on_rates,
            'parameters': {
                'mw_frequency': mw_frequency,
                'init_laser_duration': init_laser_duration,
                'readout_laser_duration': readout_laser_duration,
                'detection_duration': detection_duration,
                'init_laser_delay': init_laser_delay,
                'mw_gap': mw_gap,
                'readout_gap': readout_gap,
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

    def pulsed_odmr_contrast(self,
                              mw_frequencies: List[float],
                              mw_duration: int = 1000,
                              init_laser_duration: int = 3000,
                              readout_laser_duration: int = 1000,
                              detection_duration: int = 300,
                              init_laser_delay: int = 0,
                              mw_gap: int = 500,
                              readout_gap: int = 500,
                              detection_delay: int = 0,
                              sequence_interval: int = 2000,
                              repetitions: int = 100000,
                              plot_sequence: bool = False,
                              live_plot: bool = True,
                              progress_callback: Optional[Callable] = None) -> Dict:
        """
        Perform pulsed ODMR contrast measurement.

        Uses the same pulse sequence as the Rabi experiment (init laser → MW pulse in the
        dark → readout laser + detection), but sweeps the MW frequency with the MW pulse
        duration held fixed:

          AOM: |── init ──| ← mw_gap → [MW slot, fixed] ← readout_gap → |── readout ──|
          SPD:                                                        |detect|

          - Reference (even bins): MW off  → bright ms=0 PL at readout
          - Signal   (odd  bins): MW on   → PL after spin rotation at the swept frequency

        Because the MW is applied in the dark rather than simultaneously with the laser,
        the resonance is not power-broadened by optical pumping. The linewidth is limited
        by 1/(pi*T2*) and by the MW pulse duration (~0.8/mw_duration), typically giving
        1-3 MHz instead of the ~10 MHz of continuous-wave ODMR. This is narrow enough to
        resolve the 14N hyperfine triplet (2.16 MHz splitting).

        Setting mw_duration to the pi-pulse duration measured with rabi_oscillation_contrast
        maximises the contrast. A longer pulse (1-2 us) also works and needs no calibration,
        which makes this measurement a useful positive control for the pulsed sequence:
        the resonance frequency is already known from the CW ODMR, so a missing dip points
        to a sequence or readout timing problem rather than to spin physics.

        Args:
            mw_frequencies: List of microwave frequencies to sweep (Hz)
            mw_duration: Fixed MW pulse duration in ns (use the pi-pulse duration if known)
            init_laser_duration: Initialization laser pulse duration in ns
            readout_laser_duration: Readout laser pulse duration in ns
            detection_duration: Detection window duration in ns
            init_laser_delay: Delay before initialization laser in ns
            mw_gap: Dark time between init laser and MW pulse in ns
            readout_gap: Dark time between MW pulse and readout laser in ns
            detection_delay: SPD gate offset relative to readout edge (AOM compensation) in ns
            sequence_interval: Interval between sub-sequences in ns
            repetitions: Number of repetitions per frequency point
            plot_sequence: If True, call sequence.plot() at each sweep point (blocks until closed)
            live_plot: If True, show a contrast plot that refreshes after each frequency point
            progress_callback: Optional callback(frequencies, contrasts) for live updates

        Returns:
            Dictionary containing frequencies, contrasts, and MW off/on rates
        """
        print("🔬 Starting pulsed ODMR contrast measurement...")

        frequencies = []
        contrasts = []
        mw_off_rates = []
        mw_on_rates = []

        live = None
        if live_plot and progress_callback is None:
            live = _LiveContrastPlot(xlabel='Frequency (MHz)', ylabel='Contrast (%)',
                                     title='Pulsed ODMR Contrast (live)', x_scale=1e6)

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

        # The MW pulse length is fixed, so the sequence is identical for every frequency
        sequence, total_duration = self.pulse_controller.create_rabi_sequence_contrast(
            init_laser_duration=init_laser_duration,
            readout_laser_duration=readout_laser_duration,
            mw_duration=int(mw_duration),
            detection_duration=detection_duration,
            init_laser_delay=init_laser_delay,
            mw_gap=mw_gap,
            readout_gap=readout_gap,
            detection_delay=detection_delay,
            sequence_interval=sequence_interval
        )
        if plot_sequence and sequence:
            sequence.plot()
        time.sleep(0.2)

        for freq in mw_frequencies:
            print(f"📡 Measuring at {freq/1e6:.2f} MHz")

            if sequence:
                if self.mw_generator:
                    self.mw_generator.set_odmr_frequency(freq / 1e9)
                    self.mw_generator.set_rf_output(True)
                time.sleep(0.2)
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

                frequencies.append(freq)
                contrasts.append(contrast)
                mw_off_rates.append(rate_off)
                mw_on_rates.append(rate_on)

                if progress_callback:
                    progress_callback(frequencies.copy(), contrasts.copy())
                if live:
                    live.update(frequencies, np.array(contrasts) * 100)

                if self.mw_generator:
                    self.mw_generator.set_rf_output(False)

                time.sleep(0.05)

        if live:
            live.close()

        self.results['pulsed_odmr_contrast'] = {
            'frequencies': frequencies,
            'contrasts': contrasts,
            'mw_off_rates': mw_off_rates,
            'mw_on_rates': mw_on_rates,
            'parameters': {
                'mw_duration': self.pulse_controller.align_timing(int(mw_duration)),
                'init_laser_duration': init_laser_duration,
                'readout_laser_duration': readout_laser_duration,
                'detection_duration': detection_duration,
                'init_laser_delay': init_laser_delay,
                'mw_gap': mw_gap,
                'readout_gap': readout_gap,
                'detection_delay': detection_delay,
                'sequence_interval': sequence_interval,
                'repetitions': repetitions
            }
        }

        self._save_results('pulsed_odmr_contrast', self.results['pulsed_odmr_contrast'])
        print(f"Contrasts: {contrasts}")
        print(f"Frequencies: {frequencies}")
        print("✅ Pulsed ODMR contrast measurement completed")
        return self.results['pulsed_odmr_contrast']

    @staticmethod
    def _optimal_detection_window(times_ns: np.ndarray,
                                  ref_counts: np.ndarray,
                                  sig_counts: np.ndarray,
                                  min_width_ns: int = 48,
                                  search_start_ns: float = 0.0) -> Dict:
        """
        Find the detection window that maximises the shot-noise-limited contrast SNR.

        For a window spanning bins [i, j) the accumulated reference and signal counts
        are R and S. The measured quantity is the contrast (R - S) / R, and in the
        shot-noise limit its uncertainty scales as sqrt(R + S) / R, so the figure of
        merit to maximise is

            SNR(i, j) = (R - S) / sqrt(R + S)

        Maximising the contrast alone would collapse the window to zero width (highest
        contrast, no photons); maximising the total counts would take the whole readout
        pulse (many photons, diluted contrast). This ratio is what balances the two,
        and its argmax gives detection_delay and detection_duration simultaneously.

        The absolute SNR value depends on integration time, so only the location of the
        maximum is physically meaningful; the value is useful for comparing windows
        within the same dataset.

        Args:
            times_ns: Left edge of each bin, in ns relative to the readout laser edge
            ref_counts: Photon counts per bin with MW off
            sig_counts: Photon counts per bin with MW on
            min_width_ns: Smallest window width to consider in ns
            search_start_ns: Earliest window start to consider in ns. Defaults to the
                             readout laser edge: the dark bins recorded before it carry
                             no signal but almost no shot noise either, so leaving them
                             in the search lets the optimiser pick them up on noise alone.

        Returns:
            Dictionary with the optimal window, its contrast and SNR, and the SNR as a
            function of window width at the optimal start. That slice is usually flat
            near the maximum, so any width within a factor of ~1.5 of the optimum
            performs essentially the same.
        """
        ref_counts = np.asarray(ref_counts, dtype=float)
        sig_counts = np.asarray(sig_counts, dtype=float)
        binwidth = float(times_ns[1] - times_ns[0])

        # Cumulative sums give every window sum as a single subtraction
        cum_ref = np.concatenate(([0.0], np.cumsum(ref_counts)))
        cum_sig = np.concatenate(([0.0], np.cumsum(sig_counts)))

        # Element [i, j] corresponds to the window from bin i (inclusive) to bin j (exclusive)
        window_ref = cum_ref[None, :] - cum_ref[:, None]
        window_sig = cum_sig[None, :] - cum_sig[:, None]
        window_tot = window_ref + window_sig

        edges = np.arange(len(cum_ref))
        edge_times = float(times_ns[0]) + edges * binwidth
        window_width = (edges[None, :] - edges[:, None]) * binwidth

        with np.errstate(divide='ignore', invalid='ignore'):
            snr = (window_ref - window_sig) / np.sqrt(window_tot)
        snr[~np.isfinite(snr)] = -np.inf
        snr[window_width < min_width_ns] = -np.inf
        snr[edge_times < search_start_ns, :] = -np.inf

        i, j = np.unravel_index(int(np.argmax(snr)), snr.shape)
        best_ref = window_ref[i, j]
        best_sig = window_sig[i, j]

        # SNR versus width at the optimal start, to show how flat the maximum is
        width_slice = window_width[i, i:]
        snr_slice = snr[i, i:]
        valid = np.isfinite(snr_slice)

        return {
            'start_ns': float(times_ns[i]),
            'width_ns': float((j - i) * binwidth),
            'snr': float(snr[i, j]),
            'contrast': float((best_ref - best_sig) / best_ref) if best_ref > 0 else 0.0,
            'ref_counts': float(best_ref),
            'sig_counts': float(best_sig),
            'widths_ns': width_slice[valid],
            'snr_vs_width': snr_slice[valid],
        }

    def _acquire_transient(self,
                           mw_on: bool,
                           sequence_kwargs: Dict,
                           repetitions: int,
                           binwidth_ns: int,
                           n_bins: int,
                           plot_sequence: bool) -> Optional[np.ndarray]:
        """
        Accumulate one photon-arrival-time histogram over the readout pulse.

        The pulse sequence is streamed with infinite repetitions while the histogram
        integrates for the equivalent of `repetitions` sequence runs. Streaming
        continuously rather than for a fixed number of runs avoids having to
        synchronise the end of the stream with the end of the acquisition.

        Args:
            mw_on: MW state held for the whole run (False → reference, True → signal)
            sequence_kwargs: Arguments forwarded to create_readout_transient_sequence
            repetitions: Number of sequence runs to integrate over
            binwidth_ns: Histogram bin width in ns
            n_bins: Number of histogram bins
            plot_sequence: If True, call sequence.plot() before acquiring (blocks until closed)

        Returns:
            Array of counts per bin, or None if the sequence could not be created
        """
        created = self.pulse_controller.create_readout_transient_sequence(
            mw_on=mw_on, **sequence_kwargs
        )
        if not created:
            return None

        sequence, single_duration = created
        if plot_sequence:
            sequence.plot()

        histogram = TimeTagger.Histogram(
            tagger=self.tagger,
            click_channel=1,
            start_channel=2,
            binwidth=int(binwidth_ns * 1000),   # TimeTagger expects picoseconds
            n_bins=int(n_bins)
        )

        # Stream continuously and let the histogram define the integration time
        self.pulse_controller.run_sequence(sequence, None)
        time.sleep(0.2)

        capture_ps = int(repetitions) * int(single_duration) * 1000
        print(f"   integrating {capture_ps * 1e-12:.1f} s "
              f"({repetitions} runs × {single_duration} ns)")
        histogram.startFor(capture_ps)
        histogram.waitUntilFinished()

        counts = np.array(histogram.getData(), dtype=float)
        histogram.stop()
        histogram.clear()
        self.pulse_controller.stop_sequence()
        time.sleep(0.2)

        print(f"   total photons: {counts.sum():.0f}")
        return counts

    def readout_transient(self,
                          mw_frequency: float = 2.87e9,
                          mw_duration: int = 1000,
                          init_laser_duration: int = 3000,
                          readout_laser_duration: int = 3000,
                          detection_duration: Optional[int] = None,
                          init_laser_delay: int = 0,
                          mw_gap: int = 500,
                          readout_gap: int = 500,
                          pre_readout: int = 200,
                          sequence_interval: int = 2000,
                          repetitions: int = 200000,
                          binwidth_ns: int = 4,
                          min_window_ns: int = 48,
                          plot_sequence: bool = False) -> Dict:
        """
        Measure the time-resolved readout transient and derive the optimal detection window.

        Two histograms of photon arrival time during the readout pulse are accumulated,
        one with the MW off (reference, ms=0 bright state) and one with the MW on at a
        fixed resonant frequency (signal, spin rotated). Both use the same optical
        sequence, so their difference isolates the spin-dependent part of the
        fluorescence:

          AOM: |── init ──| ← mw_gap → [MW slot] ← readout_gap → |── readout ──|
          SPD:                                          |──── wide gate ────|
          hist:                                         |b|b|b|b|b|b|b|b|b|b|   ← binwidth_ns

        The spin information lives only in the first few hundred ns of the readout,
        while the NV is being repolarised to ms=0. Integrating beyond that adds photons
        that are identical for both spin states and therefore dilutes the contrast.
        This measurement resolves that transient directly, so detection_delay and
        detection_duration for the Rabi and pulsed ODMR sequences can be read off the
        data instead of being scanned point by point.

        Measuring all time bins simultaneously is both faster than a delay scan (by
        roughly the number of candidate window positions, since no photon is discarded)
        and immune to drift distorting the shape of the transient. The cost is that
        reference and signal come from two separate runs rather than being interleaved,
        so the two runs should be taken back to back under identical optical conditions.

        Args:
            mw_frequency: MW frequency for the signal run in Hz. Use the resonance
                          found with odmr_contrast.
            mw_duration: MW pulse duration in ns. A long saturating pulse (~1 us) works
                         and needs no calibration; the pi-pulse duration maximises the
                         contrast once known.
            init_laser_duration: Initialization laser pulse duration in ns
            readout_laser_duration: Readout laser pulse duration in ns. Should be long
                                    enough to contain the full repolarisation transient.
            detection_duration: SPD gate width in ns. Defaults to
                                pre_readout + readout_laser_duration so the gate spans
                                the whole readout pulse.
            init_laser_delay: Delay before the initialization laser in ns
            mw_gap: Dark time between init laser and MW pulse in ns
            readout_gap: Dark time between MW pulse and readout laser in ns.
                         Must be >= pre_readout.
            pre_readout: How long before the readout laser edge the gate opens in ns.
                         These leading dark bins provide the background level and make
                         the laser turn-on visible in the histogram.
            sequence_interval: Idle time after each sequence run in ns
            repetitions: Equivalent number of sequence runs to integrate per histogram
            binwidth_ns: Histogram bin width in ns. Finer bins cost no extra time, but
                         must stay coarse enough that each bin collects enough photons.
            min_window_ns: Smallest detection window width considered by the optimiser
            plot_sequence: If True, call sequence.plot() for each of the two runs

        Returns:
            Dictionary with the time axis, both transients, the per-bin contrast and the
            recommended detection_delay / detection_duration
        """
        print("🔬 Starting readout transient measurement...")

        if detection_duration is None:
            detection_duration = pre_readout + readout_laser_duration

        sequence_kwargs = {
            'init_laser_duration': init_laser_duration,
            'readout_laser_duration': readout_laser_duration,
            'mw_duration': int(mw_duration),
            'detection_duration': detection_duration,
            'init_laser_delay': init_laser_delay,
            'mw_gap': mw_gap,
            'readout_gap': readout_gap,
            'pre_readout': pre_readout,
            'sequence_interval': sequence_interval,
        }

        n_bins = int(self.pulse_controller.align_timing(detection_duration) // binwidth_ns)

        if self.mw_generator:
            self.mw_generator.prepare_for_odmr(mw_frequency / 1e9, -10.0)
            self.mw_generator.set_odmr_frequency(mw_frequency / 1e9)
            self.mw_generator.set_rf_output(False)

        print("📷 Reference transient (MW off)...")
        ref_counts = self._acquire_transient(False, sequence_kwargs, repetitions,
                                             binwidth_ns, n_bins, plot_sequence)
        if ref_counts is None:
            print("❌ Could not create the reference sequence")
            return {}

        print(f"📷 Signal transient (MW on at {mw_frequency/1e6:.2f} MHz)...")
        if self.mw_generator:
            self.mw_generator.set_rf_output(True)
            time.sleep(0.2)
        sig_counts = self._acquire_transient(True, sequence_kwargs, repetitions,
                                             binwidth_ns, n_bins, plot_sequence)
        if self.mw_generator:
            self.mw_generator.set_rf_output(False)
        if sig_counts is None:
            print("❌ Could not create the signal sequence")
            return {}

        # Time axis referenced to the readout laser edge: negative = dark bins before it
        aligned_pre_readout = self.pulse_controller.align_timing(pre_readout)
        times_ns = np.arange(n_bins) * binwidth_ns - aligned_pre_readout

        with np.errstate(divide='ignore', invalid='ignore'):
            contrast_per_bin = np.where(ref_counts > 0,
                                        (ref_counts - sig_counts) / ref_counts, np.nan)

        best = self._optimal_detection_window(times_ns, ref_counts, sig_counts,
                                              min_width_ns=min_window_ns)

        # A negative optimum start means the gate should open with the laser command edge;
        # the Rabi/pulsed ODMR sequences cannot express a negative detection_delay.
        recommended_delay = self.pulse_controller.align_timing(max(0, int(best['start_ns'])))
        recommended_duration = self.pulse_controller.align_timing(int(best['width_ns']))

        # Laser turn-on: first bin where the reference crosses half of its peak
        peak = ref_counts.max() if ref_counts.size else 0.0
        above_half = np.flatnonzero(ref_counts >= 0.5 * peak)
        laser_onset_ns = float(times_ns[above_half[0]]) if above_half.size else float('nan')

        # Repolarisation time from the spin-dependent part of the fluorescence
        tau_pol = float('nan')
        difference = ref_counts - sig_counts
        try:
            fit_mask = times_ns >= max(0.0, laser_onset_ns)
            decay = lambda t, A, tau, C: A * np.exp(-t / tau) + C
            p0 = [max(difference[fit_mask].max(), 1.0), 300.0, 0.0]
            popt, _ = curve_fit(decay, times_ns[fit_mask] - max(0.0, laser_onset_ns),
                                difference[fit_mask], p0=p0, maxfev=10000)
            tau_pol = float(popt[1])
        except Exception as e:
            print(f"Warning: repolarisation fit failed: {e}")

        print(f"\n📐 Laser turn-on (50% of peak): {laser_onset_ns:.0f} ns after the AOM edge")
        print(f"📐 Repolarisation time tau_pol: {tau_pol:.0f} ns")
        print(f"📐 Optimal window: start {best['start_ns']:.0f} ns, width {best['width_ns']:.0f} ns")
        print(f"📐 Contrast in that window: {best['contrast']*100:.2f} %")
        print(f"➡️  Use detection_delay={recommended_delay}, "
              f"detection_duration={recommended_duration}")

        self.results['readout_transient'] = {
            'times': times_ns,
            'ref_counts': ref_counts,
            'sig_counts': sig_counts,
            'difference': difference,
            'contrast_per_bin': contrast_per_bin,
            'best_window': best,
            'recommended_detection_delay': recommended_delay,
            'recommended_detection_duration': recommended_duration,
            'laser_onset_ns': laser_onset_ns,
            'tau_pol_ns': tau_pol,
            'parameters': {
                'mw_frequency': mw_frequency,
                'mw_duration': self.pulse_controller.align_timing(int(mw_duration)),
                'init_laser_duration': init_laser_duration,
                'readout_laser_duration': readout_laser_duration,
                'detection_duration': detection_duration,
                'init_laser_delay': init_laser_delay,
                'mw_gap': mw_gap,
                'readout_gap': readout_gap,
                'pre_readout': pre_readout,
                'sequence_interval': sequence_interval,
                'repetitions': repetitions,
                'binwidth_ns': binwidth_ns,
                'recommended_detection_delay': recommended_delay,
                'recommended_detection_duration': recommended_duration,
                'laser_onset_ns': laser_onset_ns,
                'tau_pol_ns': tau_pol,
                'optimal_window_contrast': best['contrast'],
            }
        }

        self._save_results('readout_transient', self.results['readout_transient'])
        print("✅ Readout transient measurement completed")
        return self.results['readout_transient']

    def t1_decay_contrast(self,
                          delay_times: List[int],
                          init_laser_duration: int = 1000,
                          readout_laser_duration: int = 1000,
                          detection_duration: int = 500,
                          init_laser_delay: int = 0,
                          detection_delay: int = 0,
                          sequence_interval: int = 10000,
                          repetitions: int = 1000,
                          plot_sequence: bool = False,
                          live_plot: bool = True,
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
            plot_sequence: If True, call sequence.plot() at each sweep point (blocks until closed)
            live_plot: If True, show a Signal/Reference plot that refreshes after each delay point
            progress_callback: Optional callback(delays, contrasts) for live updates

        Returns:
            Dictionary containing delays, contrasts, signal rates, and reference rates
        """
        print("🔬 Starting T1 contrast measurement...")

        delays = []
        contrasts = []
        sig_rates = []
        ref_rates = []

        live = None
        if live_plot and progress_callback is None:
            live = _LiveContrastPlot(xlabel='Delay (µs)', ylabel='Signal / Reference',
                                     title='T1 Contrast (live)', x_scale=1e3)

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
            if plot_sequence and sequence:
                sequence.plot()

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
                if live:
                    live.update(delays, contrasts)

                time.sleep(0.05)

        if live:
            live.close()

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

        if experiment_type in ('odmr_contrast', 'pulsed_odmr_contrast'):
            title = 'Pulsed ODMR' if experiment_type == 'pulsed_odmr_contrast' else 'ODMR'
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
            axes[0].set_title(f'{title} Contrast')
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
            ax_ratio.set_title(f'{title} – Signal / Reference')
            ax_ratio.legend()
            ax_ratio.grid(True, alpha=0.3)
            fig_ratio.tight_layout()

            fig_con, ax_con = plt.subplots(figsize=(10, 6))
            ax_con.plot(freqs, contrasts_pct, 'go-', label='Contrast = (ref − sig) / ref')
            ax_con.set_xlabel('Frequency (GHz)')
            ax_con.set_ylabel('Contrast (%)')
            ax_con.set_title(f'{title} – Contrast')
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

        elif experiment_type == 'readout_transient':
            times = np.array(data['times'])
            ref = np.array(data['ref_counts'])
            sig = np.array(data['sig_counts'])
            diff = np.array(data['difference'])
            contrast_pct = np.array(data['contrast_per_bin']) * 100
            best = data['best_window']
            win_start = best['start_ns']
            win_end = best['start_ns'] + best['width_ns']

            fig, axes = plt.gcf(), None
            plt.close(fig)
            fig, axes = plt.subplots(3, 1, figsize=(10, 14), sharex=True)

            axes[0].plot(times, ref, 'b-', label='Reference (MW off)')
            axes[0].plot(times, sig, 'r-', label='Signal (MW on)')
            axes[0].set_ylabel('Counts per bin')
            axes[0].set_title(f"Readout Transient – optimal window "
                              f"{win_start:.0f} to {win_end:.0f} ns, "
                              f"contrast {best['contrast']*100:.2f} %")
            axes[0].legend()
            axes[0].grid(True, alpha=0.3)

            axes[1].plot(times, diff, 'k-', label='Reference − Signal (spin-dependent)')
            tau_pol = data.get('tau_pol_ns', float('nan'))
            if np.isfinite(tau_pol):
                axes[1].axvline(tau_pol, color='c', linestyle=':', linewidth=2,
                                label=f'tau_pol = {tau_pol:.0f} ns')
            axes[1].set_ylabel('Counts per bin')
            axes[1].legend()
            axes[1].grid(True, alpha=0.3)

            axes[2].plot(times, contrast_pct, 'g-', label='Contrast per bin')
            axes[2].set_xlabel('Time since readout laser edge (ns)')
            axes[2].set_ylabel('Contrast (%)')
            axes[2].legend()
            axes[2].grid(True, alpha=0.3)

            for ax in axes:
                ax.axvspan(win_start, win_end, color='orange', alpha=0.15)
                ax.axvline(0, color='gray', linestyle='--', linewidth=1)

            plt.tight_layout()

            fig_win, ax_win = plt.subplots(figsize=(10, 6))
            ax_win.plot(times, ref, 'b-', label='Reference (MW off)')
            ax_win.plot(times, sig, 'r-', label='Signal (MW on)')
            ax_win.axvspan(win_start, win_end, color='orange', alpha=0.2,
                           label=f"Optimal window ({best['width_ns']:.0f} ns)")
            ax_win.axvline(0, color='gray', linestyle='--', linewidth=1,
                           label='Readout laser edge')
            ax_win.set_xlabel('Time since readout laser edge (ns)')
            ax_win.set_ylabel('Counts per bin')
            ax_win.set_title(f"Readout Transient – use detection_delay="
                             f"{data['recommended_detection_delay']}, "
                             f"detection_duration={data['recommended_detection_duration']}")
            ax_win.legend()
            ax_win.grid(True, alpha=0.3)
            fig_win.tight_layout()

            fig_snr, ax_snr = plt.subplots(figsize=(10, 6))
            ax_snr.plot(best['widths_ns'], best['snr_vs_width'], 'k-',
                        label=f"SNR at start = {win_start:.0f} ns")
            ax_snr.axvline(best['width_ns'], color='orange', linestyle='--', linewidth=2,
                           label=f"Optimum = {best['width_ns']:.0f} ns")
            ax_snr.set_xlabel('Detection window width (ns)')
            ax_snr.set_ylabel('Contrast SNR (arb.)')
            ax_snr.set_title('Readout Transient – window width optimisation')
            ax_snr.legend()
            ax_snr.grid(True, alpha=0.3)
            fig_snr.tight_layout()

            if base_path:
                fig.savefig(f"{base_path}.pdf", format='pdf', bbox_inches='tight')
                fig_win.savefig(f"{base_path}_window.pdf", format='pdf', bbox_inches='tight')
                fig_snr.savefig(f"{base_path}_snr.pdf", format='pdf', bbox_inches='tight')
                print(f"Plots saved to: {base_path}*.pdf")

            plt.show()
            return

        elif experiment_type == 't1_contrast':
            delays_us = np.array(data['delays']) / 1000  # ns -> µs
            sig = np.array(data['sig_rates'])
            ref = np.array(data['ref_rates'])
            sig_over_ref = np.array(data['contrasts'])

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
                stretched_exp = lambda t, A, T1, n, C: A * np.exp(-(t / T1) ** n) + C
                p0 = [sig_over_ref[0] - sig_over_ref[-1], delays_us[-1] / 3, 1.0, sig_over_ref[-1]]
                bounds = ([-np.inf, 0, 0.1, -np.inf], [np.inf, np.inf, 1.0, np.inf])
                popt, pcov = curve_fit(stretched_exp, delays_us, sig_over_ref,
                                       p0=p0, bounds=bounds, maxfev=10000)
                perr = np.sqrt(np.diag(pcov))
                mean_t1 = (popt[1] / popt[2]) * gamma_func(1.0 / popt[2])
                if use_log:
                    fit_t = np.logspace(np.log10(delays_us[0]), np.log10(delays_us[-1]), 500)
                else:
                    fit_t = np.linspace(delays_us[0], delays_us[-1], 500)
                fit_label = f'Fit: T1 = {popt[1]:.2f} ± {perr[1]:.2f} µs'
                axes[2].plot(fit_t, stretched_exp(fit_t, *popt), 'r-', linewidth=2, label=fit_label)
                print(f"T1 stretched-exp fit: A={popt[0]:.4f}, T1={popt[1]:.2f} ± {perr[1]:.2f} µs, "
                      f"n={popt[2]:.2f} ± {perr[2]:.2f}, C={popt[3]:.4f}, ⟨τ⟩={mean_t1:.2f} µs")
            except Exception as e:
                print(f"Warning: T1 stretched-exponential fit failed: {e}")
            axes[2].set_xlabel('Delay (µs)')
            axes[2].set_ylabel('Signal / Reference')
            axes[2].legend()
            axes[2].grid(True, alpha=0.3, which=grid_which)

            plt.tight_layout()

            fig_ratio, ax_ratio = plt.subplots(figsize=(10, 6))
            getattr(ax_ratio, plot_fn_name)(delays_us, sig_over_ref, 'mo', label='Signal / Reference')
            if fit_t is not None:
                try:
                    ax_ratio.plot(fit_t, stretched_exp(fit_t, *popt), 'r-', linewidth=2,
                                  label=fit_label)
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
    
    # Initialize RIGOL signal generator (IP from common.utils.RIGOL_IP)
    try:
        rigol = RigolDSG836Controller()
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
        #     laser_duration=100000,
        #     mw_duration=100000,
        #     detection_duration=100000,
        #     laser_delay=0,
        #     mw_delay=0,
        #     detection_delay=1500,
        #     sequence_interval=2000,
        #     repetitions=5000,
        #     plot_sequence=False,
        #     live_plot=True
        # )
        # experiments.plot_results('odmr_contrast')

        # 2. Readout transient — calibrates detection_delay and detection_duration
        #   Run this once after the CW ODMR, before Rabi, and feed the printed
        #   detection_delay / detection_duration into the experiments below.
        # print("\n" + "="*50)
        # transient_result = experiments.readout_transient(
        #     mw_frequency=2.846e9,          # use your NV ODMR resonance frequency
        #     mw_duration=1000,              # long saturating pulse, no calibration needed
        #     init_laser_duration=3000,
        #     readout_laser_duration=3000,   # long enough to contain the full transient
        #     init_laser_delay=0,
        #     mw_gap=500,
        #     readout_gap=500,
        #     pre_readout=200,               # dark bins before the laser edge
        #     sequence_interval=2000,
        #     repetitions=200000,
        #     binwidth_ns=4,
        #     plot_sequence=False
        # )
        # experiments.plot_results('readout_transient')

        # 3. Pulsed ODMR with contrast (same sequence as Rabi, MW duration fixed)
        # print("\n" + "="*50)
        # frequencies = np.linspace(2.8e9, 2.95e9, 80)   # 0.5 MHz steps around the CW dip
        # pulsed_odmr_result = experiments.pulsed_odmr_contrast(
        #     mw_frequencies=frequencies,
        #     mw_duration=1000,              # fixed; use the pi-pulse duration once known
        #     init_laser_duration=3000,
        #     readout_laser_duration=1000,
        #     detection_duration=300,
        #     init_laser_delay=0,
        #     mw_gap=500,
        #     readout_gap=500,
        #     detection_delay=100,
        #     sequence_interval=2000,
        #     repetitions=400000,
        #     plot_sequence=False,
        #     live_plot=True
        # )
        # experiments.plot_results('pulsed_odmr_contrast')

        # 4. Rabi oscillation with contrast (signal/reference normalisation)
        print("\n" + "="*50)
        mw_durations = np.linspace(0, 1008, 128)   # 0–504 ns, exact 8 ns steps
        rabi_contrast_result = experiments.rabi_oscillation_contrast(
            mw_durations=mw_durations,
            mw_frequency=2.846e9,          # use your NV ODMR resonance frequency
            init_laser_duration=3000,
            readout_laser_duration=1000,
            detection_duration=300,        # short gate: spin contrast lives in the first ~300 ns
            init_laser_delay=0,
            mw_gap=500,
            readout_gap=500,
            detection_delay=100,             # calibrate by sweeping it at fixed mw_duration
            sequence_interval=2000,
            repetitions=400000,
            plot_sequence=False,
            live_plot=True
        )
        experiments.plot_results('rabi_contrast')

        # 5. T1 decay with contrast (signal/reference normalisation)
        # print("\n" + "="*50)
        # delay_times = np.linspace(0, 30e6, 50)  # 0-10 µs in 50 steps
        # #delay_times = np.logspace(np.log10(0.5e3), np.log10(5e6), 50)
        # t1_contrast_result = experiments.t1_decay_contrast(
        #     delay_times=delay_times,
        #     init_laser_duration=50000,
        #     readout_laser_duration=50000,
        #     detection_duration=3000,
        #     init_laser_delay=0,
        #     detection_delay=1500,
        #     sequence_interval=2000,
        #     repetitions=3000,
        #     plot_sequence=False,
        #     live_plot=True
        # )
        # experiments.plot_results('t1_contrast')
        
        
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