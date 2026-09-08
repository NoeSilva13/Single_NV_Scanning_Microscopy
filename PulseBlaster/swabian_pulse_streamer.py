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
    
    def __init__(self, ip_address: Optional[str] = None):
        """
        Initialize the Pulse Streamer controller.
        
        Args:
            ip_address: Pulse Streamer IP. Defaults to ``common.utils.PULSE_STREAMER_IP``.
        """
        if ip_address is None:
            from common.utils import PULSE_STREAMER_IP
            ip_address = PULSE_STREAMER_IP
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
            self.pulse_streamer.constant(OutputState.ZERO())
            print("🔄 Pulse Streamer reset to OFF state")
        except Exception as e:
            print(f"❌ Error resetting device: {e}")
    
    def create_odmr_sequence_contrast(self,
                           laser_duration: int = None,
                           mw_duration: int = None,
                           detection_duration: int = None,
                           laser_delay: int = None,
                           mw_delay: int = None,
                           detection_delay: int = None,
                           sequence_interval: int = None) -> Optional[Sequence]:
        """
        Create an ODMR contrast pulse sequence following proper 8ns pattern building.

        Each sequence run contains two sub-sequences back-to-back:
          1. MW off sub-sequence  — reference measurement (even bins)
          2. MW on  sub-sequence  — signal  measurement  (odd  bins)

        The AOM and SPD patterns are identical in both halves so the laser
        excitation and detection window are the same.  Only the MW channel
        differs: off in the first half, on in the second half.

        Args:
            laser_duration: Duration of laser pulse in ns
            mw_duration: Duration of MW pulse in ns
            detection_duration: Duration of detection window in ns
            laser_delay: Delay before laser pulse in ns
            mw_delay: Delay before MW pulse in ns
            detection_delay: Delay before detection in ns
            sequence_interval: Dead time appended after each sub-sequence in ns

        Returns:
            Tuple (Sequence, total_duration_ns) or None if error
        """
        if not self.is_connected:
            print("❌ Device not connected")
            return None

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
            single_seq_duration = max(
                params['laser_delay'] + params['laser_duration'],
                params['mw_delay'] + params['mw_duration'],
                params['detection_delay'] + params['detection_duration']
            )
            single_seq_duration = self.align_timing(single_seq_duration)

            aom_pattern = self._create_laser_pattern(params, single_seq_duration)
            mw_pattern = self._create_mw_pattern(params, single_seq_duration)
            mw_pattern_off = self._create_mw_pattern_off(params, single_seq_duration)
            spd_pattern = self._create_spd_pattern(params, single_seq_duration)

            total_duration = sum(duration for duration, _ in aom_pattern)
            if total_duration % 8 != 0:
                print(f"❌ Error: Total sequence length ({total_duration} ns) not multiple of 8 ns")
                return None

            sequence = self.pulse_streamer.createSequence()
            # Two sub-sequences concatenated: [MW off | MW on]
            sequence.setDigital(self.CHANNEL_AOM, aom_pattern + aom_pattern)
            sequence.setDigital(self.CHANNEL_MW, mw_pattern_off + mw_pattern)
            sequence.setDigital(self.CHANNEL_SPD, spd_pattern + spd_pattern)

            full_duration = total_duration * 2
            print(f"✅ ODMR contrast sequence created: {full_duration} ns total ({total_duration} ns per sub-sequence, 8ns aligned)")

            return sequence, full_duration

        except Exception as e:
            print(f"❌ Error creating ODMR contrast sequence: {e}")
            return None

    def _create_laser_pattern(self, params: Dict, seq_duration: int) -> List[Tuple[int, int]]:
        """Create laser (AOM) pattern array for a single repetition."""
        pattern = []

        # Laser pulse timing
        if params['laser_delay'] > 0:
            pattern.append((params['laser_delay'], 0))
        pattern.append((params['laser_duration'], 1))

        # Fill remaining time to sequence duration (excluding interval)
        used_time = params['laser_delay'] + params['laser_duration']
        remaining_time = seq_duration - used_time
        if remaining_time > 0:
            pattern.append((remaining_time, 0))

        # Append sequence interval at the end
        pattern.append((params['sequence_interval'], 0))

        return pattern
    
    def _create_mw_pattern(self, params: Dict, seq_duration: int) -> List[Tuple[int, int]]:
        """Create microwave pattern array for a single repetition."""
        pattern = []

        # MW pulse timing
        if params['mw_delay'] > 0:
            pattern.append((params['mw_delay'], 0))
        pattern.append((params['mw_duration'], 1))

        # Fill remaining time to sequence duration (excluding interval)
        used_time = params['mw_delay'] + params['mw_duration']
        remaining_time = seq_duration - used_time
        if remaining_time > 0:
            pattern.append((remaining_time, 0))

        # Append sequence interval at the end
        pattern.append((params['sequence_interval'], 0))

        return pattern
    
    def _create_mw_pattern_off(self, params: Dict, seq_duration: int) -> List[Tuple[int, int]]:
        """Create microwave pattern array (always off) for a single repetition."""
        pattern = []

        if params['mw_delay'] > 0:
            pattern.append((params['mw_delay'], 0))
        pattern.append((params['mw_duration'], 0))

        used_time = params['mw_delay'] + params['mw_duration']
        remaining_time = seq_duration - used_time
        if remaining_time > 0:
            pattern.append((remaining_time, 0))

        pattern.append((params['sequence_interval'], 0))

        return pattern

    def _create_spd_pattern(self, params: Dict, seq_duration: int) -> List[Tuple[int, int]]:
        """Create SPD gate pattern array for a single repetition."""
        pattern = []

        # SPD gate timing
        if params['detection_delay'] > 0:
            pattern.append((params['detection_delay'], 0))
        pattern.append((params['detection_duration'], 1))

        # Fill remaining time to sequence duration (excluding interval)
        used_time = params['detection_delay'] + params['detection_duration']
        remaining_time = seq_duration - used_time
        if remaining_time > 0:
            pattern.append((remaining_time, 0))

        # Append sequence interval at the end
        pattern.append((params['sequence_interval'], 0))

        return pattern

    def create_rabi_sequence_contrast(self,
                                      init_laser_duration: int,
                                      readout_laser_duration: int,
                                      mw_duration: int,
                                      detection_duration: int,
                                      init_laser_delay: int = 0,
                                      mw_gap: int = 0,
                                      readout_gap: int = 0,
                                      detection_delay: int = 0,
                                      sequence_interval: int = 10000) -> Optional[Tuple]:
        """
        Create a Rabi oscillation contrast pulse sequence.

        Each sequence run contains two identical sub-sequences back-to-back.
        Only the MW channel differs (off in the reference half, on in the signal half).
        Both halves use the same AOM and SPD timing so the detection windows are
        optically equivalent — required for a meaningful interleaved contrast.

          AOM: |── init laser ──| ← mw_gap → [MW slot τ] ← readout_gap → |── readout ──| interval |
          MW:                     (OFF / ON for duration τ)
          SPD:                                                         |detect|          interval |
                                                                       ↑ readout + detection_delay

        Even bins (0, 2, 4, ...): reference — MW off, readout of ms=0 bright state
        Odd  bins (1, 3, 5, ...): signal    — MW on(τ), readout after spin rotation

        Args:
            init_laser_duration: Duration of initialization laser pulse in ns
            readout_laser_duration: Duration of readout laser pulse in ns.
                                    Must be >= detection_duration + detection_delay
                                    so the SPD window fits inside the readout pulse.
            mw_duration: Duration of the MW pulse (τ) in ns
            detection_duration: Duration of the SPD detection window in ns
            init_laser_delay: Delay before the initialization laser in ns
            mw_gap: Dark time between end of init laser and start of MW in ns
            readout_gap: Dark time between end of MW and start of readout in ns
            detection_delay: Offset of the SPD gate relative to the readout laser
                             edge, to compensate for AOM turn-on delay in ns
            sequence_interval: Idle time appended after each sub-sequence in ns

        Returns:
            Tuple (Sequence, total_duration_ns) or None if error
        """
        if not self.is_connected:
            print("❌ Device not connected")
            return None

        try:
            init_laser_duration    = self.align_timing(init_laser_duration)
            readout_laser_duration = self.align_timing(readout_laser_duration)
            mw_duration            = self.align_timing(mw_duration)
            detection_duration     = self.align_timing(detection_duration)
            init_laser_delay       = self.align_timing(init_laser_delay)
            mw_gap                 = self.align_timing(mw_gap)
            readout_gap            = self.align_timing(readout_gap)
            detection_delay        = self.align_timing(detection_delay)
            sequence_interval      = self.align_timing(sequence_interval)

            if readout_laser_duration < detection_delay + detection_duration:
                print(f"❌ Error: readout_laser_duration ({readout_laser_duration} ns) must be "
                      f">= detection_delay + detection_duration "
                      f"({detection_delay + detection_duration} ns) so the SPD window "
                      f"fits inside the readout pulse.")
                return None

            init_end      = init_laser_delay + init_laser_duration
            mw_start      = init_end + mw_gap
            mw_end        = mw_start + mw_duration
            readout_start = mw_end + readout_gap
            detect_start  = self.align_timing(readout_start + detection_delay)

            single_seq_duration = self.align_timing(max(
                readout_start + readout_laser_duration,
                detect_start + detection_duration
            ))

            # AOM: init | mw_gap | (MW slot, laser OFF) | readout_gap | readout | fill | interval
            aom_pattern = []
            if init_laser_delay > 0:
                aom_pattern.append((init_laser_delay, 0))
            aom_pattern.append((init_laser_duration, 1))

            if mw_gap > 0:
                aom_pattern.append((mw_gap, 0))
            if mw_duration > 0:
                aom_pattern.append((mw_duration, 0))
            if readout_gap > 0:
                aom_pattern.append((readout_gap, 0))
            aom_pattern.append((readout_laser_duration, 1))

            used_aom = readout_start + readout_laser_duration
            remaining_aom = single_seq_duration - used_aom
            if remaining_aom > 0:
                aom_pattern.append((remaining_aom, 0))
            if sequence_interval > 0:
                aom_pattern.append((sequence_interval, 0))

            # MW: OFF during init/gaps/readout; ON only in the MW slot (signal half)
            def _build_mw_pattern(mw_on: bool) -> List[Tuple[int, int]]:
                pattern = []
                if mw_start > 0:
                    pattern.append((mw_start, 0))
                if mw_duration > 0:
                    pattern.append((mw_duration, 1 if mw_on else 0))
                used_mw = mw_start + mw_duration
                remaining_mw = single_seq_duration - used_mw
                if remaining_mw > 0:
                    pattern.append((remaining_mw, 0))
                if sequence_interval > 0:
                    pattern.append((sequence_interval, 0))
                return pattern

            mw_pattern_off = _build_mw_pattern(mw_on=False)
            mw_pattern_on  = _build_mw_pattern(mw_on=True)

            # SPD: same readout window in both halves (symmetric contrast)
            spd_pattern = []
            if detect_start > 0:
                spd_pattern.append((detect_start, 0))
            spd_pattern.append((detection_duration, 1))

            used_spd = detect_start + detection_duration
            remaining_spd = single_seq_duration - used_spd
            if remaining_spd > 0:
                spd_pattern.append((remaining_spd, 0))
            if sequence_interval > 0:
                spd_pattern.append((sequence_interval, 0))

            total_duration = sum(d for d, _ in aom_pattern)
            if total_duration % 8 != 0:
                print(f"❌ Error: Total sequence length ({total_duration} ns) not multiple of 8 ns")
                return None

            # Two sub-sequences: [MW off | MW on] with identical AOM and SPD
            sequence = self.pulse_streamer.createSequence()
            sequence.setDigital(self.CHANNEL_AOM, aom_pattern + aom_pattern)
            sequence.setDigital(self.CHANNEL_MW, mw_pattern_off + mw_pattern_on)
            sequence.setDigital(self.CHANNEL_SPD, spd_pattern + spd_pattern)

            full_duration = total_duration * 2
            print(f"✅ Rabi contrast sequence created: τ={mw_duration} ns, "
                  f"{full_duration} ns total ({total_duration} ns per sub-sequence, 8ns aligned)")

            return sequence, full_duration

        except Exception as e:
            print(f"❌ Error creating Rabi contrast sequence: {e}")
            return None

    def create_readout_transient_sequence(self,
                                          init_laser_duration: int,
                                          readout_laser_duration: int,
                                          mw_duration: int,
                                          detection_duration: int,
                                          mw_on: bool,
                                          init_laser_delay: int = 0,
                                          mw_gap: int = 0,
                                          readout_gap: int = 0,
                                          pre_readout: int = 0,
                                          sequence_interval: int = 10000) -> Optional[Tuple]:
        """
        Create a single-half sequence for time-resolved readout characterisation.

        This is the Rabi contrast sequence reduced to ONE sub-sequence, with the SPD
        gate opened wide enough to span the whole readout pulse. It is meant to be
        combined with a TimeTagger.Histogram started on the SPD gate rising edge, so
        that the photon arrival time distribution during the readout pulse is measured
        directly instead of being integrated into a single number.

        Only one sub-sequence is emitted, so each run produces exactly one gate edge
        and the histogram is unambiguous. The MW state is fixed for the whole run
        (mw_on), which means two runs are needed to obtain the reference and signal
        transients.

          AOM: |── init ──| ← mw_gap → [MW slot τ] ← readout_gap → |── readout ──| interval |
          MW:                     (OFF / ON for the whole run)
          SPD:                                            |───── wide gate ─────|  interval |
                                                          ↑ readout − pre_readout

        Opening the gate pre_readout nanoseconds before the readout laser edge puts a
        few dark bins at the start of the histogram. Those bins give the background
        level and make the laser turn-on visible as a step, which is what allows the
        electronic latency to be read off the data rather than guessed.

        Args:
            init_laser_duration: Duration of initialization laser pulse in ns
            readout_laser_duration: Duration of readout laser pulse in ns
            mw_duration: Duration of the MW slot in ns
            detection_duration: Width of the SPD gate in ns. Should be at least
                                pre_readout + readout_laser_duration so the gate
                                spans the whole readout pulse.
            mw_on: If True the MW channel is high during the MW slot (signal
                   transient); if False it stays low (reference transient)
            init_laser_delay: Delay before the initialization laser in ns
            mw_gap: Dark time between end of init laser and start of MW in ns
            readout_gap: Dark time between end of MW and start of readout in ns.
                         Must be >= pre_readout so the gate does not open while
                         the MW pulse is still on.
            pre_readout: How long before the readout laser edge the SPD gate opens in ns
            sequence_interval: Idle time appended after the sub-sequence in ns

        Returns:
            Tuple (Sequence, total_duration_ns) or None if error
        """
        if not self.is_connected:
            print("❌ Device not connected")
            return None

        try:
            init_laser_duration    = self.align_timing(init_laser_duration)
            readout_laser_duration = self.align_timing(readout_laser_duration)
            mw_duration            = self.align_timing(mw_duration)
            detection_duration     = self.align_timing(detection_duration)
            init_laser_delay       = self.align_timing(init_laser_delay)
            mw_gap                 = self.align_timing(mw_gap)
            readout_gap            = self.align_timing(readout_gap)
            pre_readout            = self.align_timing(pre_readout)
            sequence_interval      = self.align_timing(sequence_interval)

            if readout_gap < pre_readout:
                print(f"❌ Error: readout_gap ({readout_gap} ns) must be >= pre_readout "
                      f"({pre_readout} ns) so the SPD gate does not open during the MW pulse.")
                return None

            init_end      = init_laser_delay + init_laser_duration
            mw_start      = init_end + mw_gap
            mw_end        = mw_start + mw_duration
            readout_start = mw_end + readout_gap
            detect_start  = self.align_timing(readout_start - pre_readout)

            single_seq_duration = self.align_timing(max(
                readout_start + readout_laser_duration,
                detect_start + detection_duration
            ))

            # AOM: init | mw_gap | (MW slot, laser OFF) | readout_gap | readout | fill | interval
            aom_pattern = []
            if init_laser_delay > 0:
                aom_pattern.append((init_laser_delay, 0))
            aom_pattern.append((init_laser_duration, 1))

            if mw_gap > 0:
                aom_pattern.append((mw_gap, 0))
            if mw_duration > 0:
                aom_pattern.append((mw_duration, 0))
            if readout_gap > 0:
                aom_pattern.append((readout_gap, 0))
            aom_pattern.append((readout_laser_duration, 1))

            used_aom = readout_start + readout_laser_duration
            remaining_aom = single_seq_duration - used_aom
            if remaining_aom > 0:
                aom_pattern.append((remaining_aom, 0))
            if sequence_interval > 0:
                aom_pattern.append((sequence_interval, 0))

            # MW: high during the MW slot only when mw_on
            mw_pattern = []
            if mw_start > 0:
                mw_pattern.append((mw_start, 0))
            if mw_duration > 0:
                mw_pattern.append((mw_duration, 1 if mw_on else 0))
            remaining_mw = single_seq_duration - (mw_start + mw_duration)
            if remaining_mw > 0:
                mw_pattern.append((remaining_mw, 0))
            if sequence_interval > 0:
                mw_pattern.append((sequence_interval, 0))

            # SPD: one wide gate spanning the readout pulse
            spd_pattern = []
            if detect_start > 0:
                spd_pattern.append((detect_start, 0))
            spd_pattern.append((detection_duration, 1))

            remaining_spd = single_seq_duration - (detect_start + detection_duration)
            if remaining_spd > 0:
                spd_pattern.append((remaining_spd, 0))
            if sequence_interval > 0:
                spd_pattern.append((sequence_interval, 0))

            total_duration = sum(d for d, _ in aom_pattern)
            if total_duration % 8 != 0:
                print(f"❌ Error: Total sequence length ({total_duration} ns) not multiple of 8 ns")
                return None

            sequence = self.pulse_streamer.createSequence()
            sequence.setDigital(self.CHANNEL_AOM, aom_pattern)
            sequence.setDigital(self.CHANNEL_MW, mw_pattern)
            sequence.setDigital(self.CHANNEL_SPD, spd_pattern)

            print(f"✅ Readout transient sequence created: MW {'ON' if mw_on else 'OFF'}, "
                  f"gate={detection_duration} ns opening {pre_readout} ns before readout, "
                  f"{total_duration} ns total (8ns aligned)")

            return sequence, total_duration

        except Exception as e:
            print(f"❌ Error creating readout transient sequence: {e}")
            return None

    def run_sequence(self, sequence: Sequence, n_runs: int = None):
        """
        Upload and run a pulse sequence.

        Args:
            sequence: The pulse sequence to run
            n_runs: Number of times to repeat the sequence. If None, runs infinitely.
        """
        if not self.is_connected or sequence is None:
            print("❌ Cannot run sequence: device not connected or sequence is None")
            return

        try:
            if n_runs is None:
                # Run infinitely by default
                self.pulse_streamer.stream(sequence, PulseStreamer.REPEAT_INFINITELY)
                print("🚀 Pulse sequence started (infinite repetitions)")
            else:
                # Run specified number of times
                self.pulse_streamer.stream(sequence, n_runs)
                print(f"🚀 Pulse sequence started ({n_runs} repetitions)")
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
    
    def _create_t1_sequence_contrast(self,
                                     init_laser_duration: int,
                                     readout_laser_duration: int,
                                     detection_duration: int,
                                     delay_time: int,
                                     init_laser_delay: int,
                                     sequence_interval: int,
                                     detection_delay: int = 0) -> Optional[Tuple]:
        """
        Create T1 contrast pulse sequence using a single sequence with two SPD windows.

        The init laser pulse serves as the reference measurement, and the readout
        laser pulse (after the variable delay τ) serves as the signal measurement.
        Each sequence repetition therefore produces two detection bins:

          AOM: |──────── init laser ────────| ← delay_time → |── readout laser ──| fill | interval |
          SPD:                     |ref bin|                       |sig bin|       fill | interval |
               ← NV polarising →  ↑ fully initialised             ↑ + detection_delay (AOM comp.)

        Even bins (0, 2, 4, ...): reference — fluorescence at the end of the init laser
                                  (NV fully polarised into ms=0 bright state)
        Odd  bins (1, 3, 5, ...): signal    — fluorescence at the start of the readout
                                  laser after delay τ (partially relaxed state)

        The reference window is placed at the trailing end of the init laser so the
        NV has reached steady-state polarisation.  detection_delay is only applied to
        the signal window to compensate for the AOM turn-on delay at the readout pulse.

        Because contrast normalisation (sig/ref) removes period-dependent effects,
        the sequence duration naturally varies with delay_time — no fixed-period
        padding is needed.

        Args:
            init_laser_duration: Duration of initialization laser pulse in ns.
                                 Must be >= detection_duration so the reference window
                                 fits inside the init laser pulse.
            readout_laser_duration: Duration of readout laser pulse in ns
            detection_duration: Duration of each detection window in ns
            delay_time: Dark time between init and readout in ns
            init_laser_delay: Delay before initialization laser in ns
            sequence_interval: Idle time appended after the sequence in ns
            detection_delay: Offset added to the signal SPD gate start relative to the
                             readout laser edge, to compensate for AOM delay response in ns

        Returns:
            Tuple (Sequence, total_duration_ns) or None if error
        """
        if not self.is_connected:
            print("❌ Device not connected")
            return None

        try:
            init_laser_duration    = self.align_timing(init_laser_duration)
            readout_laser_duration = self.align_timing(readout_laser_duration)
            detection_duration     = self.align_timing(detection_duration)
            delay_time             = self.align_timing(delay_time)
            init_laser_delay       = self.align_timing(init_laser_delay)
            sequence_interval      = self.align_timing(sequence_interval)
            detection_delay        = self.align_timing(detection_delay)

            if init_laser_duration < detection_duration:
                print(f"❌ Error: init_laser_duration ({init_laser_duration} ns) must be "
                      f">= detection_duration ({detection_duration} ns) so the reference "
                      f"window fits inside the init laser pulse.")
                return None

            readout_laser_delay = self.align_timing(init_laser_delay + init_laser_duration + delay_time)

            # Reference window: trailing end of init laser (NV fully polarised)
            ref_detection_start = self.align_timing(
                init_laser_delay + init_laser_duration - detection_duration)
            # Signal window: start of readout laser + AOM compensation
            sig_detection_start = self.align_timing(readout_laser_delay + detection_delay)

            single_seq_duration = self.align_timing(max(
                init_laser_delay    + init_laser_duration,
                readout_laser_delay + readout_laser_duration,
                sig_detection_start + detection_duration
            ))

            # AOM: init laser | gap | readout laser | fill | interval
            aom_pattern = []
            if init_laser_delay > 0:
                aom_pattern.append((init_laser_delay, 0))
            aom_pattern.append((init_laser_duration, 1))

            time_to_readout = readout_laser_delay - (init_laser_delay + init_laser_duration)
            if time_to_readout > 0:
                aom_pattern.append((time_to_readout, 0))
            aom_pattern.append((readout_laser_duration, 1))

            used_aom = readout_laser_delay + readout_laser_duration
            remaining_aom = single_seq_duration - used_aom
            if remaining_aom > 0:
                aom_pattern.append((remaining_aom, 0))
            if sequence_interval > 0:
                aom_pattern.append((sequence_interval, 0))

            # SPD: reference window (during init laser) then signal window (during readout laser)
            gap_between_windows = sig_detection_start - (ref_detection_start + detection_duration)
            if gap_between_windows < 0:
                print(f"❌ Error: SPD windows overlap (gap={gap_between_windows} ns). "
                      f"Reduce detection_duration or increase init_laser_duration / delay_time.")
                return None

            spd_pattern = []
            if ref_detection_start > 0:
                spd_pattern.append((ref_detection_start, 0))
            spd_pattern.append((detection_duration, 1))

            if gap_between_windows > 0:
                spd_pattern.append((gap_between_windows, 0))
            spd_pattern.append((detection_duration, 1))

            used_spd = sig_detection_start + detection_duration
            remaining_spd = single_seq_duration - used_spd
            if remaining_spd > 0:
                spd_pattern.append((remaining_spd, 0))
            if sequence_interval > 0:
                spd_pattern.append((sequence_interval, 0))

            total_duration = sum(d for d, _ in aom_pattern)
            if total_duration % 8 != 0:
                print(f"❌ Error: T1 contrast sequence length ({total_duration} ns) not multiple of 8 ns")
                return None

            sequence = self.pulse_streamer.createSequence()
            sequence.setDigital(self.CHANNEL_AOM, aom_pattern)
            sequence.setDigital(self.CHANNEL_SPD, spd_pattern)

            print(f"✅ T1 contrast sequence created: delay={delay_time}ns, "
                  f"{total_duration} ns total (interval={sequence_interval}ns)")

            return sequence, total_duration

        except Exception as e:
            print(f"❌ Error creating T1 contrast sequence: {e}")
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