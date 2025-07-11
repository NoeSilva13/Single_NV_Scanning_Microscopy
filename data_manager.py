import os
import time
import pandas as pd
import json

class DataManager:
    def __init__(self):
        """
        Initialize the DataManager.
        """
        pass
    
    def save_scan_data(self, scan_data, scan_params=None):
        """
        Save scan data to a CSV file in a daily folder.
        
        Args:
            scan_data: Dictionary containing 'image' (2D array), 'x_points', and 'y_points' arrays
            scan_params: Dictionary containing scan parameters (optional)
            
        Returns:
            str: The path to the saved file
        """
        # Create daily folder for data
        daily_folder = time.strftime("%m%d%y")
        if not os.path.exists(daily_folder):
            os.makedirs(daily_folder)
        
        # Get list of existing .csv files in the daily folder
        existing_files = [f for f in os.listdir(daily_folder) 
                        if f.startswith(daily_folder) and f.endswith('.csv')]
        
        # Determine the next sequence number (001, 002, etc.)
        seq_num = len(existing_files) + 1
        
        # Format the sequence number with leading zeros
        seq_str = f"{seq_num:03d}"
        
        # Create filename
        filename = os.path.join(daily_folder, f"{daily_folder}{seq_str}.csv")

        # Get the image and points from scan_data
        image = scan_data['image']
        x_points = scan_data['x_points']
        y_points = scan_data['y_points']
        
        # Create a DataFrame with the image data
        df = pd.DataFrame(image, index=y_points, columns=x_points)
        
        # Add a name to the index for the y-axis label
        df.index.name = r'y\x'
        
        # Write config and data to file
        with open(filename, 'w', encoding='utf-8', newline='') as f:
            # Write measurement date and time as the first line
            measurement_time = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"# Measurement Time: {measurement_time}\n")
            
            # Write scan parameters if provided
            if scan_params:
                params_json_str = json.dumps(scan_params, ensure_ascii=False, indent=2)
                f.write("# Scan Parameters (JSON):\n")
                for line in params_json_str.splitlines():
                    f.write(f"# {line}\n")
                f.write("#\n")  # Empty line to separate header from data
            
            # Write the data matrix
            df.to_csv(f, float_format='%.7f')
        
        return filename