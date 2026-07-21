# Changelog

All notable changes to this project will be documented in this file following [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) guidelines.

## [Unreleased] - 2026-07-21
### Added
- **Multi-dimensional scanning (XY / XZ / YZ / XYZ)** via a **Scan Mode** selector in the Scan Parameters panel that drives the **New Scan** button. XZ/YZ produce a 2D image in a dedicated napari layer; XYZ produces a 3D volume layer with per-axis `scale`/`units`. Axes not part of the selected mode are held at their current position (galvo held via the persistent AO task, piezo pre-moved and settled).
- Generic N-axis raster engine `raster_engine.py` (`build_raster_waveforms`, `raster_geometry`, `reconstruct`, `run_raster`): composes the fast..slow µm waveform (with inter-line flyback that also covers slow-axis settling), converts each axis to volts via its `DAQAxis`, drives `scanning_core.run_hardware_timed_sweep`, and reconstructs a 2D image or 3D volume. The XY raster now delegates to this engine.
- Axis abstraction `daq_axis.py` (`DAQAxis`): single home for the µm↔V calibration, AO channel, and travel/voltage limits. `DAQZController` is now a thin `DAQAxis` subclass; `axis_x`/`axis_y` (galvo) and `axis_z` (piezo) are instantiated in the app.

### Changed
- **µm is now the canonical unit for all axes.** Scan Parameters store/return X/Y in micrometers (no hidden volt round-trip); the µm→V conversion happens only at the DAQ boundary (waveform build / analog writes). `on_mouse_click`, single-axis scans, zoom, `ScanPointsManager`, and scale calculation all work in µm. Scale is now `um_scale(a_um, b_um, n_px)` instead of the volt-based `calculate_scale`.
- Configurable piezo settling: when Z is a stepping (slow) axis, the flyback window between lines is widened to cover the user-set **Z Dwell Time** instead of a hardcoded 25 ms, so short Z steps can run faster.
- N-D saving: `.npz` now records `scan_mode`, per-axis µm ranges/points/resolution/scale, `microns_per_volt`, `z_um_per_volt`, `units='um'`, and `format_version`; 2D modes still write CSV/TIFF/PNG. The loader detects 2D vs 3D (adds a 3D volume layer for 3D files) and remains backward compatible with old volt-based files (scale is always µm/px, so they visualize unchanged; Apply converts old volt ranges to µm using the saved/current calibration).
- The piezo Z is set to zero on program close (unchanged) and the galvo returns to zero after every scan.
- Removed the **"Apply Changes"** button from Scan Parameters; **New Scan** now rebuilds XY points from the live spinboxes at start time (dwell / Z / single-axis already read `get_params()` live).
- Moved Z scan parameters (Z Min / Z Max / Z Resolution / Z Dwell Time) into the Scan Parameters panel; the Scan Z tab now runs a single linear hardware-timed Z sweep from those values (via `run_z_sweep`) and no longer auto-moves the piezo to the peak. Removed the dwell/coarse/fine/range spinboxes from `AutoFocusWidget`.
- Rewrote the live signal plot (`plot_widgets/live_plot_napari_widget.py`) on `pyqtgraph` with a ring buffer and added lightweight controls (pause/resume, clear, refresh rate, window length, auto-Y, log-Y); the widget width is constrained to the controls row.
- Added a **"bin (ms)"** control to the live signal plot so the user can change the Time Tagger counter integration window at runtime (via a `binwidth_callback` that rebuilds the `Counter`); this binwidth now affects only the live plot.
- Migrated the auto-focus and single-axis scans to hardware-timed DAQ sweeps counted by `CountBetweenMarkers` (DAQ clock defines the bins), matching the 2D raster scan. Both previously used the free-running `Counter`/`binwidth`, which was incorrect since both move the DAQ and the DAQ clock is routed to the Time Tagger.
- Gave the auto-focus widget its own **"Dwell (ms)"** control (default 25 ms), independent of the scan `dwell_time`, since the piezo objective settles far slower than the galvos (~25 ms for a 1-100 µm step per the datasheet).
- Consolidated auto-focus into a single self-contained `AutoFocusWidget` (pyqtgraph): the dwell field, editable sweep parameters (coarse step / fine step / fine range), "Auto Focus" button, and coarse/fine result plot now live in one dock, and the sweep plots each point in real time as it is acquired (no progress bar). Replaced the previous `magicgui` button + separate matplotlib `SingleAxisPlot` dock and the `SignalBridge` (the widget now uses its own internal Qt signals for thread-safe updates).
- Refactored `SingleAxisScanWidget` (`widgets/single_axis_scan.py`) onto `pyqtgraph` with a `QTabWidget`: the X and Y scans now live in separate tabs, each with its own scan button and plot (with a red peak marker), replacing the previous shared matplotlib `SingleAxisPlot`.
- Integrated the auto-focus panel as a third **"Z Axis"** tab inside the single-axis widget (via `SingleAxisScanWidget.add_z_tab`) instead of a separate dock, and renamed its button from "Auto Focus" to **"Scan Z"** so X/Y/Z line scans share one dock.
- Extracted the shared AO + `CountBetweenMarkers` primitive into `scanning_core.py` (`run_hardware_timed_sweep`, `counts_to_rate`); the 2D raster scan, auto-focus, and single-axis scan now all use it and share the same `scan_lock`/`scan_in_progress` mutual exclusion and Stop-button integration.
- The free-running `Counter`/`binwidth` in `confocal_main_control.py` now feeds only the live signal plot.
- Migrated the whole GUI stack from PyQt5 to PySide6 (Qt6) through the `qtpy` abstraction layer: all `PyQt5.*` imports now go through `qtpy.*`, so the binding can be swapped without touching source.
- Applied Qt6 compatibility fixes: `QDesktopWidget().screenGeometry()` replaced with `QGuiApplication.primaryScreen().availableGeometry()`; `.exec_()` → `.exec()`; enums fully qualified (`Qt.AlignmentFlag`, `Qt.Orientation`, `QMessageBox.StandardButton`/`Icon`, `QFileDialog.FileMode`).
- Replaced Thorlabs Kinesis USB Z control with DAQ analog output (`Dev1/ao2` → piezo EXT IN) via new `daq_z_controller.py` (`DAQZController`).
- Moved the auto-focus Z-sweep algorithm into `widgets/auto_focus.py` (`run_focus_sweep`); the Z controller is now a minimal voltage/position mapper.
- Simplified `widgets/piezo_controls.py` for commanded-position display (no USB connection / no analog readback).

### Removed
- Removed the coarse/fine auto-focus algorithm (`run_focus_sweep`) and the module-level `DEFAULT_COARSE_STEP` / `DEFAULT_FINE_STEP` / `DEFAULT_FINE_RANGE` from `widgets/auto_focus.py`; Z scanning is now a single linear sweep driven by Scan Parameters (`z_scan`).
- Removed `PIEZO_COARSE_STEP`, `PIEZO_FINE_STEP`, and `PIEZO_FINE_RANGE` from `utils.py` (superseded by editable Z scan parameters in the Scan Parameters panel).
- Removed the PyQt5 dependency: `requirements.txt` now pins `PySide6>=6.6.0` and the `napari[pyside6]` extra (set `QT_API=pyside6`).
- Cleaned up unused Qt imports in `odmr_gui_qt.py` (`QFrame`, `QSpacerItem`, `QSizePolicy`, `QFont`, `QPalette`, `QColor`) and `spectrometer_app.py` (`QPixmap`, `QImage`, `QFont`).
- Deleted `piezo_controller.py` (Thorlabs Kinesis `.NET`/USB path); no longer imported by the confocal app.
- Dropped `pythonnet` and the Thorlabs Kinesis SDK install step from `requirements.txt` / README (piezo is initialized externally; this app only writes EXT IN voltage).

### Documentation
- Updated `README.md`, `widgets/README.md`, and architecture diagram for `daq_z_controller.py` and Z calibration constants (`Z_UM_PER_VOLT`, `Z_MAX_TRAVEL_UM`, `Z_VOLTAGE_RANGE`).
- Overhauled `README.md`: corrected calibration constants (`MICRONS_PER_VOLT = 24`, `MAX_ZOOM_LEVEL = 9`), default device IPs (Pulse Streamer `192.168.0.203`, RIGOL `192.168.0.223`), and spectrometer camera resolution (`6252x480`, not `1920x1080`).
- Documented the T1 relaxation measurement tab in `odmr_gui_qt.py`, previously missing from all documentation (ODMR/Rabi were documented, T1 was not).
- Expanded the repository overview with every supporting module (`data_manager.py`, `odmr_data_manager.py`, `galvo_controller.py`, `daq_z_controller.py`, `plot_scan_results.py`, `thread_safe_bridge.py`, `plot_widgets/`, `widgets/`) and added an architecture diagram.
- Rewrote `requirements.txt` to include all actual runtime dependencies (`napari`, `nidaqmx`, `pandas`, `tifffile`, `magicgui`, `qtpy`, `pyvisa`, `scipy`) with vendor-SDK installation notes.
- Corrected `PulseBlaster/README.md` and `PulseBlaster/README_ODMR_GUI.md`: fixed stale run instructions and example code referencing non-existent methods (`create_simple_laser_pulse`, `create_odmr_sequence`, `experiments.odmr()`), updated default IPs, documented the Rabi/T1 tabs, and clarified that Ramsey/spin-echo are not implemented.
- Corrected `widgets/README.md`: replaced references to the retired `napari_scanning_SPD.py` / `ConfigManager` with the current `confocal_main_control.py` entry point and real `ScanParametersManager` / `ScanPointsManager` / `ZoomLevelManager` classes; fixed widget factory signatures and documented `stop_scan`, `update_scan_parameters_widget`, and `create_camera_control_widget`.
- Corrected `README_Spectrometer.md` resolution and image-format claims to match `spectrometer_app.py`.

### Removed
- Deleted unreferenced duplicate `TimeTagger/time_tags_test.1.ttbin` (the non-suffixed `time_tags_test.ttbin` is the one actually used as the virtual TimeTagger fallback).
- Deleted four leftover auto-exported `pulse_sequence_diagrams/Untitled diagram _ Mermaid Chart-*.{svg,mmd}` files not referenced by any documentation or code.
- Deleted `Camera/POA_Camera_Test.py` — vendor SDK walkthrough with a broken import path (`import pyPOACamera` instead of `from Camera import pyPOACamera`), fully superseded by `Camera/camera_video_mode.py`.
- Deleted `Camera/Video_Class_Test` — extensionless one-time integration test with a broken import path, superseded by production camera wrappers.
- Deleted `TimeTagger/FileWriterTT.py` — the `.ttbin` replay file it originally generated (`time_tags_test.ttbin`) already exists in the repo and serves as the virtual TimeTagger fallback; the recording script itself is no longer needed.
- Deleted `PulseBlaster/test_rigol_connection.py` — raw-socket RIGOL network diagnostic; the PyVISA-based `RigolDSG836Controller` in `rigol_dsg836.py` now handles connection diagnostics within the GUI.
- Retained `TimeTagger/CountRateLive.py` — useful standalone count-rate monitor that can verify the TimeTagger and SPD are working independently of the full confocal stack.

## [1.1.0] - 2024-03-21
### Added
- Comprehensive spectrometer application documentation in main README
- Detailed hardware requirements for spectrometer setup
- Quick start guide for spectrometer operation

### Changed
- Simplified UI by removing redundant plot profile functionality
- Improved performance by reducing widget overhead
- Updated main README structure to include three main applications
- Changed "both programs" to "all programs" in shared codebase description

### Documentation
- Integrated spectrometer documentation into main README
- Added spectrometer-specific hardware requirements
- Enhanced quick start guide with spectrometer section
- Updated repository overview to better reflect all components

## [1.0.0] - 2025-06-30
### Added
- Initial project-level `CHANGELOG.md`.
- Comprehensive `requirements.txt` listing all runtime Python dependencies (Napari, PyQt5, pandas, etc.).
- Draft packaging notes (optional vendor libraries such as `TimeTagger` and `PulseStreamer` clearly marked).
- Enhanced TIFF metadata for ImageJ/Fiji compatibility
  - Added comprehensive ImageJ-compatible metadata to saved TIFF files
  - Includes pixel scale information (microns per pixel)
  - Includes scan parameters (voltage ranges, resolution, dwell time)
  - Includes calibration constants and acquisition details
  - Automatic scale bar support when opening in ImageJ/Fiji
  - Added `tifffile` dependency for proper metadata handling

### Changed
- Replaced napari's default TIFF save with custom metadata-rich TIFF save function
- Enhanced TIFF files now contain full acquisition context for analysis

### Fixed
- Minor formatting issues encountered when building on Python 3.12.

### Deprecated
- None.

### Removed
- None.

### Security
- None.


[1.1.0]: https://github.com/NoeSilva13/Single_NV_Scannig_Microscopy/releases/tag/v1.1.0
[1.0.0]: https://github.com/NoeSilva13/Single_NV_Scannig_Microscopy/releases/tag/v1.0.0 