#!/usr/bin/env python3
"""
Test script for camera integration in the Napari Scanning SPD application.
This script tests both POA and ZWO camera integration.
"""

import sys
import napari
from widgets.camera_controls import create_camera_control_widget
from napari.utils.notifications import show_info

def test_camera_integration():
    """Test camera integration with napari viewer"""
    print("Testing Camera Integration")
    print("-" * 30)
    
    # Create napari viewer
    viewer = napari.Viewer(title="Camera Integration Test")
    
    try:
        # Create camera control widget
        camera_widget = create_camera_control_widget(viewer)
        
        # Add the widget to the viewer
        viewer.window.add_dock_widget(camera_widget, name="Camera Control", area="right")
        
        # Check available cameras
        from Camera import POACameraController, ZWOCameraController
        
        # Test POA cameras
        try:
            poa_cameras = POACameraController.list_available_cameras()
            print(f"POA cameras found: {len(poa_cameras)}")
            for i, cam in enumerate(poa_cameras):
                print(f"  {i}: {cam.cameraName if hasattr(cam, 'cameraName') else 'POA Camera'}")
        except Exception as e:
            print(f"POA camera error: {e}")
        
        # Test ZWO cameras
        try:
            zwo_cameras = ZWOCameraController.list_available_cameras()
            print(f"ZWO cameras found: {len(zwo_cameras)}")
            for i, cam in enumerate(zwo_cameras):
                print(f"  {i}: {cam}")
        except Exception as e:
            print(f"ZWO camera error: {e}")
        
        # Show instructions
        show_info("""
        🎥 Camera Integration Test
        
        Instructions:
        1. Select camera type from dropdown (POA or ZWO)
        2. Click 'Camera Live' to start live view
        3. Adjust exposure and gain sliders
        4. Click 'Single Shot' to capture image
        5. Click 'Stop Camera' to end live view
        
        Both camera types should work with the same interface!
        """)
        
        print("\n✅ Camera integration test setup complete!")
        print("Use the GUI to test camera functionality")
        
        # Run napari
        napari.run()
        
    except Exception as e:
        print(f"❌ Error setting up camera integration test: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def main():
    """Main function"""
    print("Camera Integration Test for Napari Scanning SPD")
    print("=" * 50)
    
    try:
        success = test_camera_integration()
        if success:
            print("Test completed successfully!")
        else:
            print("Test failed!")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"Test failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 