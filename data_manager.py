import os
import time
import pandas as pd

class DataManager:
    def __init__(self):
        """
        Initialize the DataManager.
        """
        pass
    
    def save_scan_data(self, scan_data):
        """
        Save scan data to a CSV file in a daily folder.
        
        Args:
            scan_data: The scan data to be saved (can be a dictionary, list, or pandas DataFrame)
            
        Returns:
            str: The path to the saved file
        """
        # Create daily folder for data
        daily_folder = time.strftime("%m%d%y")
        if not os.path.exists(daily_folder):
            os.makedirs(daily_folder)
        
        # Save scan data in daily folder
        timestamp = time.strftime("%H%M%S")
        filename = os.path.join(daily_folder, f"scan_data_{timestamp}.csv")
        
        # Convert data to DataFrame if it's not already
        if not isinstance(scan_data, pd.DataFrame):
            df = pd.DataFrame(scan_data)
        else:
            df = scan_data
            
        # Save the data
        df.to_csv(filename, index=False)
        print(f"Scan data saved to {filename}")
        
        return filename
