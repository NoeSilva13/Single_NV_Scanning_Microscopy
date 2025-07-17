import cv2
import numpy as np
from . import pyPOACamera
from typing import Optional, List, Tuple, Any, Dict, Union


class POACameraController:
    """
    A class to control POA (Player One Astronomy) cameras with video mode support.
    """
    
    def __init__(self):
        """Initialize the camera controller."""
        self.camera_id = None
        self.camera_props = None
        self.is_connected = False
        self.is_streaming = False
        self.image_format = pyPOACamera.POAImgFormat.POA_RAW8
        self.buffer = None
        self.img_width = 0
        self.img_height = 0
        self.exposure = 50000  # microseconds
        self.gain = 300
        self._camera_list = []

    @staticmethod
    def list_available_cameras() -> List[Any]:
        """
        List all available POA cameras.
        
        Returns:
            List of camera property objects for all available cameras.
        """
        camera_count = pyPOACamera.GetCameraCount()
        cameras = []
        
        for i in range(camera_count):
            error, camera_props = pyPOACamera.GetCameraProperties(i)
            if error == pyPOACamera.POAErrors.POA_OK:
                cameras.append(camera_props)
                
        return cameras
    
    def connect(self, camera_index: int = 0, width: int = 640, height: int = 480) -> bool:
        """
        Connect to a camera by index.
        
        Args:
            camera_index: Index of the camera to connect to
            width: Desired image width
            height: Desired image height
            
        Returns:
            bool: True if connection was successful, False otherwise
        """
        # Get list of available cameras
        self._camera_list = self.list_available_cameras()
        if not self._camera_list:
            print("No cameras found.")
            return False
            
        if camera_index >= len(self._camera_list):
            print(f"Camera index {camera_index} out of range. Only {len(self._camera_list)} cameras found.")
            return False
            
        self.camera_props = self._camera_list[camera_index]
        self.camera_id = self.camera_props.cameraID
        
        # Open and initialize camera
        error = pyPOACamera.OpenCamera(self.camera_id)
        if error != pyPOACamera.POAErrors.POA_OK:
            print(f"Error opening camera: {pyPOACamera.GetErrorString(error)}")
            return False
            
        error = pyPOACamera.InitCamera(self.camera_id)
        if error != pyPOACamera.POAErrors.POA_OK:
            print(f"Error initializing camera: {pyPOACamera.GetErrorString(error)}")
            pyPOACamera.CloseCamera(self.camera_id)
            return False
            
        # Set image format
        error = pyPOACamera.SetImageFormat(self.camera_id, self.image_format)
        if error != pyPOACamera.POAErrors.POA_OK:
            print(f"Error setting image format: {pyPOACamera.GetErrorString(error)}")
            self.disconnect()
            return False
            
        # Set ROI (Region of Interest)
        pyPOACamera.SetImageStartPos(self.camera_id, 0, 0)
        pyPOACamera.SetImageSize(self.camera_id, width, height)
        pyPOACamera.SetImageBin(self.camera_id, 1)
        
        # Get final image dimensions
        error, self.img_width, self.img_height = pyPOACamera.GetImageSize(self.camera_id)
        
        # Prepare buffer
        img_size = pyPOACamera.ImageCalcSize(self.img_height, self.img_width, self.image_format)
        self.buffer = np.zeros(img_size, dtype=np.uint8)
        
        # Set initial exposure and gain
        self.set_exposure(self.exposure)
        self.set_gain(self.gain)
        
        self.is_connected = True
        return True
    
    def disconnect(self) -> None:
        """Disconnect from the camera and release resources."""
        if self.is_streaming:
            self.stop_stream()
            
        if self.camera_id is not None:
            pyPOACamera.CloseCamera(self.camera_id)
            self.camera_id = None
            
        self.is_connected = False
    
    def start_stream(self) -> bool:
        """Start the camera stream."""
        if not self.is_connected:
            print("Camera not connected")
            return False
            
        error = pyPOACamera.StartExposure(self.camera_id, False)  # False for video mode
        if error != pyPOACamera.POAErrors.POA_OK:
            print(f"Error starting exposure: {pyPOACamera.GetErrorString(error)}")
            return False
            
        self.is_streaming = True
        return True
    
    def stop_stream(self) -> None:
        """Stop the camera stream."""
        if self.is_streaming and self.camera_id is not None:
            pyPOACamera.StopExposure(self.camera_id)
            self.is_streaming = False
    
    def get_frame(self) -> Optional[np.ndarray]:
        """
        Get the current frame from the camera.
        
        Returns:
            numpy.ndarray: The current frame as a numpy array, or None if no frame is available
        """
        if not self.is_streaming or not self.is_connected or self.camera_id is None:
            return None
            
        # Check if image is ready
        error, is_ready = pyPOACamera.ImageReady(self.camera_id)
        if not is_ready:
            return None
            
        # Get image data
        error = pyPOACamera.GetImageData(self.camera_id, self.buffer, 1000)
        if error != pyPOACamera.POAErrors.POA_OK:
            print(f"Error getting image data: {pyPOACamera.GetErrorString(error)}")
            return None
            
        # Convert buffer to displayable format
        frame = pyPOACamera.ImageDataConvert(self.buffer, self.img_height, self.img_width, self.image_format)
        return frame
    
    def set_exposure(self, exposure_us: int) -> bool:
        """
        Set the camera exposure time.
        
        Args:
            exposure_us: Exposure time in microseconds
            
        Returns:
            bool: True if successful, False otherwise
        """
        self.exposure = max(1000, min(1000000, exposure_us))  # Clamp between 1ms and 1s
        if self.is_connected and self.camera_id is not None:
            error = pyPOACamera.SetExp(self.camera_id, self.exposure, False)
            return error == pyPOACamera.POAErrors.POA_OK
        return False
    
    def get_exposure(self) -> int:
        """
        Get the current exposure time.
        
        Returns:
            int: Current exposure time in microseconds
        """
        if self.is_connected and self.camera_id is not None:
            try:
                error, actual_exposure, auto = pyPOACamera.GetExp(self.camera_id)
                if error == pyPOACamera.POAErrors.POA_OK:
                    return actual_exposure
            except Exception as e:
                print(f"Error getting actual exposure: {e}")
        return self.exposure
    
    def set_gain(self, gain: int) -> bool:
        """
        Set the camera gain.
        
        Args:
            gain: Gain value (0-1000)
            
        Returns:
            bool: True if successful, False otherwise
        """
        self.gain = max(0, min(1000, gain))  # Clamp between 0 and 1000
        if self.is_connected and self.camera_id is not None:
            error = pyPOACamera.SetGain(self.camera_id, self.gain, False)
            return error == pyPOACamera.POAErrors.POA_OK
        return False
    
    def get_gain(self) -> int:
        """
        Get the current gain value.
        
        Returns:
            int: Current gain value
        """
        if self.is_connected and self.camera_id is not None:
            try:
                error, actual_gain, auto = pyPOACamera.GetGain(self.camera_id)
                if error == pyPOACamera.POAErrors.POA_OK:
                    return actual_gain
            except Exception as e:
                print(f"Error getting actual gain: {e}")
        return self.gain
    
    def get_image_dimensions(self) -> Tuple[int, int]:
        """
        Get the current image dimensions.
        
        Returns:
            tuple: (width, height) of the image
        """
        return self.img_width, self.img_height
    
    def __del__(self):
        """Ensure resources are cleaned up when the object is destroyed."""
        self.disconnect()


def main():
    """Example usage of the POACameraController class."""
    import sys
    
    # Create camera controller
    camera = POACameraController()
    
    # List available cameras
    cameras = camera.list_available_cameras()
    if not cameras:
        print("No cameras found. Exiting...")
        return
        
    print(f"Found {len(cameras)} camera(s):")
    for i, cam in enumerate(cameras):
        print(f"{i}: {cam.cameraModelName} (ID: {cam.cameraID})")
    
    # Connect to the first camera
    if not camera.connect(camera_index=0):
        print("Failed to connect to camera. Exiting...")
        return
    
    print(f"Connected to camera: {camera.camera_props.cameraModelName}")
    print(f"Image size: {camera.img_width}x{camera.img_height}")
    
    # Start the stream
    if not camera.start_stream():
        print("Failed to start stream. Exiting...")
        camera.disconnect()
        return
    
    print("\nCamera started. Press 'q' to quit.")
    print("Press 'i' to increase exposure, 'd' to decrease exposure")
    print("Press 'g' to increase gain, 'h' to decrease gain")
    
    try:
        while True:
            frame = camera.get_frame()
            if frame is not None:
                # Add text overlay with settings
                cv2.putText(frame, f"Exp: {camera.get_exposure()/1000:.0f}ms  Gain: {camera.get_gain()}", 
                          (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                # Display the frame
                cv2.imshow('Camera - Press q to quit', frame)
            
            # Handle key presses
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):  # Quit
                break
            elif key == ord('i'):  # Increase exposure
                camera.set_exposure(camera.get_exposure() + 10000)
                print(f"Exposure: {camera.get_exposure()/1000:.0f}ms")
            elif key == ord('d'):  # Decrease exposure
                camera.set_exposure(camera.get_exposure() - 10000)
                print(f"Exposure: {camera.get_exposure()/1000:.0f}ms")
            elif key == ord('g'):  # Increase gain
                camera.set_gain(camera.get_gain() + 10)
                print(f"Gain: {camera.get_gain()}")
            elif key == ord('h'):  # Decrease gain
                camera.set_gain(camera.get_gain() - 10)
                print(f"Gain: {camera.get_gain()}")
    
    except KeyboardInterrupt:
        print("\nStopping camera...")
    
    finally:
        # Cleanup
        camera.disconnect()
        cv2.destroyAllWindows()
        print("\nCamera released.")


if __name__ == "__main__":
    main()
