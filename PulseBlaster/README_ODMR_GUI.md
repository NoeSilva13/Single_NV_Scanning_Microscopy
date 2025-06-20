# ODMR Control Center - Qt GUI

A professional graphical interface for controlling continuous wave ODMR (Optically Detected Magnetic Resonance) experiments with NV centers. Built with PyQt5 and designed to match the dark theme visual style of the napari-based scanning microscopy software suite.

![ODMR Control Center](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-blue)
![Python](https://img.shields.io/badge/Python-3.7%2B-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

## 🔬 Features

### Real-Time ODMR Measurements
- **Live Spectrum Plotting**: Real-time visualization of ODMR spectra with dark napari-style theme
- **Parameter Control**: Full control over all timing and frequency parameters
- **Progress Monitoring**: Real-time progress tracking and status updates with terminal-style logging
- **Professional Interface**: Dark theme (#262930) with green accents (#00d4aa) matching napari viewer

### Hardware Integration
- **Swabian Pulse Streamer**: Complete pulse sequence control via IP connection (default: 192.168.0.201)
- **RIGOL DSG836**: Microwave signal generation and frequency sweeping via Ethernet
- **TimeTagger**: Single photon detection and counting
- **Safety Features**: Automatic RF output control and hardware cleanup

### Data Management
- **Parameter Presets**: Save and load measurement configurations
- **Export Options**: Save results in JSON or CSV format
- **Real-Time Logging**: Timestamped status messages and error reporting with green terminal-style text

### Clean Interface Design
- **Only Functional Parameters**: All GUI elements are connected to measurement logic
- **Honest User Interface**: No non-functional placeholder parameters
- **Streamlined Layout**: Organized tabbed interface with logical parameter grouping

## 🛠️ Installation

### Prerequisites

1. **Python 3.7 or higher**
2. **Required Python packages**:
   ```bash
   pip install PyQt5 numpy matplotlib
   ```

3. **Hardware drivers**:
   - Swabian Pulse Streamer drivers and pulsestreamer Python package
   - TimeTagger software package
   - RIGOL DSG836 VISA drivers

### Quick Start

1. **Clone or download** the repository
2. **Navigate** to the PulseBlaster directory:
   ```bash
   cd Single_NV_Scannig_Microscopy/PulseBlaster
   ```
3. **Run the application**:
   ```bash
   python odmr_gui_qt.py
   ```

## 🎛️ User Interface

The application features a clean tabbed interface with two main sections:

### 🔬 ODMR Control Tab
**Main measurement control with all functional parameters organized in logical groups:**

- **Frequency Parameters**
  - Start Frequency (GHz): Beginning of frequency sweep
  - Stop Frequency (GHz): End of frequency sweep  
  - Number of Points: Resolution of frequency sweep

- **Timing Parameters (ns)**
  - Laser Duration: Length of optical pumping pulse
  - MW Duration: Length of microwave pulse
  - Detection Duration: Length of fluorescence detection window

- **Delay Parameters (ns)**
  - Laser Delay: Initial delay before laser pulse
  - MW Delay: Delay before microwave pulse
  - Detection Delay: Delay before detection window

- **Sequence Parameters**
  - Sequence Interval: Time between sequence repetitions
  - Repetitions: Number of sequences per frequency point

- **Microwave Settings**
  - MW Power (dBm): Microwave power level (moved to main tab for easy access)

- **Measurement Control**
  - Start/Stop buttons with safety interlocks
  - Progress bar with percentage completion
  - Real-time status updates

- **File Operations**
  - Save/Load parameter configurations
  - Export measurement results

### ⚙️ Device Settings Tab
**Hardware connection management and system information:**

- **Device Connections**
  - Pulse Streamer IP: Network connection to Pulse Streamer (default: 192.168.0.201)
  - RIGOL DSG836 IP: Network connection to signal generator (default: 192.168.0.222)
  - Connection status indicators (🟢 Connected / 🔴 Disconnected)

- **System Information**
  - Real-time system status display
  - Hardware connection status
  - Software version information
  - Terminal-style status log with green text

- **Connection Tests**
  - Individual device testing functions
  - System refresh capabilities

## 🚀 Getting Started

### 1. Hardware Setup
1. **Connect hardware**:
   - Swabian Pulse Streamer via IP network (default IP: 192.168.0.201)
   - RIGOL DSG836 via Ethernet (default IP: 192.168.0.222)
   - TimeTagger via USB
   - Optical setup with NV sample

2. **Network Configuration**:
   - Ensure Pulse Streamer and RIGOL are on same network as control computer
   - Verify IP addresses are accessible (can ping devices)
   - Configure static IPs if needed for stability

3. **Power on devices** in order:
   - TimeTagger
   - Pulse Streamer
   - RIGOL Signal Generator

### 2. Software Configuration
1. **Launch the application**:
   ```bash
   python odmr_gui_qt.py
   ```

2. **Check device connections** in the Device Settings tab:
   - Verify Pulse Streamer shows "🟢 Connected" 
   - Verify RIGOL shows "🟢 Connected"
   - Update IP addresses if necessary

3. **Configure MW power** in the ODMR Control tab (typically -10 to 0 dBm for NV centers)

### 3. Running Measurements
1. **Stay in ODMR Control tab** (all controls are here)
2. **Set frequency range** (typically 2.8-2.9 GHz for NV centers)
3. **Configure timing parameters**:
   - Laser Duration: 2000 ns (typical)
   - MW Duration: 2000 ns (typical)
   - Detection Duration: 1000 ns (typical)
4. **Set MW power** (typically -10 dBm to start)
5. **Click "🚀 Start ODMR"**
6. **Monitor progress** in real-time plot and terminal-style status log

### 4. Data Analysis
- **Real-time visualization**: Watch ODMR spectrum develop during measurement
- **Save results**: Export data in JSON or CSV format
- **Parameter storage**: Save configurations for reproducible measurements

## 📊 Example ODMR Parameters

### Standard NV Center ODMR
```
Frequency Range: 2.80 - 2.90 GHz
Number of Points: 101
Laser Duration: 2000 ns
MW Duration: 2000 ns
Detection Duration: 1000 ns
Laser Delay: 0 ns
MW Delay: 0 ns
Detection Delay: 0 ns
Sequence Interval: 10000 ns
Repetitions: 100
MW Power: -10 dBm
```

### High-Resolution ODMR
```
Frequency Range: 2.865 - 2.875 GHz
Number of Points: 201
Laser Duration: 2000 ns
MW Duration: 2000 ns
Detection Duration: 1000 ns
Repetitions: 500
MW Power: -5 dBm
```

## 🔧 Troubleshooting

### Connection Issues

**Pulse Streamer not connecting:**
- Check network connection to device
- Verify IP address (default: 192.168.0.201)
- Try pinging the device: `ping 192.168.0.201`
- Check firewall settings
- Verify pulsestreamer Python package is installed

**RIGOL not connecting:**
- Check Ethernet connection
- Verify IP address (default: 192.168.0.222)
- Try pinging the device: `ping 192.168.0.222`
- Check network settings and firewall
- Use "Test RIGOL Signal" button in Device Settings

**TimeTagger issues:**
- Check USB connection
- Verify TimeTagger software is installed
- Check for driver conflicts
- Restart computer if necessary

### Measurement Issues

**No signal detected:**
- Check optical alignment
- Verify sample positioning
- Check laser power
- Verify detection path
- Check TimeTagger connection

**Poor ODMR contrast:**
- Optimize MW power (try -10 to 0 dBm range)
- Check MW delivery to sample
- Verify frequency range includes resonances
- Check for magnetic field drift
- Verify pulse timing parameters

**Measurement interruptions:**
- Check all network connections
- Verify network stability for networked devices
- Check for power supply issues
- Use shorter sequence intervals
- Check status log for error messages

### Software Issues

**Application crashes:**
- Check Python version (3.7+ required)
- Verify all dependencies are installed:
  ```bash
  pip install PyQt5 numpy matplotlib
  ```
- Check system resources (RAM, CPU)
- Restart application

**Plot not updating:**
- Check measurement parameters are valid
- Verify hardware connections in Device Settings tab
- Look for error messages in terminal-style status log
- Try refreshing devices

## 📝 File Formats

### Parameter Files (.json)
```json
{
  "start_freq_ghz": 2.80,
  "stop_freq_ghz": 2.90,
  "num_points": 101,
  "laser_duration": 2000,
  "mw_duration": 2000,
  "detection_duration": 1000,
  "laser_delay": 0,
  "mw_delay": 0,
  "detection_delay": 0,
  "sequence_interval": 10000,
  "repetitions": 100,
  "mw_power_dbm": -10.0
}
```

### Results Files (.json)
```json
{
  "frequencies_hz": [2.8e9, 2.801e9, ...],
  "count_rates_hz": [1250.5, 1248.2, ...],
  "parameters": { ... },
  "timestamp": "2025-01-XX XX:XX:XX"
}
```

### CSV Export
```csv
Frequency_GHz,Count_Rate_Hz
2.800,1250.5
2.801,1248.2
...
```

## 🔒 Safety Features

- **Automatic RF shutdown** on application exit
- **Hardware cleanup** on unexpected closure  
- **Parameter validation** before measurement start
- **Emergency stop** functionality
- **Connection monitoring** with automatic retry
- **Network timeout handling** for device connections

## 🎨 Visual Design

The interface uses a professional dark theme matching the napari scanning software:

### Color Scheme
- **Background**: `#262930` (dark gray)
- **Accent**: `#00d4aa` (cyan-green)
- **Bright Accent**: `#00ff88` (bright green)
- **Text**: `#ffffff` (white)
- **Input Fields**: `#3c3c3c` (dark gray)
- **Plot Background**: Dark with green data visualization
- **Status Log**: Terminal-style with green text on dark background

### Design Philosophy
- **Clean and Honest**: Only functional parameters are shown
- **Professional**: Dark theme with scientific application styling
- **Organized**: Logical grouping of related parameters
- **Consistent**: Matches napari scanning application aesthetic

## 📞 Support

For technical support:
1. Check this README for common solutions
2. Review terminal-style status log for error messages
3. Test individual device connections in Device Settings tab
4. Verify network connectivity to devices
5. Contact NV Lab for hardware-specific issues

## 🔄 Version History

- **v1.0**: Initial Qt implementation with tabbed interface
- **v1.1**: Added dark theme and napari-style visualization  
- **v1.2**: Enhanced device testing and error handling
- **v1.3**: Code quality cleanup - removed non-functional parameters
- **v1.4**: Interface reorganization - moved MW Power to main control tab
- **v1.5**: Updated Pulse Streamer connection to IP-only (USB not supported)

## 📚 Related Documentation

- **ODMR Experiments**: See `odmr_experiments.py` for measurement implementation details
- **Pulse Control**: See `swabian_pulse_streamer.py` for pulse sequence programming
- **Signal Generation**: See `rigol_dsg836.py` for MW source control
- **Main Scanning Software**: See `napari_scanning_SPD_refactored.py` for overall system integration

## 📄 License

This software is part of the NV Lab single NV scanning microscopy suite.
Developed for research use in quantum sensing applications.

---

**NV Lab - Burke Research Group**  
*Professional tools for quantum sensing and NV center research* 