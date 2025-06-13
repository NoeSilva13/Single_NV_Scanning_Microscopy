# PulseBlaster - Swabian Pulse Streamer 8/2 Controller

This module provides pulse generation control for ODMR (Optically Detected Magnetic Resonance) experiments with Nitrogen-Vacancy (NV) centers using the Swabian Pulse Streamer 8/2.

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

### `odmr_experiments.py`
Example experiment implementations including:
- Continuous Wave ODMR
- Rabi oscillation measurements
- Ramsey coherence experiments
- Spin echo measurements

## Installation

1. Install the Swabian PulseStreamer library:
```bash
pip install pulsestreamer
```

2. Ensure your Pulse Streamer device is connected and accessible at IP address `169.254.8.2` (default).

## Quick Start

```python
from PulseBlaster.swabian_pulse_streamer import SwabianPulseController

# Initialize controller
controller = SwabianPulseController()

# Create a simple laser pulse
laser_seq = controller.create_simple_laser_pulse(1000)  # 1 µs pulse

# Run the sequence
controller.run_sequence(laser_seq)

# Stop and disconnect
controller.stop_sequence()
controller.disconnect()
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

- Swabian Pulse Streamer 8/2
- AOM for laser control
- Microwave source
- Single photon detector (SPD)
- Appropriate RF/optical connections

## Notes

- All timing parameters are specified in nanoseconds
- The device IP address can be configured during initialization
- Error handling is built-in for device connection issues
- Sequences support overlapping pulses with automatic timing management 