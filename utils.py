"""
Utility functions and constants for the Napari Scanning SPD application.
"""

import numpy as np
import tifffile
from napari.utils.notifications import show_info

# Calibration constant: microns per volt based on empirical measurements
MICRONS_PER_VOLT = 130

# Maximum zoom level allowed in the scanning interface
MAX_ZOOM_LEVEL = 6

# Default binwidth for TimeTagger counter in picoseconds (5e9 = 5 milliseconds)
BINWIDTH = int(5e9)

# Piezo auto-focus parameters (in micrometers)
PIEZO_COARSE_STEP = 5.0  # Step size for coarse focus scan
PIEZO_FINE_STEP = 0.5    # Step size for fine focus scan
PIEZO_FINE_RANGE = 10.0  # Range around peak for fine scan


def calculate_scale(V1, V2, image_width_px, microns_per_volt=MICRONS_PER_VOLT):
    """
    Calculate microns per pixel based on empirical calibration.
    Used for X and Y axes which are in volts and need conversion.
    
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


def calculate_scale_z(z1, z2, image_width_px):
    """
    Calculate microns per pixel for Z-axis.
    Z-axis values are already in micrometers (no voltage conversion needed).
    
    Args:
        z1 (float): Start Z position in micrometers
        z2 (float): End Z position in micrometers
        image_width_px (int): Image width in pixels
        
    Returns:
        float: Scale in microns per pixel
    """
    z_span = abs(z2 - z1)
    return z_span / image_width_px if image_width_px > 0 else 0.0 


def save_tiff_with_imagej_metadata(image_data, filepath, x_points, y_points, scan_config, timestamp=None, 
                                   scale_x=None, scale_y=None, x_in_volts=True, y_in_volts=True):
    """
    Save TIFF file with comprehensive metadata that ImageJ/Fiji can interpret.
    
    Args:
        image_data (np.ndarray): 2D image array
        filepath (str): Path to save the TIFF file
        x_points (np.ndarray): X scan positions (in volts if x_in_volts=True, else in micrometers)
        y_points (np.ndarray): Y scan positions (in volts if y_in_volts=True, else in micrometers)
        scan_config (dict): Configuration dictionary with scan parameters
        timestamp (str): Optional timestamp string
        scale_x (float): Optional pre-calculated X scale in um/pixel (overrides calculation)
        scale_y (float): Optional pre-calculated Y scale in um/pixel (overrides calculation)
        x_in_volts (bool): Whether x_points are in volts (True) or micrometers (False)
        y_in_volts (bool): Whether y_points are in volts (True) or micrometers (False)
    """
    height, width = image_data.shape
    
    # Calculate microns per pixel (use provided scales if available, otherwise calculate)
    if scale_x is not None:
        microns_per_pixel_x = scale_x
    elif x_in_volts:
        microns_per_pixel_x = calculate_scale(x_points[0], x_points[-1], width)
    else:
        # X points are already in micrometers
        microns_per_pixel_x = calculate_scale_z(x_points[0], x_points[-1], width)
    
    if scale_y is not None:
        microns_per_pixel_y = scale_y
    elif y_in_volts:
        microns_per_pixel_y = calculate_scale(y_points[0], y_points[-1], height)
    else:
        # Y points are already in micrometers
        microns_per_pixel_y = calculate_scale_z(y_points[0], y_points[-1], height)
    
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
X Range: {x_points[0]:.3f} to {x_points[-1]:.3f} V
Y Range: {y_points[0]:.3f} to {y_points[-1]:.3f} V
X Resolution: {width} pixels
Y Resolution: {height} pixels
X Scale: {microns_per_pixel_x:.6f} um/pixel
Y Scale: {microns_per_pixel_y:.6f} um/pixel
Calibration: {MICRONS_PER_VOLT} um/V
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
    
    show_info(f"💾 TIFF saved with ImageJ metadata: {filepath}")
    show_info(f"📏 Scale: {microns_per_pixel_x:.3f} × {microns_per_pixel_y:.3f} um/pixel") 