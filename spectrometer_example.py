#!/usr/bin/env python3
"""
Example script demonstrating programmatic use of the spectrometer components
without the GUI interface.
"""

import time
import numpy as np
import matplotlib.pyplot as plt
from Camera.camera_video_mode import POACameraController
from Camera import pyPOACamera


def capture_and_process_spectrum():
    """Example function to capture and process a spectrum"""
    
    # Initialize camera
    camera = POACameraController()
    
    # List available cameras
    cameras = camera.list_available_cameras()
    if not cameras:
        print("No cameras found!")
        return
    
    print(f"Found {len(cameras)} cameras:")
    for i, cam in enumerate(cameras):
        print(f"  {i}: {cam.cameraModelName}")
    
    # Connect to first camera at 1920x1080
    print("\nConnecting to camera...")
    if not camera.connect(camera_index=0, width=1920, height=1080):
        print("Failed to connect to camera!")
        return
    
    print(f"Connected to {camera.camera_props.cameraModelName}")
    print(f"Image size: {camera.img_width}x{camera.img_height}")
    
    # Set camera parameters
    camera.set_exposure(50000)  # 50ms exposure
    camera.set_gain(300)        # Gain 300
    
    # Start streaming
    print("Starting camera stream...")
    if not camera.start_stream():
        print("Failed to start stream!")
        camera.disconnect()
        return
    
    # Wait for camera to stabilize
    time.sleep(1)
    
    # Capture a frame
    print("Capturing frame...")
    frame = None
    for i in range(10):  # Try up to 10 times
        frame = camera.get_frame()
        if frame is not None:
            break
        time.sleep(0.1)
    
    if frame is None:
        print("Failed to capture frame!")
        camera.disconnect()
        return
    
    print(f"Captured frame: {frame.shape}, dtype: {frame.dtype}")
    
    # Process spectrum
    print("Processing spectrum...")
    spectrum = process_horizontal_line_spectrum(frame)
    
    # Create wavelength calibration (400-800 nm)
    wavelengths = np.linspace(400, 800, len(spectrum))
    
    # Plot results
    plt.figure(figsize=(12, 8))
    
    # Plot the camera image
    plt.subplot(2, 1, 1)
    if len(frame.shape) == 3:
        plt.imshow(frame[:, :, 0], cmap='gray')
    else:
        plt.imshow(frame, cmap='gray')
    plt.title('Camera Image')
    plt.xlabel('X (pixels)')
    plt.ylabel('Y (pixels)')
    plt.colorbar()
    
    # Plot the spectrum
    plt.subplot(2, 1, 2)
    plt.plot(wavelengths, spectrum, 'b-', linewidth=2)
    plt.title('Extracted Spectrum')
    plt.xlabel('Wavelength (nm)')
    plt.ylabel('Intensity')
    plt.grid(True)
    
    plt.tight_layout()
    plt.show()
    
    # Save spectrum data
    save_spectrum_data(wavelengths, spectrum, "example_spectrum.csv")
    
    # Cleanup
    camera.stop_stream()
    camera.disconnect()
    print("Camera disconnected.")


def process_horizontal_line_spectrum(frame, roi_center=None, roi_height=50):
    """
    Process a camera frame to extract horizontal line spectrum
    
    Args:
        frame: Camera frame (numpy array)
        roi_center: Y position of ROI center (None for image center)
        roi_height: Height of ROI in pixels
    
    Returns:
        1D spectrum array
    """
    # Handle different frame formats
    if len(frame.shape) == 3:
        # Multi-channel image, convert to grayscale
        if frame.shape[2] == 3:
            # RGB image
            frame = np.dot(frame[...,:3], [0.2989, 0.5870, 0.1140])
        else:
            # Single channel with extra dimension
            frame = frame[:, :, 0]
    
    # Set ROI center to image center if not specified
    if roi_center is None:
        roi_center = frame.shape[0] // 2
    
    # Calculate ROI bounds
    roi_start = max(0, roi_center - roi_height // 2)
    roi_end = min(frame.shape[0], roi_center + roi_height // 2)
    
    # Extract ROI
    roi = frame[roi_start:roi_end, :]
    
    # Average vertically to get horizontal spectrum
    spectrum = np.mean(roi, axis=0, dtype=np.float64)
    
    return spectrum


def save_spectrum_data(wavelengths, spectrum, filename):
    """Save spectrum data to CSV file"""
    try:
        with open(filename, 'w') as f:
            f.write("Wavelength,Intensity\n")
            for w, i in zip(wavelengths, spectrum):
                f.write(f"{w:.2f},{i:.6f}\n")
        print(f"Spectrum saved to {filename}")
    except Exception as e:
        print(f"Error saving spectrum: {e}")


def capture_dark_and_reference_corrected_spectrum():
    """Example showing dark frame and reference correction"""
    
    # Initialize camera
    camera = POACameraController()
    
    if not camera.connect(camera_index=0, width=1920, height=1080):
        print("Failed to connect to camera!")
        return
    
    # Set camera parameters
    camera.set_exposure(50000)
    camera.set_gain(300)
    
    if not camera.start_stream():
        print("Failed to start stream!")
        camera.disconnect()
        return
    
    # Wait for stabilization
    time.sleep(1)
    
    # Capture dark frame
    input("Block all light and press Enter to capture dark frame...")
    dark_frame = camera.get_frame()
    if dark_frame is None:
        print("Failed to capture dark frame!")
        camera.disconnect()
        return
    
    dark_spectrum = process_horizontal_line_spectrum(dark_frame)
    print("Dark frame captured")
    
    # Capture reference frame
    input("Set up reference light source and press Enter to capture reference...")
    reference_frame = camera.get_frame()
    if reference_frame is None:
        print("Failed to capture reference frame!")
        camera.disconnect()
        return
    
    reference_spectrum = process_horizontal_line_spectrum(reference_frame)
    print("Reference frame captured")
    
    # Capture sample spectrum
    input("Set up sample and press Enter to capture spectrum...")
    sample_frame = camera.get_frame()
    if sample_frame is None:
        print("Failed to capture sample frame!")
        camera.disconnect()
        return
    
    sample_spectrum = process_horizontal_line_spectrum(sample_frame)
    print("Sample spectrum captured")
    
    # Apply corrections
    # Dark subtraction
    sample_corrected = sample_spectrum - dark_spectrum
    reference_corrected = reference_spectrum - dark_spectrum
    
    # Reference normalization
    reference_corrected = np.where(reference_corrected > 0, reference_corrected, 1)
    sample_normalized = sample_corrected / reference_corrected
    
    # Create wavelength axis
    wavelengths = np.linspace(400, 800, len(sample_spectrum))
    
    # Plot comparison
    plt.figure(figsize=(12, 10))
    
    plt.subplot(3, 1, 1)
    plt.plot(wavelengths, sample_spectrum, 'b-', label='Raw Sample')
    plt.plot(wavelengths, dark_spectrum, 'k-', label='Dark')
    plt.plot(wavelengths, reference_spectrum, 'r-', label='Reference')
    plt.legend()
    plt.title('Raw Spectra')
    plt.ylabel('Intensity')
    plt.grid(True)
    
    plt.subplot(3, 1, 2)
    plt.plot(wavelengths, sample_corrected, 'b-', label='Sample - Dark')
    plt.plot(wavelengths, reference_corrected, 'r-', label='Reference - Dark')
    plt.legend()
    plt.title('Dark Corrected Spectra')
    plt.ylabel('Intensity')
    plt.grid(True)
    
    plt.subplot(3, 1, 3)
    plt.plot(wavelengths, sample_normalized, 'g-', linewidth=2)
    plt.title('Final Normalized Spectrum')
    plt.xlabel('Wavelength (nm)')
    plt.ylabel('Relative Intensity')
    plt.grid(True)
    
    plt.tight_layout()
    plt.show()
    
    # Save corrected spectrum
    save_spectrum_data(wavelengths, sample_normalized, "corrected_spectrum.csv")
    
    # Cleanup
    camera.stop_stream()
    camera.disconnect()


if __name__ == "__main__":
    print("CCD Camera Spectrometer Example")
    print("================================")
    print("1. Basic spectrum capture")
    print("2. Dark and reference corrected spectrum")
    
    choice = input("\nChoose example (1 or 2): ")
    
    if choice == "1":
        capture_and_process_spectrum()
    elif choice == "2":
        capture_dark_and_reference_corrected_spectrum()
    else:
        print("Invalid choice!") 