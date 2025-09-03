# Changelog

All notable changes to this project will be documented in this file following [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) guidelines.

## [1.2.0] - 2024-12-01
### Added
- **Z-Axis Scanning Functionality**: Complete 3D imaging capabilities
  - X-Z scanning (X vs Z at fixed Y position)
  - Y-Z scanning (Y vs Z at fixed X position)
  - 3D volumetric scanning (X-Y scans over Z steps)
  - Integration with Thorlabs piezo controller for Z-axis control
- **New Modules**:
  - `z_scan_controller.py`: Main controller for Z-axis scanning operations
  - `z_scan_data_manager.py`: Data management for 3D scan results
  - `widgets/z_scan_controls.py`: GUI components for Z scanning
- **Extended GUI**: New Z scan parameter controls and scan type selection
- **3D Data Management**: Multiple export formats (NPZ, TIFF, MIP)
- **Progress Tracking**: Real-time progress updates for long Z scans
- **Test Suite**: `test_z_scanning.py` for functionality verification

### Changed
- Extended main confocal control with Z scanning capabilities
- Enhanced scan parameters widget to include Z-axis controls
- Updated data management to handle 3D volumetric data
- Improved Napari viewer integration for 3D visualization
- Extended hardware requirements to include piezo controller

### Documentation
- Added comprehensive `README_Z_Scanning.md` with detailed usage guide
- Updated main README to include Z scanning features
- Added hardware requirements for piezo controller
- Enhanced quick start guide with Z scanning instructions
- Added API reference and troubleshooting sections

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


[1.2.0]: https://github.com/NoeSilva13/Single_NV_Scannig_Microscopy/releases/tag/v1.2.0
[1.1.0]: https://github.com/NoeSilva13/Single_NV_Scannig_Microscopy/releases/tag/v1.1.0
[1.0.0]: https://github.com/NoeSilva13/Single_NV_Scannig_Microscopy/releases/tag/v1.0.0 