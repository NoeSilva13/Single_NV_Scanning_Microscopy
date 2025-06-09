"""
Utility functions and constants for the Napari Scanning SPD application.
"""

# Calibration constant: microns per volt based on empirical measurements
MICRONS_PER_VOLT = 87.5


def calculate_scale(V1, V2, image_width_px, microns_per_volt=MICRONS_PER_VOLT):
    """
    Calculate microns per pixel based on empirical calibration.
    
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