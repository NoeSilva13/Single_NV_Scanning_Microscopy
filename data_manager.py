import os
import time
import pandas as pd

class DataManager:
    def __init__(self):
        """
        Initialize the DataManager.
        """
        pass

    def _next_index(self, daily_folder):
        """Next sequence number based on distinct scan basenames in the folder.

        Counts unique ``mmddyy###`` basenames across both ``.csv`` and ``.npz``
        outputs so that 2D scans (which write .csv + .npz) and 3D scans (which
        write only .npz) share a single, collision-free counter.
        """
        bases = set()
        for f in os.listdir(daily_folder):
            if f.startswith(daily_folder) and (f.endswith('.csv') or f.endswith('.npz')):
                bases.add(os.path.splitext(f)[0])
        return len(bases) + 1

    def next_base_path(self, ext=''):
        """Create today's folder and return the next sequential path.

        Args:
            ext: Optional extension (e.g. ``'.npz'``). If empty, returns the
                base path without extension.
        """
        daily_folder = time.strftime("%m%d%y")
        if not os.path.exists(daily_folder):
            os.makedirs(daily_folder)
        seq_str = f"{self._next_index(daily_folder):03d}"
        base = os.path.join(daily_folder, f"{daily_folder}{seq_str}")
        return base + ext if ext else base

    def save_scan_data(self, scan_data, scan_params):
        """
        Save scan data to a CSV file in a daily folder.
        
        Args:
            scan_data: Dictionary containing 'image' (2D array), 'x_points', 'y_points', 'scale_x', 'scale_y' arrays
            scan_params: Dictionary containing scan parameters (optional)
            
        Returns:
            str: The path to the saved file
        """
        # Create filename using the shared counter (counts both .csv and .npz)
        # so 2D and 3D scans never reuse the same sequence number.
        filename = self.next_base_path('.csv')

        # Get the image and points from scan_data
        image = scan_data['image']
        x_points = scan_data['x_points']
        y_points = scan_data['y_points']
        scale_x = scan_data.get('scale_x', None)
        scale_y = scan_data.get('scale_y', None)

        # Create a DataFrame with the image data
        df = pd.DataFrame(image, index=y_points, columns=x_points)

        # Add a name to the index for the y-axis label
        df.index.name = r'y\x'

        # Write config and data to file
        with open(filename, 'w', encoding='utf-8', newline='') as f:
            # Write measurement date and time as the first line
            measurement_time = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"# Measurement Time: {measurement_time}\n")
            
            # Write scale information 
            f.write(f"# Scale: {scale_x:.6f} x {scale_y:.6f} µm/pixel\n")
            
            # Write scan ranges
            x_range = scan_params['scan_range']['x']
            y_range = scan_params['scan_range']['y']
            f.write(f"# X Range: {x_range[0]:.6f} to {x_range[1]:.6f} um\n")
            f.write(f"# Y Range: {y_range[0]:.6f} to {y_range[1]:.6f} um\n")
                
            # Write resolutions
            x_res = scan_params['resolution']['x']
            y_res = scan_params['resolution']['y']
            f.write(f"# X Resolution: {x_res} pixels\n")
            f.write(f"# Y Resolution: {y_res} pixels\n")
                
            # Write dwell time
            dwell_time = scan_params['dwell_time']
            f.write(f"# Dwell Time: {dwell_time:.6f} s\n")

            # Write total scan time (acquisition duration) if available
            scan_time = scan_params.get('scan_time', None)
            if scan_time is not None:
                f.write(f"# Scan Time: {scan_time:.2f} s\n")
            
            # Write scan points information
            f.write(f"# X Points: {len(x_points)} points from {x_points[0]:.6f}um to {x_points[-1]:.6f}um\n")
            f.write(f"# Y Points: {len(y_points)} points from {y_points[0]:.6f}um to {y_points[-1]:.6f}um\n")
            
            f.write("#\n")  # Empty line to separate header from data
            
            # Write the data matrix
            df.to_csv(f, float_format='%.7f')
        
        return filename