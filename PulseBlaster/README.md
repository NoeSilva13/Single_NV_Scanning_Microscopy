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
Integrated experiment implementations including:
- Continuous Wave ODMR with automatic MW frequency control
- Rabi oscillation measurements with MW power management
- Automated ODMR sweeps using RIGOL's internal frequency sweep
- Ramsey coherence and spin echo experiments

## Installation

1. Install the Swabian PulseStreamer library:
```bash
pip install pulsestreamer
```

2. Ensure your instruments are connected and accessible:
   - Pulse Streamer 8/2 at IP address `192.168.0.201` (default)
   - RIGOL DSG836 Signal Generator at IP address `192.168.0.222` (default)

## Quick Start

### Basic Pulse Control
```python
from PulseBlaster.swabian_pulse_streamer import SwabianPulseController

# Initialize controller
controller = SwabianPulseController("192.168.0.201")

# Create a simple laser pulse
laser_seq = controller.create_simple_laser_pulse(1000)  # 1 µs pulse

# Run the sequence
controller.run_sequence(laser_seq)

# Stop and disconnect
controller.stop_sequence()
controller.disconnect()
```

### ODMR with RIGOL Signal Generator
```python
from PulseBlaster import SwabianPulseController, RigolDSG836Controller, ODMRExperiments

# Initialize instruments
pulse_controller = SwabianPulseController("192.168.0.201")
rigol = RigolDSG836Controller("192.168.0.222")

# Connect to both instruments
pulse_controller.connect()
rigol.connect()

# Initialize experiments
experiments = ODMRExperiments(pulse_controller, rigol)

# Run ODMR sweep
frequencies = [2.85e9, 2.87e9, 2.89e9]  # MHz
results = experiments.odmr(frequencies)

# Plot results
experiments.plot_results('odmr')

# Clean up
rigol.set_rf_output(False)
rigol.disconnect()
pulse_controller.disconnect()
```

## ODMR Sequence Example

```python
# Create ODMR sequence
odmr_seq = controller.create_odmr_sequence(
    laser_duration=1000,      # 1 µs laser pulse
    mw_duration=100,          # 100 ns MW pulse
    detection_duration=500,   # 500 ns detection window
    repetitions=1000          # 1000 repetitions
)

# Run the sequence
controller.run_sequence(odmr_seq)
```

## Default Timing Parameters

- Laser duration: 1 µs
- MW duration: 100 ns
- Detection duration: 500 ns
- Laser delay: 50 ns
- MW delay: 100 ns
- Detection delay: 200 ns
- Sequence interval: 10 µs

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
