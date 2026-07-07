# PulseBlaster - ODMR Control System

This module provides comprehensive control for ODMR (Optically Detected Magnetic Resonance) experiments with Nitrogen-Vacancy (NV) centers using:
- **Swabian Pulse Streamer 8/2** for precise pulse timing
- **RIGOL DSG836 Signal Generator** for microwave control

## Channel Assignment

- **Channel 0**: AOM Laser control
- **Channel 1**: Microwave (MW) control  
- **Channel 2**: Single Photon Detector (SPD) gate

## Files

### `swabian_pulse_streamer.py`
Main controller class for the Pulse Streamer device. Provides:
- Device connection and initialization
- Basic pulse sequence creation (ODMR, Rabi, etc.)
- Sequence execution and control
- Error handling and device status monitoring

### `rigol_dsg836.py`
RIGOL DSG836 Signal Generator controller providing:
- Ethernet connection and SCPI command interface
- Frequency and power control for ODMR experiments
- RF output switching and sweep functionality
- Error handling and status monitoring

### `odmr_experiments.py`
Integrated experiment implementations (all using the interleaved signal/reference **contrast** method for common-mode noise rejection), consumed directly by `odmr_gui_qt.py`:
- `odmr_contrast()` - Continuous-wave frequency sweep with interleaved MW-off/MW-on measurement per point
- `rabi_oscillation_contrast()` - Microwave-duration sweep at fixed frequency to observe Rabi oscillations
- `t1_decay_contrast()` - Dark-time delay sweep between init/readout laser pulses to measure T1, with automatic stretched-exponential curve fitting (`scipy.optimize.curve_fit`)
- `plot_results()` - Generates and saves PDF summary plots for any of the three experiment types

> Note: Ramsey and spin-echo sequences are not currently implemented; only ODMR, Rabi, and T1 are available.

## Installation

1. Install the Swabian PulseStreamer library:
```bash
pip install pulsestreamer
```

2. Ensure your instruments are connected and accessible:
   - Pulse Streamer 8/2 at IP address `192.168.0.203` (default used by `odmr_gui_qt.py`; the `SwabianPulseController` class default is also `192.168.0.203`)
   - RIGOL DSG836 Signal Generator at IP address `192.168.0.223` (default used by `odmr_gui_qt.py`; note the standalone `RigolDSG836Controller` class default differs at `192.168.0.224` - always confirm the IP configured in the GUI's Device Settings tab)

## Quick Start

### Basic Pulse Control
```python
from PulseBlaster.swabian_pulse_streamer import SwabianPulseController

# Initialize controller (connects automatically on construction)
controller = SwabianPulseController("192.168.0.203")

# Create a laser-only pulse sequence for a T1 measurement
sequence, duration_ns = controller._create_t1_sequence_contrast(
    init_laser_duration=1000,
    readout_laser_duration=1000,
    detection_duration=500,
    delay_time=2000,
    init_laser_delay=0,
    sequence_interval=10000
)

# Run the sequence for a fixed number of repetitions
controller.run_sequence(sequence, n_runs=1000)

# Stop and disconnect
controller.stop_sequence()
controller.disconnect()
```

### ODMR with RIGOL Signal Generator
```python
from PulseBlaster import SwabianPulseController, RigolDSG836Controller, ODMRExperiments
import numpy as np

# Initialize instruments (SwabianPulseController connects automatically)
pulse_controller = SwabianPulseController("192.168.0.203")
rigol = RigolDSG836Controller("192.168.0.223")
rigol.connect()

# Initialize experiments (also connects to TimeTagger: real -> network -> virtual fallback)
experiments = ODMRExperiments(pulse_controller, rigol)

# Run an ODMR contrast sweep
frequencies = np.linspace(2.80e9, 2.90e9, 101)
results = experiments.odmr_contrast(
    mw_frequencies=frequencies,
    laser_duration=2000,
    mw_duration=2000,
    detection_duration=1000,
    repetitions=100
)

# Plot + save summary figures
experiments.plot_results('odmr_contrast')

# Clean up
rigol.set_rf_output(False)
rigol.disconnect()
pulse_controller.disconnect()
experiments.cleanup()
```

## ODMR Sequence Example

```python
# Create an ODMR contrast sequence (MW-off + MW-on sub-sequences back-to-back)
odmr_seq, total_duration_ns = controller.create_odmr_sequence_contrast(
    laser_duration=1000,      # 1 µs laser pulse
    mw_duration=104,          # MW pulse (rounded up to nearest 8 ns)
    detection_duration=504,   # Detection window (rounded up to nearest 8 ns)
    sequence_interval=10000
)

# Run the sequence for a fixed number of repetitions
controller.run_sequence(odmr_seq, n_runs=1000)
```

## Default Timing Parameters

`SwabianPulseController.default_params` (all values in nanoseconds, aligned to 8 ns boundaries by `align_timing`):

- Laser duration: 1000 ns (1 µs)
- MW duration: 104 ns
- Detection duration: 504 ns
- Laser delay: 48 ns
- MW delay: 104 ns
- Detection delay: 200 ns
- Sequence interval: 10000 ns (10 µs)

These are only starting points; `odmr_gui_qt.py` and `odmr_experiments.py` methods accept explicit overrides for every parameter per-measurement.

## Hardware Requirements

- **Swabian Pulse Streamer 8/2** - Precise pulse timing control
- **RIGOL DSG836 Signal Generator** - Microwave source (1-6 GHz)
- **AOM (Acousto-Optic Modulator)** for laser control
- **Single Photon Detector (SPD)** with TTL gate input
- **NV Diamond Sample** with appropriate optics
- **Network connections** for both instruments (Ethernet)

## Notes

- All timing parameters are specified in nanoseconds
- The device IP address can be configured during initialization
- Error handling is built-in for device connection issues
- Sequences support overlapping pulses with automatic timing management 

---
### Contact
For questions and support:
- Contact: **Javier Noé Ramos Silva** ‑ *jramossi@uci.edu*  
- Lab [Burke Lab](https://www.burkelab.com/) – Department of Electrical Engineering and Computer Science, University of California, Irvine
