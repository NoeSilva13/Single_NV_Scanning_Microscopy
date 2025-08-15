import os
import time
import json
import pandas as pd
import numpy as np

class ODMRDataManager:
    def __init__(self):
        """
        Initialize the ODMR Data Manager.
        """
        pass
    
    def save_odmr_data(self, frequencies, count_rates, parameters):
        """
        Save ODMR data to a CSV file in a daily folder with experiment-specific subfolder.
        
        Args:
            frequencies: List of microwave frequencies (Hz)
            count_rates: List of corresponding count rates (Hz)
            parameters: Dictionary containing measurement parameters
            
        Returns:
            str: The path to the saved file
        """
        # Create daily folder for data
        daily_folder = time.strftime("%m%d%y")
        if not os.path.exists(daily_folder):
            os.makedirs(daily_folder)
        
        # Create ODMR subfolder
        odmr_folder = os.path.join(daily_folder, "ODMR")
        if not os.path.exists(odmr_folder):
            os.makedirs(odmr_folder)
        
        # Get list of existing .csv files in the ODMR folder
        existing_files = [f for f in os.listdir(odmr_folder) 
                        if f.startswith(daily_folder) and f.endswith('.csv')]
        
        # Determine the next sequence number (001, 002, etc.)
        seq_num = len(existing_files) + 1
        
        # Format the sequence number with leading zeros
        seq_str = f"{seq_num:03d}"
        
        # Create filename
        filename = os.path.join(odmr_folder, f"{daily_folder}{seq_str}_ODMR.csv")

        # Create a DataFrame with the data
        df = pd.DataFrame({
            'Frequency_Hz': frequencies,
            'Frequency_GHz': np.array(frequencies) / 1e9,
            'Count_Rate_Hz': count_rates
        })

        # Write data to file
        with open(filename, 'w', encoding='utf-8', newline='') as f:
            # Write measurement date and time as the first line
            measurement_time = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"# Measurement Time: {measurement_time}\n")
            f.write(f"# Experiment Type: ODMR\n")
            
            # Write frequency range
            if len(frequencies) > 0:
                f.write(f"# Frequency Range: {min(frequencies)/1e9:.6f} to {max(frequencies)/1e9:.6f} GHz\n")
                f.write(f"# Number of Points: {len(frequencies)}\n")
            
            # Write measurement parameters
            for key, value in parameters.items():
                if key != 'mw_frequencies':  # Skip the frequencies list as it's in the data
                    f.write(f"# {key}: {value}\n")
            
            f.write("#\n")  # Empty line to separate header from data
            
            # Write the data
            df.to_csv(f, index=False, float_format='%.7f')
        
        return filename
    
    def save_rabi_data(self, durations, count_rates, parameters):
        """
        Save Rabi oscillation data to a CSV file in a daily folder with experiment-specific subfolder.
        
        Args:
            durations: List of MW pulse durations (ns)
            count_rates: List of corresponding count rates (Hz)
            parameters: Dictionary containing measurement parameters
            
        Returns:
            str: The path to the saved file
        """
        # Create daily folder for data
        daily_folder = time.strftime("%m%d%y")
        if not os.path.exists(daily_folder):
            os.makedirs(daily_folder)
        
        # Create Rabi subfolder
        rabi_folder = os.path.join(daily_folder, "Rabi")
        if not os.path.exists(rabi_folder):
            os.makedirs(rabi_folder)
        
        # Get list of existing .csv files in the Rabi folder
        existing_files = [f for f in os.listdir(rabi_folder) 
                        if f.startswith(daily_folder) and f.endswith('.csv')]
        
        # Determine the next sequence number (001, 002, etc.)
        seq_num = len(existing_files) + 1
        
        # Format the sequence number with leading zeros
        seq_str = f"{seq_num:03d}"
        
        # Create filename
        filename = os.path.join(rabi_folder, f"{daily_folder}{seq_str}_Rabi.csv")

        # Create a DataFrame with the data
        df = pd.DataFrame({
            'Duration_ns': durations,
            'Count_Rate_Hz': count_rates
        })

        # Write data to file
        with open(filename, 'w', encoding='utf-8', newline='') as f:
            # Write measurement date and time as the first line
            measurement_time = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"# Measurement Time: {measurement_time}\n")
            f.write(f"# Experiment Type: Rabi Oscillation\n")
            
            # Write duration range
            if len(durations) > 0:
                f.write(f"# Duration Range: {min(durations)} to {max(durations)} ns\n")
                f.write(f"# Number of Points: {len(durations)}\n")
            
            # Write measurement parameters
            for key, value in parameters.items():
                if key != 'mw_durations':  # Skip the durations list as it's in the data
                    f.write(f"# {key}: {value}\n")
            
            f.write("#\n")  # Empty line to separate header from data
            
            # Write the data
            df.to_csv(f, index=False, float_format='%.7f')
        
        return filename
    
    def save_t1_data(self, delays, count_rates, parameters):
        """
        Save T1 decay data to a CSV file in a daily folder with experiment-specific subfolder.
        
        Args:
            delays: List of delay times (ns)
            count_rates: List of corresponding count rates (Hz)
            parameters: Dictionary containing measurement parameters
            
        Returns:
            str: The path to the saved file
        """
        # Create daily folder for data
        daily_folder = time.strftime("%m%d%y")
        if not os.path.exists(daily_folder):
            os.makedirs(daily_folder)
        
        # Create T1 subfolder
        t1_folder = os.path.join(daily_folder, "T1")
        if not os.path.exists(t1_folder):
            os.makedirs(t1_folder)
        
        # Get list of existing .csv files in the T1 folder
        existing_files = [f for f in os.listdir(t1_folder) 
                        if f.startswith(daily_folder) and f.endswith('.csv')]
        
        # Determine the next sequence number (001, 002, etc.)
        seq_num = len(existing_files) + 1
        
        # Format the sequence number with leading zeros
        seq_str = f"{seq_num:03d}"
        
        # Create filename
        filename = os.path.join(t1_folder, f"{daily_folder}{seq_str}_T1.csv")

        # Create a DataFrame with the data
        df = pd.DataFrame({
            'Delay_ns': delays,
            'Delay_us': np.array(delays) / 1000,
            'Count_Rate_Hz': count_rates
        })

        # Write data to file
        with open(filename, 'w', encoding='utf-8', newline='') as f:
            # Write measurement date and time as the first line
            measurement_time = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"# Measurement Time: {measurement_time}\n")
            f.write(f"# Experiment Type: T1 Decay\n")
            
            # Write delay range
            if len(delays) > 0:
                f.write(f"# Delay Range: {min(delays)} to {max(delays)} ns ({min(delays)/1000:.3f} to {max(delays)/1000:.3f} µs)\n")
                f.write(f"# Number of Points: {len(delays)}\n")
            
            # Write measurement parameters
            for key, value in parameters.items():
                if key != 'delay_times':  # Skip the delays list as it's in the data
                    f.write(f"# {key}: {value}\n")
            
            f.write("#\n")  # Empty line to separate header from data
            
            # Write the data
            df.to_csv(f, index=False, float_format='%.7f')
        
        return filename
