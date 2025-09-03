# Z-Axis Scanning Functionality

## Overview

This module extends the confocal microscopy system with comprehensive Z-axis scanning capabilities, enabling 3D imaging and depth-resolved measurements. The system integrates with the existing galvo scanner for X-Y positioning and a Thorlabs piezo stage for Z-axis control.

## Features

### Scan Types

1. **X-Y Scan** (Original functionality)
   - Standard 2D raster scanning
   - Galvo-controlled X-Y positioning
   - Real-time image acquisition

2. **X-Z Scan**
   - Scan X vs Z at fixed Y position
   - Useful for depth profiling along X-axis
   - Generates 2D image (Z vs X)

3. **Y-Z Scan**
   - Scan Y vs Z at fixed X position
   - Useful for depth profiling along Y-axis
   - Generates 2D image (Z vs Y)

4. **3D Volumetric Scan**
   - Complete 3D imaging capability
   - X-Y scans over multiple Z steps
   - Generates 3D volume data (Z, Y, X)

## Hardware Requirements

### Z-Axis Control
- **Thorlabs Benchtop Precision Piezo Controller**
- Serial Number: 44506104 (configurable)
- Travel Range: 0-20 µm (typical)
- Resolution: <1 nm

### Existing Hardware
- Thorlabs LSKGG4 Galvo-Galvo Scanner
- National Instruments USB-6453 DAQ
- Single Photon Detector (SPD)
- TimeTagger for photon counting

## Software Architecture

### Core Modules

#### `z_scan_controller.py`
Main controller for Z-axis scanning operations:
- `ZScanController` class
- Methods: `scan_xz()`, `scan_yz()`, `scan_3d()`
- Progress tracking and error handling

#### `z_scan_data_manager.py`
Data management for Z scan results:
- `ZScanDataManager` class
- Save/load 3D data
- Multiple export formats (NPZ, TIFF, MIP)

#### `widgets/z_scan_controls.py`
GUI components for Z scanning:
- `ExtendedScanParametersWidget` class
- Scan type selection
- Z-axis parameter controls
- Progress tracking widgets

### Integration Points

The Z scanning functionality integrates with existing components:
- **Scan Parameters Manager**: Extended to handle Z-axis parameters
- **Data Manager**: Enhanced for 3D data handling
- **Piezo Controller**: Reused from auto-focus functionality
- **Napari Viewer**: Extended for 3D visualization

## Usage

### Basic Workflow

1. **Initialize System**
   ```python
   # Piezo controller is automatically initialized
   piezo_controller = PiezoController()
   z_scan_controller = ZScanController(piezo_controller, output_task, counter, binwidth)
   ```

2. **Configure Parameters**
   - Set X-Y scan ranges and resolution
   - Set Z scan range (0-20 µm typical)
   - Choose scan type (X-Y, X-Z, Y-Z, 3D)
   - Set dwell time and fixed positions

3. **Execute Scan**
   - Use "Start Z Scan" button for Z-axis scans
   - Use "New Scan" button for X-Y scans
   - Monitor progress in real-time

4. **Data Management**
   - Automatic saving in multiple formats
   - 3D data stored as NPZ files
   - Individual Z-slices as TIFF files
   - Maximum intensity projections

### Parameter Configuration

#### X-Y Parameters
- **X Range**: -10V to +10V (typical: -1V to +1V)
- **Y Range**: -10V to +10V (typical: -1V to +1V)
- **Resolution**: 2-1000 pixels per axis
- **Dwell Time**: 0.001-10 seconds per pixel

#### Z-Axis Parameters
- **Z Range**: 0-20 µm (piezo travel limit)
- **Z Resolution**: 2-100 steps
- **Fixed Positions**: For X-Z and Y-Z scans
  - Fixed X: -10V to +10V
  - Fixed Y: -10V to +10V

#### Scan Types
- **X-Y**: Standard 2D scanning
- **X-Z**: X vs Z at fixed Y position
- **Y-Z**: Y vs Z at fixed X position
- **3D**: Complete volumetric scan

## Data Formats

### NPZ Files
Comprehensive data storage with metadata:
```python
# 3D scan data
np.savez(filename, 
         volume=volume_data,           # 3D array (Z, Y, X)
         x_points=x_positions,         # X scan positions
         y_points=y_positions,         # Y scan positions
         z_points=z_positions,         # Z scan positions
         dwell_time=dwell_time,        # Dwell time per pixel
         scan_time=total_scan_time,    # Total scan duration
         scale_x=scale_x,              # Physical scale (µm/pixel)
         scale_y=scale_y,              # Physical scale (µm/pixel)
         scale_z=scale_z,              # Physical scale (µm/step)
         scan_type=scan_type,          # Scan type identifier
         timestamp=timestamp)          # Scan timestamp
```

### TIFF Files
ImageJ-compatible format with metadata:
- Individual Z-slices for 3D scans
- Maximum intensity projections
- Physical scale information
- Scan parameters in metadata

### Data Organization
```
z_scan_data/
├── xz_scan_20241201-143022.npz
├── xz_scan_20241201-143022.tiff
├── yz_scan_20241201-143156.npz
├── yz_scan_20241201-143156.tiff
├── 3d_scan_20241201-143245.npz
├── 3d_scan_20241201-143245_z0.00.tiff
├── 3d_scan_20241201-143245_z0.50.tiff
├── 3d_scan_20241201-143245_z1.00.tiff
└── 3d_scan_20241201-143245_mip.tiff
```

## Performance Considerations

### Scan Times
Typical scan durations:
- **X-Z/Y-Z**: 1-10 minutes (depending on resolution)
- **3D Scan**: 10-60 minutes (depending on volume size)
- **X-Y**: 1-5 minutes (existing functionality)

### Memory Usage
- **2D Scans**: 1-10 MB typical
- **3D Scans**: 10-1000 MB (depending on resolution)
- **Data Storage**: NPZ compression reduces file sizes

### Optimization Tips
1. **Resolution Trade-offs**: Higher resolution = longer scan times
2. **Z-Step Size**: Smaller steps = better depth resolution
3. **Dwell Time**: Balance between signal quality and scan speed
4. **Memory Management**: Large 3D scans may require significant RAM

## Error Handling

### Common Issues
1. **Piezo Connection**: Verify piezo controller is connected
2. **Travel Limits**: Z range must be within piezo limits (0-20 µm)
3. **Memory Limits**: Large 3D scans may exceed available memory
4. **Hardware Errors**: Check galvo and piezo communication

### Recovery Procedures
1. **Scan Interruption**: Use "Stop Z Scan" button
2. **Hardware Reset**: Restart piezo controller if needed
3. **Data Recovery**: Partial scans are saved automatically

## Visualization

### 2D Scans (X-Z, Y-Z)
- Displayed as standard 2D images in Napari
- Z-axis mapped to image rows
- X/Y-axis mapped to image columns
- Real-time contrast adjustment

### 3D Scans
- Volume rendering in Napari
- Maximum intensity projections
- Orthogonal slice views
- Interactive 3D navigation

## Future Enhancements

### Planned Features
1. **Advanced Scan Patterns**: Spiral, random access scanning
2. **Adaptive Resolution**: Variable resolution based on signal
3. **Real-time 3D**: Live 3D visualization during scanning
4. **Multi-channel**: Support for multiple detection channels
5. **Automated Analysis**: Built-in 3D data analysis tools

### Integration Opportunities
1. **Auto-focus Integration**: Automatic Z-range determination
2. **ODMR Integration**: 3D ODMR scanning
3. **Pulse Sequence Integration**: Time-resolved 3D imaging
4. **External Analysis**: Export to external analysis software

## Troubleshooting

### Piezo Issues
```python
# Check piezo connection
if not piezo_controller._is_connected:
    print("Piezo not connected - check hardware")

# Check travel range
max_travel = piezo_controller.get_max_travel()
print(f"Piezo travel range: 0-{max_travel} µm")
```

### Performance Issues
```python
# Monitor memory usage
import psutil
memory_usage = psutil.virtual_memory().percent
print(f"Memory usage: {memory_usage}%")

# Estimate scan time
total_pixels = x_res * y_res * z_res
estimated_time = total_pixels * dwell_time / 60  # minutes
print(f"Estimated scan time: {estimated_time:.1f} minutes")
```

### Data Issues
```python
# Verify data integrity
data, metadata = z_scan_data_manager.load_scan_data(filepath)
print(f"Data shape: {data.shape}")
print(f"Scan type: {metadata['scan_type']}")
print(f"Scan time: {metadata['scan_time']:.1f} seconds")
```

## API Reference

### ZScanController
```python
class ZScanController:
    def scan_xz(x_points, z_points, y_fixed, dwell_time=0.002)
    def scan_yz(y_points, z_points, x_fixed, dwell_time=0.002)
    def scan_3d(x_points, y_points, z_points, dwell_time=0.002)
    def stop_scan()
    def is_scanning() -> bool
```

### ZScanDataManager
```python
class ZScanDataManager:
    def save_xz_scan(image_data, metadata) -> str
    def save_yz_scan(image_data, metadata) -> str
    def save_3d_scan(volume_data, metadata) -> str
    def load_scan_data(filepath) -> Tuple[np.ndarray, Dict]
    def get_scan_summary(filepath) -> Dict
    def list_scan_files() -> list
```

### ExtendedScanParametersWidget
```python
class ExtendedScanParametersWidget:
    def get_parameters() -> Dict
    def update_values(x_range, y_range, z_range, x_res, y_res, z_res, dwell_time)
    def apply_changes()
```

## Contributing

When contributing to the Z scanning functionality:

1. **Testing**: Test all scan types with various parameters
2. **Documentation**: Update this README for new features
3. **Error Handling**: Add appropriate error handling for new features
4. **Performance**: Consider performance implications of changes
5. **Compatibility**: Ensure compatibility with existing functionality

## License

This Z scanning functionality is part of the Single NV Scanning Microscopy project and follows the same licensing terms as the main project.
