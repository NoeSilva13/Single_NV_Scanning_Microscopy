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
    
    def save_scan_data(self, scan_data):
        """
        Save scan data to a CSV file in a daily folder.
        
        Args:
            scan_data: The scan data to be saved (can be a dictionary, list, or pandas DataFrame)
            
        Returns:
            str: The path to the saved file
        """
        # Load configuration
        with open("config_template.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        
        # Create daily folder for data
        daily_folder = time.strftime("%m%d%y")
        if not os.path.exists(daily_folder):
            os.makedirs(daily_folder)
        
        # Get list of existing files in the daily folder
        existing_files = [f for f in os.listdir(daily_folder) if f.startswith(daily_folder)]
        
        # Determine the next sequence number (001, 002, etc.)
        seq_num = len(existing_files) + 1
        
        # Format the sequence number with leading zeros
        seq_str = f"{seq_num:03d}"
        
        # Save scan data in daily folder with sequence number
        timestamp = time.strftime("%H%M%S")
        filename = os.path.join(daily_folder, f"{daily_folder}{seq_str}_scan{timestamp}.csv")

        # Convert data to DataFrame if it's not already
        if not isinstance(scan_data, pd.DataFrame):
            df = pd.DataFrame(scan_data)
        else:
            df = scan_data
            
        # Write config as a single JSON string in a comment block
        with open(filename, 'w', encoding='utf-8', newline='') as f:
            config_json_str = json.dumps(config, ensure_ascii=False, indent=2)
            f.write("# Experiment Configuration (JSON):\n")
            for line in config_json_str.splitlines():
                f.write(f"# {line}\n")
            f.write("#\n")  # Empty line to separate header from data
            df.to_csv(f, index=False)
        
        return filename
    