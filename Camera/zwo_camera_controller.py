"""
ZWO Camera Controller for compatibility with the Napari Scanning SPD application.

This module provides a wrapper around the zwo_camera module to match
the interface of POACameraController for seamless integration.
"""

import numpy as np
import time
from typing import Optional, Tuple
from . import zwo_camera


class ZWOCameraController:
    """
    A class to control ZWO ASI cameras with video mode support.
    Compatible interface with POACameraController.
    """
    
    def __init__(self):
        """Initialize the camera controller."""
        self.camera = None
        self.is_connected = False
        self.is_streaming = False
        self.img_width = 0
        self.img_height = 0
        self.exposure = 50000  # microseconds
        self.gain = 300
        self._original_roi = None  # Store original ROI for restoration
        
    @staticmethod
    def list_available_cameras():
        """
        List all available ZWO cameras.
        
        Returns:
            List of camera names for all available cameras.
        """
        try:
            return zwo_camera.list_cameras()
        except Exception as e:
            print(f"Error listing cameras: {e}")
            return []
    
    def connect(self, camera_index: int = 0, width: int = 640, height: int = 480) -> bool:
        """
        Connect to a ZWO camera by index.
        
        Args:
            camera_index: Index of the camera to connect to
            width: Desired image width
            height: Desired image height
            
        Returns:
            bool: True if connection was successful, False otherwise
        """
        try:
            # Check if cameras are available
            num_cameras = zwo_camera.get_num_cameras()
            if num_cameras == 0:
                print("No ZWO cameras found.")
                return False
                
            if camera_index >= num_cameras:
                print(f"Camera index {camera_index} out of range. Only {num_cameras} cameras found.")
                return False
            
            # Initialize camera
            self.camera = zwo_camera.Camera(camera_index)
            
            # Get camera info
            cam_info = self.camera.get_camera_property()
            print(f"Connected to: {cam_info['Name']}")
            
            # Store original ROI for restoration later
            self._original_roi = self.camera.get_roi()
            
            # Set desired ROI (constrain to camera limits)
            max_width = cam_info['MaxWidth']
            max_height = cam_info['MaxHeight']
            
            # Ensure width and height are within camera limits and meet requirements
            width = min(width, max_width)
            height = min(height, max_height)
            
            # Ensure width is multiple of 8 and height is multiple of 2 (ZWO requirement)
            width = (width // 8) * 8
            height = (height // 2) * 2
            
            # Set ROI
            self.camera.set_roi(width=width, height=height)
            
            # Get actual image dimensions
            roi = self.camera.get_roi()
            self.img_width = roi[2]  # width
            self.img_height = roi[3]  # height
            
            # Set image type to RGB24 for color images (since this is a color camera)
            self.camera.set_image_type(zwo_camera.ASI_IMG_RGB24)
            
            # Set initial exposure and gain
            self.set_exposure(self.exposure)
            self.set_gain(self.gain)
            
            self.is_connected = True
            print(f"Camera connected successfully. Image size: {self.img_width}x{self.img_height}")
            return True
            
        except Exception as e:
            print(f"Error connecting to camera: {e}")
            if self.camera:
                try:
                    self.camera.close()
                except:
                    pass
                self.camera = None
            return False
    
    def disconnect(self) -> None:
        """Disconnect from the camera and release resources."""
        if self.is_streaming:
            self.stop_stream()
            
        if self.camera:
            try:
                # Restore original ROI if we changed it
                if self._original_roi:
                    self.camera.set_roi_start_position(self._original_roi[0], self._original_roi[1])
                    self.camera.set_roi_format(self._original_roi[2], self._original_roi[3], 
                                             self.camera.get_roi_format()[2], 
                                             self.camera.get_roi_format()[3])
                
                self.camera.close()
            except Exception as e:
                print(f"Error closing camera: {e}")
            finally:
                self.camera = None
                
        self.is_connected = False
        print("ZWO camera disconnected")
    
    def start_stream(self) -> bool:
        """Start the camera video stream."""
        if not self.is_connected or not self.camera:
            print("Camera not connected")
            return False
            
        try:
            self.camera.start_video_capture()
            self.is_streaming = True
            print("ZWO camera video stream started")
            return True
        except Exception as e:
            print(f"Error starting video stream: {e}")
            return False
    
    def stop_stream(self) -> None:
        """Stop the camera video stream."""
        if self.is_streaming and self.camera:
            try:
                self.camera.stop_video_capture()
                print("ZWO camera video stream stopped")
            except Exception as e:
                print(f"Error stopping video stream: {e}")
            finally:
                self.is_streaming = False
    
    def get_frame(self) -> Optional[np.ndarray]:
        """
        Get the current frame from the camera.
        
        Returns:
            numpy.ndarray: The current frame as a numpy array, or None if no frame is available
        """
        if not self.is_streaming or not self.is_connected or not self.camera:
            return None
            
        try:
            # Use a reasonable timeout (1 second)
            timeout_ms = 1000
            frame = self.camera.capture_video_frame(timeout=timeout_ms)
            return frame
        except zwo_camera.ZWO_Error as e:
            # Handle timeout gracefully
            if "timeout" in str(e).lower():
                return None
            print(f"Error getting frame: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error getting frame: {e}")
            return None
    
    def set_exposure(self, exposure_us: int) -> bool:
        """
        Set the camera exposure time.
        
        Args:
            exposure_us: Exposure time in microseconds
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Store the exposure value
        self.exposure = max(1000, min(10000000, exposure_us))  # Clamp between 1ms and 10s
        
        if self.is_connected and self.camera:
            try:
                self.camera.set_control_value(zwo_camera.ASI_EXPOSURE, self.exposure, auto=False)
                return True
            except Exception as e:
                print(f"Error setting exposure: {e}")
                return False
        return False
    
    def get_exposure(self) -> int:
        """
        Get the current exposure time.
        
        Returns:
            int: Current exposure time in microseconds
        """
        if self.is_connected and self.camera:
            try:
                exposure_value = self.camera.get_control_value(zwo_camera.ASI_EXPOSURE)[0]
                self.exposure = exposure_value
                return exposure_value
            except Exception as e:
                print(f"Error getting exposure: {e}")
        return self.exposure
    
    def set_gain(self, gain: int) -> bool:
        """
        Set the camera gain.
        
        Args:
            gain: Gain value (typically 0-600 for ZWO cameras)
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Get gain limits from camera if connected
        if self.is_connected and self.camera:
            try:
                controls = self.camera.get_controls()
                if 'Gain' in controls:
                    max_gain = controls['Gain']['MaxValue']
                    min_gain = controls['Gain']['MinValue']
                    self.gain = max(min_gain, min(max_gain, gain))
                else:
                    self.gain = max(0, min(600, gain))  # Default ZWO gain range
                
                self.camera.set_control_value(zwo_camera.ASI_GAIN, self.gain, auto=False)
                return True
            except Exception as e:
                print(f"Error setting gain: {e}")
                return False
        else:
            # Just store the value if not connected
            self.gain = max(0, min(600, gain))
        return False
    
    def get_gain(self) -> int:
        """
        Get the current gain value.
        
        Returns:
            int: Current gain value
        """
        if self.is_connected and self.camera:
            try:
                gain_value = self.camera.get_control_value(zwo_camera.ASI_GAIN)[0]
                self.gain = gain_value
                return gain_value
            except Exception as e:
                print(f"Error getting gain: {e}")
        return self.gain
    
    def get_image_dimensions(self) -> Tuple[int, int]:
        """
        Get the current image dimensions.
        
        Returns:
            Tuple[int, int]: (width, height) of the current image
        """
        return (self.img_width, self.img_height)
    
    def __del__(self):
        """Cleanup when object is destroyed."""
        if self.is_connected:
            self.disconnect()


def main():
    """Example usage of the ZWOCameraController class."""
    print("ZWO Camera Controller Test")
    
    # List available cameras
    cameras = ZWOCameraController.list_available_cameras()
    print(f"Available cameras: {cameras}")
    
    if cameras:
        # Test camera connection
        controller = ZWOCameraController()
        if controller.connect(0, 800, 600):
            print("Camera connected successfully!")
            
            # Test video mode
            if controller.start_stream():
                print("Video stream started")
                
                # Capture a few frames
                for i in range(5):
                    frame = controller.get_frame()
                    if frame is not None:
                        print(f"Frame {i+1}: {frame.shape}, mean: {frame.mean():.1f}")
                    else:
                        print(f"Frame {i+1}: No frame received")
                    time.sleep(0.1)
                
                controller.stop_stream()
            
            controller.disconnect()
        else:
            print("Failed to connect to camera")
    else:
        print("No cameras found")


if __name__ == "__main__":
    main() 