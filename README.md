# Single NV Scanning & ODMR Control Suite

![NV Scanning Microscopy](https://img.shields.io/badge/Microscopy-NV%20Centers-brightgreen)
![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

A Python toolkit developed at the **[Burke Lab](https://www.burkelab.com/)** for high-precision optical, microwave and timing control of single Nitrogen-Vacancy (NV) centers in diamond.
It bundles two graphical applications plus a script-driven ODMR experiment suite that share common infrastructure (data management, calibration constants, reusable Qt/napari widgets):

1. **Confocal Scan GUI** ([confocal_main_control.py](confocal_main_control.py)) - real-time galvo raster scanning, live photon counting, click-to-move positioning, region zoom, auto-focus and single-axis line scans, built on a [napari](https://napari.org/) viewer.
2. **ODMR experiments** ([PulseBlaster/odmr_experiments.py](PulseBlaster/odmr_experiments.py)) - script-driven continuous-wave **ODMR**, **pulsed ODMR**, **Rabi**, **T1**, and **readout transient** measurements with live matplotlib updates and PDF/CSV export.
3. **Spectrometer Control** ([spectrometer_app.py](spectrometer_app.py)) - real-time spectral analysis using a Player One Astronomy (POA) camera in line-scan mode, with wavelength calibration and data recording.

Each entry point can be run independently and only requires the hardware/drivers relevant to it (see [Hardware requirements](#-hardware-requirements)).

---
## ✨ Key capabilities

### Confocal Scan GUI (`confocal_main_control.py`)
- **Multi-dimensional scanning (XY / XZ / YZ / XYZ)** selected via a **Scan Mode** dropdown that drives **New Scan**: 2D modes render an image, XYZ renders a 3D volume in napari, all through one generic N-axis raster engine (`raster_engine.py`). Every axis is calibrated in micrometers (canonical unit) through a shared `DAQAxis` abstraction (`daq_axis.py`); the µm→V conversion happens only at the DAQ boundary.
- Live **XY raster scanning** with per-pixel, hardware-timed photon counting (NI-DAQ sample clock + Swabian TimeTagger `CountBetweenMarkers`).
- **napari**-based viewer (zoom, pan, live contrast auto-scaling, scale bar in µm).
- **Click-to-move** galvo positioning (on the scan image and on the single-axis line-scan plots) and rectangle **ROI zoom** (up to 9 nested zoom levels, with history/undo via "Reset Zoom").
- Integrated **Scan Z** (linear piezo Z sweep) and **single-axis line scans** along X or Y, both hardware-timed with per-point photon counting via the DAQ clock + TimeTagger `CountBetweenMarkers` (shared `scanning_core.py`). Z min/max/resolution/dwell are set in the Scan Parameters panel.
- Multi-backend **live camera preview** (POA / ZWO / USB webcam) and single-shot capture, docked in the viewer.
- Real-time photon-count **strip-chart plot** with overflow indication.
- Manual **X/Y/Z axis control** widget (slider + spinbox per axis) that also tracks the scanner's current position: galvo X/Y via the AO task, piezo Z via DAQ `ao2` → EXT IN. It updates on click-to-move and at the end of every scan.
- Automatic data saving after every scan: `.csv` (metadata header), `.npz` (image + full metadata), `.tiff` (ImageJ/Fiji-compatible with scale calibration) and a `.png` heatmap.
- **Load Scan** widget to reopen previously saved `.npz` scans at the correct physical scale.

### ODMR experiments (`PulseBlaster/odmr_experiments.py`)
- Script-driven measurement loops with interleaved signal/reference **contrast** for common-mode noise rejection:
  - **`odmr_contrast`** - continuous-wave frequency sweep to locate the NV resonance.
  - **`pulsed_odmr_contrast`** - frequency sweep with a fixed MW pulse in the dark (narrower linewidths than CW).
  - **`rabi_oscillation_contrast`** - microwave-duration sweep to calibrate π/2 and π pulses.
  - **`t1_decay_contrast`** - dark-time delay sweep with automatic stretched-exponential fit.
  - **`readout_transient`** - time-resolved readout histogram to choose `detection_delay` / `detection_duration`.
- Optional **live matplotlib plot** (`live_plot=True`) that refreshes after every sweep point; final multi-panel figures are still saved as PDF via `plot_results()`.
- Ethernet control of a **Rigol DSG836** and a **Swabian Pulse Streamer 8/2** (laser/MW/SPD gate timing, 8 ns resolution).
- Automatic CSV saving via `ODMRDataManager` into dated, per-experiment-type folders under [`data/`](data/).
- Edit timing/frequency parameters in `run_example_experiments()` (or call the methods from your own script).

### Spectrometer Control (`spectrometer_app.py`)
- Real-time **spectral analysis** using a POA camera configured in a **6252x480** line-scan mode.
- Adjustable **ROI** (manual spinboxes or an interactive pyqtgraph rectangle) to select the spectral line and vertical averaging window.
- Linear **wavelength calibration** (start/end nm mapped across the sensor width).
- **Dark-frame subtraction** and **reference-frame normalization**.
- Live spectrum plot (pyqtgraph) updated every camera frame (~30 FPS acquisition).
- Time-series **recording** and multi-spectrum **CSV export**.
- Automatic exposure/gain control with GUI/hardware value sync.

### Common infrastructure
- Modular **hardware controller** classes: [galvo_controller.py](galvo_controller.py) (NI-DAQ galvo I/O), [daq_z_controller.py](daq_z_controller.py) (NI-DAQ `ao2` → piezo EXT IN for Z position), [PulseBlaster/swabian_pulse_streamer.py](PulseBlaster/swabian_pulse_streamer.py) and [PulseBlaster/rigol_dsg836.py](PulseBlaster/rigol_dsg836.py).
- [data_manager.py](data_manager.py) / [odmr_data_manager.py](odmr_data_manager.py) - automatic, date-stamped CSV folder hierarchies for confocal scans and ODMR-family experiments respectively.
- [utils.py](utils.py) - centralized calibration constants and TIFF metadata export shared by the confocal app.
- Reusable **napari/magicgui widgets** ([widgets/](widgets/)) and **matplotlib plot widgets** ([plot_widgets/](plot_widgets/)) shared across applications.
- Tested on Python 3.8-3.12, Windows 10/11.

---
## 🖥️ Hardware requirements

Mandatory for confocal scans (`confocal_main_control.py`)
- Thorlabs **LSKGG4** galvo-galvo scanner
- NI **USB-6453** DAQ (static + hardware-timed AO for galvos, sample clock export)
- **Single-photon detector** (e.g. Excelitas SPCM-AQRH-10-FC)
- **Swabian TimeTagger** (real, network, or virtual/replay fallback)
- Optional: Thorlabs **piezo Z-stage** (initialized in closed loop by Thorlabs software; position commanded via DAQ `ao2` → EXT IN) for Scan Z; POA/ZWO/USB camera for live preview

Additional for ODMR / advanced timing (`PulseBlaster/odmr_experiments.py`)
- **Swabian Pulse Streamer 8/2** (default IP `192.168.0.203`)
- **Rigol DSG836** microwave source, Ethernet/VISA (default IP `192.168.0.223`)
- **Acousto-Optic Modulator** (AOM) for laser gating
- **Swabian TimeTagger** (real, network, or virtual/replay fallback)

Additional for Spectrometer (`spectrometer_app.py`)
- **POA camera** (Player One Astronomy) with USB3 connection, run in a 6252x480 line-scan configuration
- Spectrometer setup with horizontal line output (e.g., transmission grating)

All instruments communicate via USB/Ethernet and require vendor drivers (see below).

---
## ⚙️ Installation
```bash
# 1. Clone the repository
$ git clone https://github.com/NoeSilva13/Single_NV_Scannig_Microscopy.git
$ cd Single_NV_Scannig_Microscopy

# 2. Create a fresh environment (conda or venv)
$ python -m venv venv
$ source venv/Scripts/activate   # Windows (Git Bash) - use venv\Scripts\activate.ps1 in PowerShell

# 3. Install Python dependencies
$ pip install -r requirements.txt

# 4. Install vendor drivers/SDKs (not distributed on PyPI)
- NI-DAQmx (USB-6453)                 https://www.ni.com/en/support/downloads/drivers/download.ni-daqmx.html
- Swabian TimeTagger SDK              https://www.swabianinstruments.com/time-tagger/downloads/
- Swabian Pulse Streamer package      pip install pulsestreamer (already in requirements.txt)
- Rigol DSG836 (Ethernet/VISA)        Requires a VISA runtime (e.g. NI-VISA or Keysight IO Libraries); no vendor driver otherwise
- Player One Astronomy (POA) SDK      https://player-one-astronomy.com/service/software/
- ZWO ASI Camera SDK (optional)       https://astronomy-imaging-camera.com/software-drivers
```

---
## 🚀 Quick start

### 1. Confocal scanning
```bash
python confocal_main_control.py
```
Actions inside the napari window:
- "🔬 New Scan" ⇒ run full raster scan at the current parameters.
- **Drag a rectangle** on the image ⇒ zoom into that region (up to 9 nested levels).
- "🔄 Reset Zoom" ⇒ return to the original field of view.
- "🎯 Set to Zero" ⇒ return galvos to (0, 0) µm.
- "🛑 Stop Scan" ⇒ abort a running scan safely.
- "Scan Parameters" dock ⇒ adjust XY range / resolution / dwell and Z min/max/resolution/dwell on-the-fly.
- "Camera Control" dock ⇒ switch between POA/ZWO/USB cameras, live view and single-shot capture.
- "Single Axis Scan" dock ⇒ 1D line scans along X, Y, or Z (tabs) at the current position; left-click a point on an X/Y plot to move there.
- "Axis Control" dock ⇒ manual X/Y/Z positioning (slider + spinbox) that mirrors the scanner's current position.

### 2. ODMR (CW, pulsed, Rabi, T1, readout transient)
```bash
python PulseBlaster/odmr_experiments.py
```
Edit the active call inside `run_example_experiments()` (timing, frequencies, repetitions, `live_plot=True`). The sweep updates a live contrast plot after each point, then `plot_results(...)` saves the final PDFs. Data CSVs land under `data/mmddyy/<ExperimentType>/`. See [PulseBlaster/README.md](PulseBlaster/README.md) for API details.

### 3. Spectrometer Control
```bash
python spectrometer_app.py
```
Basic operation:
- Connect the camera and start live imaging.
- Adjust the ROI (manually or via the visual selector) to capture the spectral line.
- Configure exposure and gain settings.
- Capture dark/reference frames if needed, then apply wavelength calibration (a recent preset is in [`Camera/072926SpectrometerCal02OK.json`](Camera/072926SpectrometerCal02OK.json)).
- Record and export spectral data to CSV.

---
## ⚖️ Calibration Parameters

The confocal system's calibration parameters and constants are centrally defined in [utils.py](utils.py):

### Microscope Calibration
- `MICRONS_PER_VOLT = 24` - Galvo scanner calibration (µm/V); empirically re-measured per objective (comments in the file list values for other objectives, e.g. 130 for a 40x air objective, 51 for an oil objective).
- `MAX_ZOOM_LEVEL = 9` - Maximum allowed nested zoom levels in the scanning interface.

### Z Scan Parameters
Z Min (µm), Z Max (µm), Z Resolution (points), and Z Dwell Time (ms) are edited in the Scan Parameters dock. Defaults are 0–450 µm, 50 points, and 5 ms (increase for larger Z steps, as the piezo settles slower than the galvos). The Scan Z tab reads these via `scan_params_manager` and runs a single linear hardware-timed sweep.

### Z Piezo Analog Control (DAQ `ao2` → EXT IN)
- `Z_UM_PER_VOLT = 45.0` - Closed-loop calibration (µm/V); 0–10 V maps to 0–450 µm
- `Z_MAX_TRAVEL_UM = 450.0` - Full travel of the piezo stage (µm)
- `Z_VOLTAGE_RANGE = (0.0, 10.0)` - Allowed EXT IN voltage range in closed loop

The piezo controller is initialized and kept in closed loop by external Thorlabs software; this app only commands position through the DAQ analog output wired to EXT IN.

### Timing Parameters
- `BINWIDTH = int(5e9)` - Default binwidth for the TimeTagger live-count strip chart (picoseconds; 5e9 = 5 milliseconds)

To modify these parameters:
1. Open [utils.py](utils.py).
2. Update the desired constant value (re-measure `MICRONS_PER_VOLT` whenever the objective or optical path changes).
3. Restart the application for changes to take effect.

**ODMR / Pulse Streamer defaults** live in [PulseBlaster/swabian_pulse_streamer.py](PulseBlaster/swabian_pulse_streamer.py) (`default_params`, 8 ns timing resolution) and can also be overridden per-measurement when calling methods on `ODMRExperiments`.

---
## 📂 Data layout

All experiment outputs are written under [`data/`](data/) (override with env var `NV_EXPERIMENT_DATA`). The folder is gitignored so you can delete dated subfolders anytime without affecting the code.

Confocal scans (via [data_manager.py](data_manager.py)), in a daily `mmddyy` folder with a shared, collision-free sequence number `mmddyy###`:
```
data/072226/
 └─ 072226001.csv     # photon counts + metadata header (2D modes: XY / XZ / YZ)
 └─ 072226001.npz     # image/volume + per-axis µm metadata (all modes, incl. XYZ)
 └─ 072226001.tiff    # ImageJ/Fiji-compatible, scale-calibrated (2D modes)
 └─ 072226001.png     # auto-saved heatmap figure (2D modes)
```
3D (XYZ) scans write only the `.npz` (image/volume + metadata); 2D modes (XY/XZ/YZ) additionally write `.csv`, `.tiff`, and `.png`.

ODMR-family experiments (via [odmr_data_manager.py](odmr_data_manager.py)), one dated subfolder per experiment type:
```
data/072226/
 └─ ODMR_Contrast/
     └─ 072226001_ODMR_Contrast.csv
 └─ Rabi_Contrast/
     └─ 072226001_Rabi_Contrast.csv
 └─ T1_Contrast/
     └─ 072226001_T1_Contrast.csv
```

Each measurement is automatically placed in a date folder by the corresponding `DataManager` class. You can delete old `data/mmddyy/` folders anytime to free disk space; they are not tracked by git.

---
## 🏗️ Repository overview

```
Single_NV_Scannig_Microscopy/
├─ confocal_main_control.py     # Entry point: napari GUI for confocal galvo scanning
├─ spectrometer_app.py           # Entry point: Qt (PySide6/qtpy) GUI for POA-camera spectrometer
├─ data/                         # Experiment outputs (mmddyy/...); gitignored, clean manually
│
├─ data_manager.py               # DataManager: saves confocal scan CSVs with metadata
├─ odmr_data_manager.py          # ODMRDataManager: saves ODMR/Rabi/T1 CSVs per experiment type
├─ galvo_controller.py           # GalvoScannerController: NI-DAQ channel setup & voltage I/O
├─ daq_axis.py                   # DAQAxis: per-axis µm↔V calibration, channel, travel/voltage limits
├─ daq_z_controller.py           # DAQZController: DAQAxis subclass for the piezo (NI-DAQ ao2 → EXT IN)
├─ scanning_core.py              # Shared hardware-timed AO + CountBetweenMarkers sweep primitive
├─ raster_engine.py              # Generic N-axis raster (µm): waveform build, run, 2D/3D reconstruct
├─ plot_scan_results.py          # Thread-safe PNG heatmap export after each confocal scan
├─ thread_safe_bridge.py         # GUIBridge: marshal background-thread updates onto the Qt/napari main thread
├─ utils.py                      # Calibration constants, experiment_data_root(), TIFF export
│
├─ widgets/                      # Re-usable magicgui/Qt (qtpy) widgets for the confocal napari GUI
│   ├─ scan_controls.py          #   New Scan / Stop / Reset Zoom / Scan Parameters panel
│   ├─ camera_controls.py        #   Multi-backend (POA/ZWO/USB) live view + single shot
│   ├─ auto_focus.py             #   Scan Z tab: linear Z sweep + pyqtgraph plot
│   ├─ single_axis_scan.py       #   1D X/Y/Z line-scan widget (pyqtgraph tabs)
│   ├─ file_operations.py        #   Load a saved .npz scan back into napari
│   └─ axis_controls.py          #   Manual X/Y/Z position widget (galvo + DAQZController)
│
├─ plot_widgets/                 # Plot widgets shared across apps
│   └─ live_plot_napari_widget.py#   pyqtgraph live count-rate plot with controls (napari dock)
│
├─ PulseBlaster/                 # Pulse Streamer & Rigol drivers + experiment logic
│   ├─ swabian_pulse_streamer.py #   SwabianPulseController: pulse sequence generation (ODMR/Rabi/T1)
│   ├─ rigol_dsg836.py           #   RigolDSG836Controller: SCPI/VISA microwave source control
│   └─ odmr_experiments.py       #   ODMRExperiments: measurement loops, TimeTagger acquisition, plotting
│
├─ Camera/                       # Camera backends (used by confocal & spectrometer apps)
│   ├─ camera_video_mode.py      #   POACameraController
│   ├─ pyPOACamera.py            #   Low-level POA SDK ctypes bindings
│   ├─ zwo_camera.py / zwo_camera_controller.py  # ZWO ASI camera backend
│   ├─ usb_webcam_controller.py  #   Generic OpenCV USB webcam backend
│   └─ 072926SpectrometerCal02OK.json  # Latest spectrometer wavelength/ROI calibration
│
├─ TimeTagger/                   # TimeTagger helpers and virtual-device replay data
│   ├─ time_tags_test.ttbin      #   Recorded photon-tag stream used as a virtual TimeTagger fallback
│   └─ CountRateLive.py          #   Standalone live count-rate widget (standalone detector health check)
│
├─ requirements.txt              # Python dependencies (see file for vendor SDK notes)
└─ CHANGELOG.md
```

### Architecture at a glance

```mermaid
flowchart TD
    subgraph confocalApp [confocal_main_control.py]
        DataManager
        GalvoController[galvo_controller]
        DAQZController[daq_z_controller]
        PlotScanResults[plot_scan_results]
        ThreadSafeBridge[thread_safe_bridge]
        Utils[utils]
        Widgets["widgets/*"]
        LivePlot["plot_widgets.live_plot_napari_widget"]
    end

    subgraph odmrApp [PulseBlaster/odmr_experiments.py]
        ODMRDataManager[odmr_data_manager]
        PulseStreamer["PulseBlaster.swabian_pulse_streamer"]
        Rigol["PulseBlaster.rigol_dsg836"]
        Experiments["ODMRExperiments"]
    end

    subgraph spectrometerApp [spectrometer_app.py]
        POACamera["Camera.camera_video_mode"]
    end

    Widgets --> DAQZController
    Widgets --> Camera["Camera/* backends"]
    Experiments --> ODMRDataManager
    Experiments --> TimeTagger
    confocalApp --> TimeTagger
    DataManager --> DataDir["data/"]
    ODMRDataManager --> DataDir
```

---
## 📑 Citation
If you use this software in academic work, please cite our forthcoming instrumentation paper or acknowledge the **Burke Lab, University of California, Irvine**.

---
## 🧑‍💻 Contributing
Pull requests are welcome! Open an issue to discuss new features, hardware support or bug-fixes.

---
## 📄 License
This project is licensed under the MIT License - see `LICENSE` for details.

---
### Contact
For questions and support:
- Contact: **Javier Noé Ramos Silva** - *jramossi@uci.edu*
- Lab [Burke Lab](https://www.burkelab.com/) - Department of Electrical Engineering and Computer Science, University of California, Irvine
