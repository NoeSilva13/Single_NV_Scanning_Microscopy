# Single NV Scanning & ODMR Control Suite

![NV Scanning Microscopy](https://img.shields.io/badge/Microscopy-NV%20Centers-brightgreen)
![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

A Python toolkit developed at the **[Burke Lab](https://www.burkelab.com/)** for high-precision optical, microwave and timing control of single Nitrogen–Vacancy (NV) centers in diamond.  
It bundles two flagship graphical applications:

1. **Confocal Scan GUI** (`confocal_main_control.py`) – real-time raster scanning, live photon counting and auto-focus based on a Napari viewer.
2. **ODMR Control Center** (`odmr_gui_qt.py`) – a professional Qt interface for continuous-wave ODMR, Rabi and related pulse-sequence measurements.

Both programs share a common codebase and are designed to run out-of-the-box with our standard NV microscope (Thorlabs galvos, NI-DAQ, Swabian Time-Tagger, PulseStreamer, Rigol MW source and single-photon detectors).

---
## ✨ Key capabilities

### Confocal Scan GUI
- Live **XY raster scanning** with dwell-time control.
- **Napari** based viewer (zoom, pan, 2-D colormaps, profile plots).
- **Click-to-move** galvo positioning and ROI (**rectangle zoom**) with history.
- Integrated **auto-focus** routine and **single-axis line scans**.
- Real-time photon-count **histogram panel** driven by a Swabian TimeTagger.
- Automatic data saving (`.csv` + `.npz` + `.tiff`) and figure export after every scan.

### ODMR Control Center
- **Continuous-wave ODMR sweeps** with live spectral plot.
- **Rabi oscillations**, and customizable pulse sequences (via Swabian PulseStreamer 8/2).
- Ethernet control of **Rigol DSG836** microwave generator (frequency / power / sweeps).
- Progress bars, rich logging console and device-status widgets.
- Save/Load parameter presets (pulse sequence) and measurement results (`.json`, `.csv`).

### Common infrastructure
- Modular **hardware controller** classes (`galvo_controller.py`, `swabian_pulse_streamer.py`, etc.).
- `config_template.json` for centralised scan parameters.
- **DataManager** for automatic date-stamped folder hierarchies.
- Tested on Python 3.8–3.12, Windows 10/11.

---
## 🖥️ Hardware requirements

Mandatory for confocal scans
- Thorlabs **LSKGG4** galvo-galvo scanner
- NI **USB-6453** (static AO for galvos)
- **Single-photon detector** (Excelitas SPCM-AQRH-10-FC)

Additional for ODMR / advanced timing
- **Swabian TimeTagger** 
- **Swabian Pulse Streamer 8/2**
- **Rigol DSG836** microwave source
- **Acousto-Optic Modulator** (laser gating)

All instruments communicate via USB/Ethernet and require vendor drivers (see below).

---
## ⚙️ Installation
```bash
# 1. Clone the repository
$ git clone https://github.com/NoeSilva13/Single_NV_Scannig_Microscopy.git
$ cd Single_NV_Scannig_Microscopy

# 2. Create a fresh environment (conda or venv)
$ python -m venv venv
$ source venv/Scripts/activate   # Windows

# 3. Install Python dependencies
$ pip install -r requirements.txt

# 4. Install vendor drivers
- NI-DAQmx  (USB-6453)          https://www.ni.com/en/support/downloads/drivers/download.ni-daqmx.html
- Swabian **TimeTagger** SDK    https://www.swabianinstruments.com/time-tagger/downloads/
- Swabian **Pulse Streamer**    https://www.swabianinstruments.com/pulse-streamer/downloads/
- Rigol **DSG836** Ethernet SCPI interface (no driver)  
```

---
## 🚀 Quick start

### 1. Confocal scanning
```bash
python confocal_main_control.py
```
Actions inside the Napari window:
- "🔄 New Scan" ⇒ run full raster scan.
- **Drag rectangle** ⇒ zoom into ROI (up to 3 levels).
- "🎯 Set to Zero" ⇒ return galvos to (0,0) V.
- "⚙️ Scan Parameters" dock ⇒ adjust range / resolution on-the-fly.

### 2. ODMR (continuous wave or Rabi)
```bash
python odmr_gui_qt.py
```
Select the **ODMR** or **Rabi** tab, fill in microwave / laser timing, hit **Start**.  Real-time plots update during acquisition, and raw data can be exported afterwards.

---
## ⚖️ Calibration Parameters

The system's calibration parameters and constants are centrally defined in `utils.py`:

### Microscope Calibration
- `MICRONS_PER_VOLT = 86` - Galvo scanner calibration (µm/V)
- `MAX_ZOOM_LEVEL = 6` - Maximum allowed zoom levels in the scanning interface

### Auto-Focus Parameters
- `PIEZO_COARSE_STEP = 5.0` - Step size for coarse focus scan (µm)
- `PIEZO_FINE_STEP = 0.5` - Step size for fine focus scan (µm)
- `PIEZO_FINE_RANGE = 10.0` - Range around peak for fine scan (µm)

### Timing Parameters
- `BINWIDTH = int(5e9)` - Default binwidth for TimeTagger counter (picoseconds, 5e9 = 5 milliseconds)

To modify these parameters:
1. Open `utils.py`
2. Update the desired constant value
3. Restart the application for changes to take effect

---
## 📂 Data layout
```
YYYYMMDD/
 ├─ scans/
 │   ├─ scan_120530.csv            # photon counts
 │   ├─ scan_120530.npz            # image + metadata
 │   └─ scan_120530.png            # auto-saved figure
 └─ odmr/
     ├─ odmr_134501.csv
     └─ odmr_134501.json           # parameter snapshot
```
Each measurement is automatically placed in a date folder using `DataManager`.

---
## 🏗️ Repository overview
```
Single_NV_Scannig_Microscopy/
 ├─ confocal_main_control.py   # Napari GUI (confocal scans)
 ├─ odmr_gui_qt.py             # Qt GUI (ODMR & Rabi)
 ├─ widgets/                   # Re-usable MagicGUI widgets
 ├─ PulseBlaster/              # PulseStreamer & Rigol drivers + experiments
 ├─ Camera/                    # ZWO & PlayerOne camera wrappers (optional)
 ├─ TimeTagger/                # Example ttbin files & helpers
 ├─ plot_widgets/              # Matplotlib helpers for Napari
 └─ utils.py                   # calibration & shared helper functions
```

---
## 📑 Citation
If you use this software in academic work, please cite our forthcoming instrumentation paper or acknowledge the **Burke Lab, University of California, Irvine**.

---
## 🧑‍💻 Contributing
Pull requests are welcome!  Open an issue to discuss new features, hardware support or bug-fixes.

---
## 📄 License
This project is licensed under the MIT License – see `LICENSE` for details.

---
### Contact
For questions and support:
- Contact: **Javier Noé Ramos Silva** ‑ *jramossi@uci.edu*  
- Lab [Burke Lab](https://www.burkelab.com/) – Department of Electrical Engineering and Computer Science, University of California, Irvine
