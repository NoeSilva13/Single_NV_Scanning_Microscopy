# Changelog

All notable changes to this project will be documented in this file following [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) guidelines.

## [Unreleased] - 2026-07-17
### Changed
- Migrated the whole GUI stack from PyQt5 to PySide6 (Qt6) through the `qtpy` abstraction layer: all `PyQt5.*` imports now go through `qtpy.*`, so the binding can be swapped without touching source.
- Applied Qt6 compatibility fixes: `QDesktopWidget().screenGeometry()` replaced with `QGuiApplication.primaryScreen().availableGeometry()`; `.exec_()` → `.exec()`; enums fully qualified (`Qt.AlignmentFlag`, `Qt.Orientation`, `QMessageBox.StandardButton`/`Icon`, `QFileDialog.FileMode`).
- Replaced Thorlabs Kinesis USB Z control with DAQ analog output (`Dev1/ao2` → piezo EXT IN) via new `daq_z_controller.py` (`DAQZController`).
- Moved the auto-focus Z-sweep algorithm into `widgets/auto_focus.py` (`run_focus_sweep`); the Z controller is now a minimal voltage/position mapper.
- Simplified `widgets/piezo_controls.py` for commanded-position display (no USB connection / no analog readback).

### Removed
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