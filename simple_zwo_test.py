#!/usr/bin/env python3
"""
Simple test script for ZWO ASI camera.
This basic test checks camera connectivity and captures a single image.
"""

import sys
import time

# Import the ZWO camera module
try:
    from Camera import zwo_camera
except ImportError:
    try:
        import zwo_camera
    except ImportError:
        print("Error: Could not import zwo_camera module")
        print("Make sure zwo_camera.py is in the same directory or in your Python path")
        sys.exit(1)

def main():
    print("Simple ZWO ASI Camera Test")
    print("-" * 30)
    
    try:
        # Check if the library can be initialized
        print("Checking camera library initialization...")
        
        # Get number of connected cameras
        num_cameras = zwo_camera.get_num_cameras()
        print(f"Number of connected cameras: {num_cameras}")
        
        if num_cameras == 0:
            print("\nNo cameras detected!")
            print("Please check:")
            print("1. Camera is connected via USB")
            print("2. ASICamera2.dll is available")
            print("3. Camera drivers are properly installed")
            return False
        
        # List available cameras
        print("\nAvailable cameras:")
        cameras = zwo_camera.list_cameras()
        for i, name in enumerate(cameras):
            print(f"  {i}: {name}")
        
        # Select first camera
        camera_id = 0
        print(f"\nTesting camera {camera_id}: {cameras[camera_id]}")
        
        # Initialize camera
        print("Opening camera...")
        camera = zwo_camera.Camera(camera_id)
        
        # Get camera info
        info = camera.get_camera_property()
        print(f"Camera: {info['Name']}")
        print(f"Max Resolution: {info['MaxWidth']} x {info['MaxHeight']}")
        print(f"Color Camera: {info['IsColorCam']}")
        print(f"Pixel Size: {info['PixelSize']:.2f} μm")
        
        # Set basic parameters
        print("\nSetting camera parameters...")
        
        # Set a reasonable ROI (smaller for faster testing)
        width = min(800, info['MaxWidth'])
        height = min(600, info['MaxHeight'])
        camera.set_roi(width=width, height=height)
        
        # Set image type
        camera.set_image_type(zwo_camera.ASI_IMG_RAW8)
        
        # Set exposure and gain
        camera.set_control_value(zwo_camera.ASI_EXPOSURE, 10000)  # 10ms
        camera.set_control_value(zwo_camera.ASI_GAIN, 50)
        
        # Get current settings
        roi = camera.get_roi()
        print(f"ROI: {roi[2]} x {roi[3]} at ({roi[0]}, {roi[1]})")
        
        exposure = camera.get_control_value(zwo_camera.ASI_EXPOSURE)[0]
        gain = camera.get_control_value(zwo_camera.ASI_GAIN)[0]
        print(f"Exposure: {exposure} μs")
        print(f"Gain: {gain}")
        
        # Capture test image
        print("\nCapturing test image...")
        start_time = time.time()
        
        image = camera.capture()
        
        capture_time = time.time() - start_time
        print(f"Capture completed in {capture_time:.3f} seconds")
        
        # Display image statistics
        print(f"Image shape: {image.shape}")
        print(f"Image type: {image.dtype}")
        print(f"Pixel values - Min: {image.min()}, Max: {image.max()}, Mean: {image.mean():.1f}")
        
        # Try to save image (optional)
        try:
            import numpy as np
            # Save as raw numpy array
            np.save('test_image.npy', image)
            print("Image saved as 'test_image.npy'")
        except ImportError:
            print("NumPy not available for saving")
        
        # Close camera
        camera.close()
        print("\nCamera closed successfully")
        
        print("\n✓ Test completed successfully!")
        return True
        
    except zwo_camera.ZWO_Error as e:
        print(f"\nZWO Camera Error: {e}")
        if hasattr(e, 'error_code'):
            print(f"Error code: {e.error_code}")
        return False
        
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("ZWO ASI Camera Simple Test")
    print("Ensure ASICamera2.dll is in your PATH or current directory\n")
    
    success = main()
    
    if success:
        print("\nTest passed! Your ZWO camera is working correctly.")
    else:
        print("\nTest failed! Please check your camera setup.")
        sys.exit(1) 