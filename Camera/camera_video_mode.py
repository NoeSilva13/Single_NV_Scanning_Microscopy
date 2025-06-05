import cv2
import numpy as np
import pyPOACamera

def list_available_cameras():
    """List all available POA cameras and return the first one found."""
    camera_count = pyPOACamera.GetCameraCount()
    print(f"Found {camera_count} camera(s)")
    
    if camera_count == 0:
        print("No cameras found. Please check the connection and try again.")
        return None
    
    for i in range(camera_count):
        error, camera_props = pyPOACamera.GetCameraProperties(i)
        if error == pyPOACamera.POAErrors.POA_OK:
            print(f"\nCamera {i}:")
            print(f"  Model: {camera_props.cameraModelName}")
            print(f"  ID: {camera_props.cameraID}")
            print(f"  Max Resolution: {camera_props.maxWidth}x{camera_props.maxHeight}")
            print(f"  Is Color: {bool(camera_props.isColorCamera)}")
            
            # Try to open the camera to check if it's accessible
            open_error = pyPOACamera.OpenCamera(camera_props.cameraID)
            if open_error == pyPOACamera.POAErrors.POA_OK:
                pyPOACamera.CloseCamera(camera_props.cameraID)  # Close it for now
                return camera_props
            else:
                print(f"  Status: In use or error opening: {pyPOACamera.GetErrorString(open_error)}")
    
    print("\nNo available cameras found or all cameras are in use.")
    return None

def main():
    # List and select camera
    camera_props = list_available_cameras()
    if not camera_props:
        return
    
    camera_id = camera_props.cameraID
    print(f"\nUsing camera: {camera_props.cameraModelName}")
    
    try:
        # Open and initialize camera
        error = pyPOACamera.OpenCamera(camera_id)
        if error != pyPOACamera.POAErrors.POA_OK:
            print(f"Error opening camera: {pyPOACamera.GetErrorString(error)}")
            return

        error = pyPOACamera.InitCamera(camera_id)
        if error != pyPOACamera.POAErrors.POA_OK:
            print(f"Error initializing camera: {pyPOACamera.GetErrorString(error)}")
            pyPOACamera.CloseCamera(camera_id)
            return

        # Set image format
        image_format = pyPOACamera.POAImgFormat.POA_RAW8
        error = pyPOACamera.SetImageFormat(camera_id, image_format)
        if error != pyPOACamera.POAErrors.POA_OK:
            print(f"Error setting image format: {pyPOACamera.GetErrorString(error)}")
            pyPOACamera.CloseCamera(camera_id)
            return

        # Set ROI (Region of Interest)
        width, height = 640, 480  # Reduced resolution
        pyPOACamera.SetImageStartPos(camera_id, 0, 0)
        pyPOACamera.SetImageSize(camera_id, width, height)
        pyPOACamera.SetImageBin(camera_id, 1)

        # Camera settings
        pyPOACamera.SetExp(camera_id, 50000, False)  # 50ms exposure
        pyPOACamera.SetGain(camera_id, 300, False)   # Higher gain

        # Get final image dimensions
        error, img_width, img_height = pyPOACamera.GetImageSize(camera_id)
        print(f"Image size: {img_width}x{img_height}")

        # Prepare buffer
        img_size = pyPOACamera.ImageCalcSize(img_height, img_width, image_format)
        buffer = np.zeros(img_size, dtype=np.uint8)

        # Start video mode
        error = pyPOACamera.StartExposure(camera_id, False)  # False for video mode
        if error != pyPOACamera.POAErrors.POA_OK:
            print(f"Error starting exposure: {pyPOACamera.GetErrorString(error)}")
            pyPOACamera.CloseCamera(camera_id)
            return

        print("\nCamera started. Press 'q' to quit.")
        print("Press 'i' to increase exposure, 'd' to decrease exposure")
        print("Press 'g' to increase gain, 'h' to decrease gain")

        exposure = 50000  # Initial exposure in microseconds
        gain = 300       # Initial gain
        
        # Main loop
        while True:
            # Check if image is ready
            error, is_ready = pyPOACamera.ImageReady(camera_id)
            if not is_ready:
                continue
                
            # Get image data
            error = pyPOACamera.GetImageData(camera_id, buffer, 1000)
            if error != pyPOACamera.POAErrors.POA_OK:
                print(f"Error getting image data: {pyPOACamera.GetErrorString(error)}")
                break
                
            # Convert buffer to displayable format
            frame = pyPOACamera.ImageDataConvert(buffer, img_height, img_width, image_format)
            
            # Add text overlay with settings
            cv2.putText(frame, f"Exp: {exposure/1000:.0f}ms  Gain: {gain}", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # Display the frame
            cv2.imshow('Camera - Press q to quit', frame)
            
            # Handle key presses
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):  # Quit
                break
            elif key == ord('i'):  # Increase exposure
                exposure = min(1000000, exposure + 10000)  # Max 1 second
                pyPOACamera.SetExp(camera_id, exposure, False)
                print(f"Exposure: {exposure/1000:.0f}ms")
            elif key == ord('d'):  # Decrease exposure
                exposure = max(1000, exposure - 10000)  # Min 1ms
                pyPOACamera.SetExp(camera_id, exposure, False)
                print(f"Exposure: {exposure/1000:.0f}ms")
            elif key == ord('g'):  # Increase gain
                gain = min(1000, gain + 10)
                pyPOACamera.SetGain(camera_id, gain, False)
                print(f"Gain: {gain}")
            elif key == ord('h'):  # Decrease gain
                gain = max(0, gain - 10)
                pyPOACamera.SetGain(camera_id, gain, False)
                print(f"Gain: {gain}")
    
    except KeyboardInterrupt:
        print("\nStopping camera...")
    
    finally:
        # Cleanup
        try:
            pyPOACamera.StopExposure(camera_id)
            pyPOACamera.CloseCamera(camera_id)
            cv2.destroyAllWindows()
            print("\nCamera released.")
        except Exception as e:
            print(f"Error during cleanup: {str(e)}")

if __name__ == "__main__":
    main()
