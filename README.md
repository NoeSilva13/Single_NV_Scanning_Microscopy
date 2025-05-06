# Single NV Scanning Microscopy

This Python project provides software control for a Single Nitrogen-Vacancy (NV) Scanning Microscopy system. The setup is based on the **Thorlabs LSKGG4 Galvo-Galvo Scanner** and the **NI USB-6453 Data Acquisition (DAQ) device**.

## Overview

The system enables two-dimensional imaging of samples by scanning with high precision and detecting single photons emitted by NV centers in diamond. Two types of detectors are supported:

- **Avalanche Photodiode (APD)**
- **Excelitas SPCM-AQRH-10-FC Single Photon Counting Module**

These detectors are used to collect fluorescence data from the sample as it is scanned, enabling high-resolution image reconstruction.

## Features

- Real-time control of galvo scanners
- Synchronization with single-photon detectors
- Real-time image acquisition and visualization
- Support for both real-time and buffered scanning modes
- Configurable scan parameters and hardware settings
- Interactive visualization with live updates

## Requirements

- **Hardware**:
  - Thorlabs LSKGG4 Galvo-Galvo Scanner
  - NI USB-6453 DAQ
  - APD or Excelitas SPCM-AQRH-10-FC detector

- **Software**:
  - Python 3.7 or higher
  - Required Python packages:
    - numpy
    - matplotlib
    - nidaqmx
    - pyvisa

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/Single_NV_Scanning_Microscopy.git
cd Single_NV_Scanning_Microscopy
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

1. **Real-time Scanning Mode**:
```bash
python main.py --mode realtime
```
This mode provides live visualization of the scan as it progresses.

2. **Buffered Scanning Mode**:
```bash
python main.py --mode buffered
```
This mode is faster but only shows the final result.

### Configuration

The system can be configured using a JSON configuration file. A template is provided in `config_template.json`. Key configuration options include:

- Scan range and resolution
- Dwell time per point
- Hardware settings (sample rate, settling time)
- Visualization preferences

To use a custom configuration:
```bash
python main.py --config your_config.json
```

### Configuration Options

```json
{
    "scan_range": {
        "x": [-5.0, 5.0],  // X-axis voltage range
        "y": [-5.0, 5.0]   // Y-axis voltage range
    },
    "resolution": {
        "x": 100,          // Number of points in X
        "y": 100           // Number of points in Y
    },
    "dwell_time": 0.01,    // Time per point in seconds
    "scan_mode": "realtime", // or "buffered"
    "hardware": {
        "sample_rate": 1000,
        "samples_per_point": 10,
        "settling_time": 0.001
    },
    "visualization": {
        "colormap": "viridis",
        "update_interval": 50
    }
}
```

## Operation

1. **Starting a Scan**:
   - Choose the scanning mode (realtime or buffered)
   - Configure scan parameters in the config file
   - Run the appropriate command

2. **During Scanning**:
   - Real-time mode: Watch the live visualization update
   - Buffered mode: Wait for the scan to complete
   - Press Ctrl+C to safely stop the scan

3. **After Scanning**:
   - The system will automatically save the scan data
   - The visualization will remain available for analysis

## Safety Features

- Automatic voltage range limiting
- Safe shutdown on interruption
- Position feedback monitoring
- Emergency stop capability

## Troubleshooting

1. **No Signal Detection**:
   - Check detector connections
   - Verify DAQ channel configuration
   - Ensure proper voltage ranges

2. **Scanner Not Responding**:
   - Verify DAQ connections
   - Check voltage ranges
   - Ensure proper initialization

3. **Visualization Issues**:
   - Check matplotlib backend
   - Verify data format
   - Ensure proper configuration

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

[Add your license information here]

