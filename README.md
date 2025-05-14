# Single NV Scanning Microscopy

![NV Scanning Microscopy](https://img.shields.io/badge/Microscopy-NV%20Centers-brightgreen)
![Python](https://img.shields.io/badge/python-3.7+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

A Python-based control system for Single Nitrogen-Vacancy (NV) Scanning Microscopy, featuring integration with Thorlabs LSKGG4 Galvo-Galvo Scanner, NI USB-6453 DAQ, and Swabian TimeTagger for high-precision photon counting.

## 🔍 Key Features

- **High-Precision Scanning**:
  - Two-dimensional sample imaging with nanoscale precision
  - Real-time and buffered scanning modes
  - Configurable scan parameters and hardware settings
  
- **Advanced Detection**:
  - Dual detector support (APD and SPCM)
  - Swabian TimeTagger integration for precise photon counting
  - High temporal resolution measurements
  
- **Interactive Visualization**:
  - Real-time image display with Napari viewer
  - Live scan preview and zooming capabilities
  - Interactive region selection and scanning
  - Multiple visualization modes (2D plot, histogram)

## 💻 System Requirements

### Hardware
- Thorlabs LSKGG4 Galvo-Galvo Scanner
- National Instruments USB-6453 DAQ device
- One of the supported detectors:
  - Avalanche Photodiode (APD)
  - Excelitas SPCM-AQRH-10-FC Single Photon Counting Module
- Swabian TimeTagger device
- Computer with USB 3.0+ ports

### Software
- Python 3.7 or higher
- Operating System: Windows 10/11
- Dependencies:
  ```
  numpy>=1.20.0
  matplotlib>=3.4.0
  nidaqmx>=0.6.0
  pyvisa>=1.11.0
  napari>=0.4.17
  magicgui>=0.3.0
  TimeTagger>=0.9.0
  ```

## 📦 Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/NoeSilva13/Single_NV_Scannig_Microscopy.git
   cd Single_NV_Scannig_Microscopy
   ```

2. **Create and Activate Virtual Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Hardware Drivers**
   - [NI-DAQmx](https://www.ni.com/en/support/downloads/drivers/download.ni-daqmx.html)
   - [Swabian TimeTagger Software](https://www.swabianinstruments.com/time-tagger/downloads/)

## 🚀 Usage

### Napari-based Interface

1. **Launch the Napari Interface**
   ```bash
   python napari_scanning.py  # For APD-based scanning
   # or
   python napari_scanning_SPD_TT.py  # For TimeTagger-based scanning
   ```

2. **Interface Features**:
   - 🔄 Reset Zoom: Return to original view
   - 📷 New Scan: Start a new scanning sequence
   - 💾 Save Image: Save the current scan
   - 🎯 Set to Zero: Reset scanner position

### Command-Line Interface

1. **Real-time Scanning Mode**
   ```bash
   python main.py --mode realtime
   ```

2. **Buffered Scanning Mode**
   ```bash
   python main.py --mode buffered
   ```

### Jupyter Notebook Interface
Use `microscope_control.ipynb` for interactive control and visualization:
- Real-time photon counting
- Live scan visualization
- Parameter adjustment
- Data analysis

## ⚙️ Configuration

### Configuration File (config_template.json)
```json
{
    "scan_range": {
        "x": [-5.0, 5.0],
        "y": [-5.0, 5.0]
    },
    "resolution": {
        "x": 100,
        "y": 100
    },
    "dwell_time": 0.01,
    "scan_mode": "realtime",
    "hardware": {
        "sample_rate": 1000,
        "samples_per_point": 10,
        "settling_time": 0.001
    }
}
```

### Advanced Settings
- **Scan Resolution**: 16x16 to 512x512 pixels
- **Dwell Time**: 0.1ms to 1000ms per point
- **Voltage Range**: ±10V maximum
- **TimeTagger Settings**: 
  - Channel 1: SPD input
  - Adjustable sampling time
  - Configurable binning

## 📊 Data Management

### Data Structure
- Raw scan data: `.npy` files
- Processed images: `.png`, `.tiff`
- Metadata: `.json`
- Daily folders: `MMDDYY/scan_data_HHMMSS.csv`

### Data Analysis Features
- Real-time count rate monitoring
- 2D scan visualization
- Region-of-interest selection
- Time trace analysis

## 🔧 Troubleshooting

1. **No Signal Detection**
   - Check detector power and connections
   - Verify DAQ/TimeTagger channel configuration
   - Ensure proper voltage ranges

2. **Scanner Issues**
   - Check USB connections
   - Verify DAQ device in NI MAX
   - Check voltage limits (±10V)

3. **TimeTagger Problems**
   - Verify USB connection
   - Check channel assignments
   - Update TimeTagger software

## 📚 References

- [NV Center Physics Documentation](https://quantum-diamond.physics.org)
- [Thorlabs LSKGG4 Manual](https://www.thorlabs.com)
- [NI USB-6453 Specifications](https://www.ni.com)
- [Swabian TimeTagger Documentation](https://www.swabianinstruments.com/time-tagger/)
- [Napari Documentation](https://napari.org/stable/)

## 📧 Contact

For questions and support:
- **Email**: jramossi@uci.edu
- **Lab Website**: [[lab-website-url](https://www.burkelab.com/)]

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---
*Last updated: May 2025*
