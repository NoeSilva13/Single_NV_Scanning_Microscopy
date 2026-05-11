"""
USB Webcam Controller for compatibility with the Napari Scanning SPD application.

This module provides a wrapper around OpenCV's VideoCapture to match the interface
of POACameraController and ZWOCameraController for seamless integration.
"""

import numpy as np
from typing import Optional, Tuple

try:
    import cv2
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False
    print("Warning: opencv-python is not installed. USBWebcamController will not function.")


class USBWebcamController:
    """
    A class to control generic USB webcams via OpenCV VideoCapture.
    Compatible interface with POACameraController and ZWOCameraController.
    """

    def __init__(self):
        """Initialize the webcam controller."""
        self.cap = None
        self.is_connected = False
        self.is_streaming = False
        self.img_width = 0
        self.img_height = 0
        self.exposure = 50000   # microseconds (stored internally in µs)
        self.gain = 0

    @staticmethod
    def list_available_cameras() -> list:
        """
        List all available USB webcams by probing indices 0–9.

        Returns:
            List of name strings for each available camera index.
        """
        if not _CV2_AVAILABLE:
            return []

        available = []
        for i in range(10):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap is not None and cap.isOpened():
                available.append(f"Webcam {i}")
                cap.release()
        return available

    def connect(self, camera_index: int = 0, width: int = 640, height: int = 480) -> bool:
        """
        Connect to a USB webcam by index.

        Args:
            camera_index: Index of the camera to connect to
            width: Desired image width
            height: Desired image height

        Returns:
            bool: True if connection was successful, False otherwise
        """
        if not _CV2_AVAILABLE:
            print("opencv-python is not installed. Cannot connect to USB webcam.")
            return False

        try:
            self.cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                print(f"Could not open webcam at index {camera_index}.")
                self.cap = None
                return False

            # Request desired resolution
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

            # Read back the actual resolution the driver settled on
            self.img_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.img_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            # Apply initial exposure and gain (best-effort; many webcams ignore these)
            self._apply_exposure(self.exposure)
            self._apply_gain(self.gain)

            self.is_connected = True
            print(f"USB webcam {camera_index} connected. "
                  f"Image size: {self.img_width}x{self.img_height}")
            return True

        except Exception as e:
            print(f"Error connecting to USB webcam: {e}")
            if self.cap is not None:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None
            return False

    def disconnect(self) -> None:
        """Disconnect from the webcam and release resources."""
        self.is_streaming = False
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception as e:
                print(f"Error releasing webcam: {e}")
            finally:
                self.cap = None
        self.is_connected = False
        print("USB webcam disconnected.")

    def start_stream(self) -> bool:
        """Mark the webcam stream as active (VideoCapture is always live once opened)."""
        if not self.is_connected or self.cap is None:
            print("Webcam not connected.")
            return False
        self.is_streaming = True
        print("USB webcam stream started.")
        return True

    def stop_stream(self) -> None:
        """Mark the webcam stream as inactive."""
        self.is_streaming = False
        print("USB webcam stream stopped.")

    def get_frame(self) -> Optional[np.ndarray]:
        """
        Grab the current frame from the webcam.

        Returns:
            numpy.ndarray: Frame as an RGB uint8 array of shape (H, W, 3),
                           or None if no frame is available.
        """
        if not self.is_streaming or not self.is_connected or self.cap is None:
            return None

        try:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                return None
            # OpenCV returns BGR; convert to RGB for display in Napari
            return frame[:, :, ::-1].copy()
        except Exception as e:
            print(f"Error reading webcam frame: {e}")
            return None

    # ------------------------------------------------------------------
    # Exposure helpers
    # ------------------------------------------------------------------

    def _apply_exposure(self, exposure_us: int) -> None:
        """Push exposure to the driver. Converts µs → ms; silently ignores failures."""
        if self.cap is None or not self.cap.isOpened():
            return
        try:
            # Disable auto-exposure first so the manual value takes effect
            self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # 0.25 = manual on many backends
            exposure_ms = exposure_us / 1000.0
            self.cap.set(cv2.CAP_PROP_EXPOSURE, exposure_ms)
        except Exception:
            pass  # Webcam drivers routinely ignore unsupported properties

    def set_exposure(self, exposure_us: int) -> bool:
        """
        Set the camera exposure time.

        Args:
            exposure_us: Exposure time in microseconds

        Returns:
            bool: True if the value was stored (hardware application is best-effort)
        """
        self.exposure = max(100, exposure_us)
        if self.is_connected:
            self._apply_exposure(self.exposure)
        return True

    def get_exposure(self) -> int:
        """
        Get the current exposure time in microseconds.

        Returns:
            int: Stored exposure value in microseconds
        """
        if self.is_connected and self.cap is not None:
            try:
                val_ms = self.cap.get(cv2.CAP_PROP_EXPOSURE)
                if val_ms > 0:
                    self.exposure = int(val_ms * 1000)
            except Exception:
                pass
        return self.exposure

    # ------------------------------------------------------------------
    # Gain helpers
    # ------------------------------------------------------------------

    def _apply_gain(self, gain: int) -> None:
        """Push gain to the driver; silently ignores failures."""
        if self.cap is None or not self.cap.isOpened():
            return
        try:
            self.cap.set(cv2.CAP_PROP_GAIN, gain)
        except Exception:
            pass

    def set_gain(self, gain: int) -> bool:
        """
        Set the camera gain.

        Args:
            gain: Gain value (clamped to 0–255 for generic webcam drivers)

        Returns:
            bool: True if the value was stored (hardware application is best-effort)
        """
        self.gain = max(0, min(255, gain))
        if self.is_connected:
            self._apply_gain(self.gain)
        return True

    def get_gain(self) -> int:
        """
        Get the current gain value.

        Returns:
            int: Stored gain value
        """
        if self.is_connected and self.cap is not None:
            try:
                val = self.cap.get(cv2.CAP_PROP_GAIN)
                if val >= 0:
                    self.gain = int(val)
            except Exception:
                pass
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
    """Example usage of the USBWebcamController class."""
    print("USB Webcam Controller Test")

    cameras = USBWebcamController.list_available_cameras()
    print(f"Available cameras: {cameras}")

    if not cameras:
        print("No USB webcams found.")
        return

    controller = USBWebcamController()
    if not controller.connect(0, 640, 480):
        print("Failed to connect to webcam.")
        return

    print("Webcam connected successfully!")
    if controller.start_stream():
        print("Stream started.")
        import time
        for i in range(5):
            frame = controller.get_frame()
            if frame is not None:
                print(f"Frame {i + 1}: shape={frame.shape}, mean={frame.mean():.1f}")
            else:
                print(f"Frame {i + 1}: No frame received.")
            time.sleep(0.1)
        controller.stop_stream()

    controller.disconnect()


if __name__ == "__main__":
    main()
