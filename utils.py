"""
Utility functions and constants for the Napari Scanning SPD application.
"""

import numpy as np
import tifffile

# Calibration constant: microns per volt based on empirical measurements
# Air objective 40x 0.95 NA
#MICRONS_PER_VOLT = 130 
# Oil objective 
#MICRONS_PER_VOLT = 51
# Oil objective Zeiss 100x 1.4 NA
MICRONS_PER_VOLT = 24

# Maximum zoom level allowed in the scanning interface
MAX_ZOOM_LEVEL = 9

# Default binwidth for TimeTagger counter in picoseconds (5e9 = 5 milliseconds)
BINWIDTH = int(5e9)

# Z piezo analog control calibration (DAQ ao2 -> EXT IN of the piezo controller)
# The piezo is initialized/kept in closed loop by external Thorlabs software; the
# DAQ only commands position through the EXT IN BNC. In closed loop, 0-10 V maps
# to 0-450 um, i.e. 45 um/V.
Z_UM_PER_VOLT = 45.0            # Calibration factor (micrometers per volt)
Z_MAX_TRAVEL_UM = 450.0        # Full travel of the piezo stage in micrometers
Z_VOLTAGE_RANGE = (0.0, 10.0)  # Allowed EXT IN voltage range for closed-loop control


def calculate_scale(V1, V2, image_width_px, microns_per_volt=MICRONS_PER_VOLT):
    """
    Calculate microns per pixel from a voltage span (legacy volt-based helper).

    Kept for backward compatibility with tools/data that reason in volts.
    New code works in micrometers and should use :func:`um_scale` instead.

    Args:
        V1 (float): Start voltage
        V2 (float): End voltage
        image_width_px (int): Image width in pixels
        microns_per_volt (float): Calibration factor (microns per volt)

    Returns:
        float: Scale in microns per pixel
    """
    voltage_span = abs(V2 - V1)
    scan_width_microns = voltage_span * microns_per_volt
    return scan_width_microns / image_width_px


def um_scale(a_um, b_um, n_pixels):
    """Micrometers-per-pixel for an axis spanning ``a_um``..``b_um`` in ``n_pixels``.

    This is the canonical scale helper: inputs are already in micrometers, so no
    calibration factor is applied.
    """
    if n_pixels <= 0:
        return 0.0
    return abs(float(b_um) - float(a_um)) / n_pixels 


def save_tiff_with_imagej_metadata(image_data, filepath, x_points, y_points, scan_config, timestamp=None):
    """
    Save TIFF file with comprehensive metadata that ImageJ/Fiji can interpret.
    
    Args:
        image_data (np.ndarray): 2D image array
        filepath (str): Path to save the TIFF file
        x_points (np.ndarray): Fast-axis (columns) scan positions in micrometers
        y_points (np.ndarray): Slow-axis (rows) scan positions in micrometers
        scan_config (dict): Configuration dictionary with scan parameters. May
            include ``axis_names`` (fast, slow), ``scan_mode``, ``microns_per_volt``
            and ``z_um_per_volt`` so the description reflects the real scanned axes.
        timestamp (str): Optional timestamp string
    """
    height, width = image_data.shape

    # Real scanned axes (fast -> columns, slow -> rows). Defaults keep older
    # XY-only callers working.
    axis_names = scan_config.get('axis_names', ('x', 'y'))
    fast_name = str(axis_names[0]).upper()
    slow_name = str(axis_names[1]).upper()
    scan_mode = scan_config.get('scan_mode', None)

    # Positions are already in micrometers (canonical unit).
    microns_per_pixel_x = um_scale(x_points[0], x_points[-1], width)
    microns_per_pixel_y = um_scale(y_points[0], y_points[-1], height)
    
    # Convert to pixels per micron for ImageJ (resolution tags expect pixels per unit)
    pixels_per_micron_x = 1.0 / microns_per_pixel_x if microns_per_pixel_x > 0 else 1.0
    pixels_per_micron_y = 1.0 / microns_per_pixel_y if microns_per_pixel_y > 0 else 1.0
    
    # Create ImageJ-compatible metadata
    # ImageJ expects specific format for the ImageDescription
    imagej_metadata = {
        'ImageWidth': width,
        'ImageLength': height,
        'BitsPerSample': 32,  # float32
        'SampleFormat': 3,    # IEEE floating point
        'unit': 'micron',
        'finterval': scan_config.get('dwell_time', 0.1),
        'spacing': min(microns_per_pixel_x, microns_per_pixel_y),
        'loop': False,
        'min': float(np.nanmin(image_data)),
        'max': float(np.nanmax(image_data)),
    }
    
    # Create comprehensive ImageDescription
    image_description = f"""ImageJ=1.54
images=1
slices=1
frames=1
unit=micron
finterval={scan_config.get('dwell_time', 0.1)}
spacing={min(microns_per_pixel_x, microns_per_pixel_y)}
loop=false
min={float(np.nanmin(image_data))}
max={float(np.nanmax(image_data))}

Confocal NV Microscopy Data
Acquisition Software: NV Scanning Microscopy
Scan Mode: {scan_mode if scan_mode is not None else fast_name + slow_name}
{fast_name} Range: {x_points[0]:.3f} to {x_points[-1]:.3f} um
{slow_name} Range: {y_points[0]:.3f} to {y_points[-1]:.3f} um
{fast_name} Resolution: {width} pixels
{slow_name} Resolution: {height} pixels
{fast_name} Scale: {microns_per_pixel_x:.6f} um/pixel
{slow_name} Scale: {microns_per_pixel_y:.6f} um/pixel
Calibration (galvo): {scan_config.get('microns_per_volt', MICRONS_PER_VOLT)} um/V"""

    z_um_per_volt = scan_config.get('z_um_per_volt', None)
    if z_um_per_volt is not None:
        image_description += f"\nCalibration (piezo Z): {z_um_per_volt} um/V"

    image_description += f"""
Dwell Time: {scan_config.get('dwell_time', 0.1)} s
Detector: Single Photon Detector (SPD)
Scanner: Thorlabs LSKGG4 Galvo-Galvo"""

    if timestamp:
        image_description += f"\nTimestamp: {timestamp}"
    
    # Prepare TIFF tags for ImageJ compatibility
    # Resolution unit: 1=none, 2=inches, 3=centimeters
    # We'll use unit=1 (none) and put the actual scale in ImageDescription
    tiff_tags = {
        'ImageDescription': image_description,
        'Software': 'NV Scanning Microscopy v1.0',
        'XResolution': (pixels_per_micron_x, 1),  # Stored as rational number
        'YResolution': (pixels_per_micron_y, 1),  # Stored as rational number
        'ResolutionUnit': 1,  # No absolute unit (we specify in description)
    }
    
    # Save TIFF with metadata
    tifffile.imwrite(
        filepath,
        image_data.astype(np.float32),
        metadata=tiff_tags,
        resolution=(pixels_per_micron_x, pixels_per_micron_y),
        imagej=True  # Enable ImageJ-specific metadata format
    )
    
    print(f"💾 TIFF saved with ImageJ metadata: {filepath}")
    print(f"📏 Scale: {microns_per_pixel_x:.3f} × {microns_per_pixel_y:.3f} um/pixel") 