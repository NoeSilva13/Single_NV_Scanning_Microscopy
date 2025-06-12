#!/usr/bin/env python3
"""
Basic test script for ZWO ASI camera using zwo_camera.py module.
This script demonstrates:
1. Camera detection and listing
2. Camera initialization
3. Basic configuration (ROI, exposure, gain)
4. Image capture
5. Proper cleanup
"""

import sys
import os
import time
import numpy as np
from datetime import datetime

# Import the ZWO camera module
try:
    from Camera import zwo_camera
except ImportError:
    import zwo_camera

def print_camera_info(camera):
    """Print detailed camera information"""
    print("\n=== Camera Information ===")
    cam_info = camera.get_camera_property()
    for key, value in cam_info.items():
        print(f"{key}: {value}")
    
    print("\n=== Available Controls ===")
    controls = camera.get_controls()
    for name, control in controls.items():
        print(f"{name}: Min={control['MinValue']}, Max={control['MaxValue']}, "
              f"Default={control['DefaultValue']}, Auto={control['IsAutoSupported']}")

def test_camera_basic():
    """Basic camera functionality test"""
    print("ZWO ASI Camera Basic Test")
    print("=" * 40)
    
    try:
        # Check for connected cameras
        num_cameras = zwo_camera.get_num_cameras()
        print(f"Number of connected cameras: {num_cameras}")
        
        if num_cameras == 0:
            print("No cameras found. Please check:")
            print("1. Camera is connected via USB")
            print("2. ASICamera2.dll is in the system PATH or current directory")
            print("3. Camera drivers are installed")
            return False
        
        # List all available cameras
        print("\nAvailable cameras:")
        camera_list = zwo_camera.list_cameras()
        for i, camera_name in enumerate(camera_list):
            print(f"  {i}: {camera_name}")
        
        # Use the first camera
        camera_id = 0
        print(f"\nInitializing camera {camera_id}...")
        
        # Open and initialize camera
        camera = zwo_camera.Camera(camera_id)
        print("Camera opened successfully!")
        
        # Print camera information
        print_camera_info(camera)
        
        # Set basic parameters
        print("\n=== Setting Camera Parameters ===")
        
        # Set ROI (Region of Interest) - using full sensor
        camera.set_roi()  # This will use maximum width/height
        roi = camera.get_roi()
        print(f"ROI set to: x={roi[0]}, y={roi[1]}, width={roi[2]}, height={roi[3]}")
        
        # Set image type to RAW8 for faster processing
        camera.set_image_type(zwo_camera.ASI_IMG_RAW8)
        print(f"Image type set to: {camera.get_image_type()}")
        
        # Set exposure time (in microseconds)
        exposure_us = 100000  # 100ms
        camera.set_control_value(zwo_camera.ASI_EXPOSURE, exposure_us)
        print(f"Exposure set to: {exposure_us} μs")
        
        # Set gain
        gain_value = 100
        camera.set_control_value(zwo_camera.ASI_GAIN, gain_value)
        print(f"Gain set to: {gain_value}")
        
        # Disable auto exposure and gain for consistent results
        camera.set_control_value(zwo_camera.ASI_EXPOSURE, exposure_us, auto=False)
        camera.set_control_value(zwo_camera.ASI_GAIN, gain_value, auto=False)
        
        print("\n=== Capturing Images ===")
        
        # Capture a few test images
        for i in range(3):
            print(f"Capturing image {i+1}/3...")
            start_time = time.time()
            
            # Capture image
            img = camera.capture()
            
            capture_time = time.time() - start_time
            print(f"  Image captured in {capture_time:.3f} seconds")
            print(f"  Image shape: {img.shape}")
            print(f"  Image dtype: {img.dtype}")
            print(f"  Image min/max values: {img.min()}/{img.max()}")
            print(f"  Image mean: {img.mean():.2f}")
            
            # Save image with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"test_image_{timestamp}_{i+1}.png"
            
            try:
                # Save using PIL (if available)
                from PIL import Image
                pil_image = Image.fromarray(img)
                pil_image.save(filename)
                print(f"  Image saved as: {filename}")
            except ImportError:
                print("  PIL not available, skipping image save")
            except Exception as e:
                print(f"  Failed to save image: {e}")
            
            # Wait between captures
            if i < 2:
                time.sleep(1)
        
        print("\n=== Testing Video Mode ===")
        try:
            # Start video capture mode
            camera.start_video_capture()
            print("Video capture mode started")
            
            # Capture a few video frames
            for i in range(3):
                print(f"Capturing video frame {i+1}/3...")
                timeout_ms = 2000  # 2 second timeout
                frame = camera.capture_video_frame(timeout=timeout_ms)
                print(f"  Frame shape: {frame.shape}, mean: {frame.mean():.2f}")
            
            # Stop video capture
            camera.stop_video_capture()
            print("Video capture mode stopped")
            
        except Exception as e:
            print(f"Video mode test failed: {e}")
        
        # Test control values
        print("\n=== Current Control Values ===")
        control_values = camera.get_control_values()
        for name, value in control_values.items():
            print(f"{name}: {value}")
        
        # Close camera
        camera.close()
        print("\nCamera closed successfully!")
        
        return True
        
    except zwo_camera.ZWO_Error as e:
        print(f"ZWO Camera Error: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        print("Traceback:")
        import traceback
        traceback.print_exc()
        return False

def test_multiple_cameras():
    """Test multiple cameras if available"""
    print("\n" + "=" * 40)
    print("Multiple Camera Test")
    print("=" * 40)
    
    try:
        num_cameras = zwo_camera.get_num_cameras()
        if num_cameras < 2:
            print("Less than 2 cameras connected, skipping multiple camera test")
            return
        
        cameras = []
        
        # Open all cameras
        for i in range(min(num_cameras, 3)):  # Test up to 3 cameras
            print(f"Opening camera {i}...")
            camera = zwo_camera.Camera(i)
            cameras.append(camera)
            
            # Set basic parameters
            camera.set_roi(width=640, height=480)  # Smaller ROI for faster capture
            camera.set_control_value(zwo_camera.ASI_EXPOSURE, 50000)  # 50ms
            camera.set_control_value(zwo_camera.ASI_GAIN, 50)
        
        print(f"Successfully opened {len(cameras)} cameras")
        
        # Capture from all cameras simultaneously
        print("Capturing from all cameras...")
        images = []
        for i, camera in enumerate(cameras):
            img = camera.capture()
            images.append(img)
            print(f"Camera {i}: {img.shape}, mean={img.mean():.2f}")
        
        # Close all cameras
        for i, camera in enumerate(cameras):
            camera.close()
            print(f"Camera {i} closed")
        
    except Exception as e:
        print(f"Multiple camera test failed: {e}")

if __name__ == "__main__":
    print("ZWO ASI Camera Test Suite")
    print("Make sure ASICamera2.dll is available in your system PATH or current directory")
    print("Press Ctrl+C to stop the test at any time\n")
    
    try:
        # Run basic camera test
        success = test_camera_basic()
        
        if success:
            print("\n✓ Basic camera test completed successfully!")
            
            # Run multiple camera test if requested
            if len(sys.argv) > 1 and sys.argv[1] == "--multiple":
                test_multiple_cameras()
        else:
            print("\n✗ Basic camera test failed!")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\nTest suite failed with error: {e}")
        sys.exit(1)
    
    print("\nTest completed!") 