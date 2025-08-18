import os
import time
import json
import pandas as pd
import numpy as np

class ODMRDataManager:
    """Data manager for ODMR-related experiments."""
    
    # Define experiment types and their configurations
    EXPERIMENT_CONFIGS = {
        'odmr': {
            'folder_name': 'ODMR',
            'file_suffix': '_ODMR',
            'x_column': 'Frequency_Hz',
            'x_columns_converted': [],
            'data_key': 'mw_frequencies',
            'x_label': 'Frequency',
            'x_unit': 'Hz',
            'x_range_format': lambda min_x, max_x: f"{min_x:.1f} Hz ({min_x/1e9:.6f} to {max_x/1e9:.6f} GHz)"
        },
        'rabi': {
            'folder_name': 'Rabi',
            'file_suffix': '_Rabi',
            'x_column': 'Duration_ns',
            'x_columns_converted': [
                ('Duration_s', 1e-9),  # SI unit
            ],
            'data_key': 'mw_durations',
            'x_label': 'Duration',
            'x_unit': 'ns',
            'x_range_format': lambda min_x, max_x: f"{min_x} ns ({min_x*1e-9:.9f} to {max_x*1e-9:.9f} s)"
        },
        't1': {
            'folder_name': 'T1',
            'file_suffix': '_T1',
            'x_column': 'Delay_ns',
            'x_columns_converted': [
                ('Delay_s', 1e-9),  # SI unit
                ('Delay_us', 1e-3),  # Common unit in the field
            ],
            'data_key': 'delay_times',
            'x_label': 'Delay',
            'x_unit': 'ns',
            'x_range_format': lambda min_x, max_x: f"{min_x} ns ({min_x*1e-9:.9f} to {max_x*1e-9:.9f} s)"
        }
    }
    
    def save_experiment_data(self, experiment_type: str, x_data: list, count_rates: list, parameters: dict) -> str:
        """
        Save experiment data to a CSV file in a daily folder with experiment-specific subfolder.
        
        Args:
            experiment_type: Type of experiment ('odmr', 'rabi', or 't1')
            x_data: List of x-axis values (frequencies, durations, or delays)
            count_rates: List of corresponding count rates (cps)
            parameters: Dictionary containing measurement parameters
            
        Returns:
            str: The path to the saved file
            
        Raises:
            ValueError: If experiment_type is not recognized
        """
        if experiment_type not in self.EXPERIMENT_CONFIGS:
            raise ValueError(f"Unknown experiment type: {experiment_type}")
        
        config = self.EXPERIMENT_CONFIGS[experiment_type]
        
        # Create daily folder for data
        daily_folder = time.strftime("%m%d%y")
        if not os.path.exists(daily_folder):
            os.makedirs(daily_folder)
        
        # Create experiment-specific subfolder
        exp_folder = os.path.join(daily_folder, config['folder_name'])
        if not os.path.exists(exp_folder):
            os.makedirs(exp_folder)
        
        # Get list of existing .csv files in the experiment folder
        existing_files = [f for f in os.listdir(exp_folder) 
                        if f.startswith(daily_folder) and f.endswith('.csv')]
        
        # Determine the next sequence number (001, 002, etc.)
        seq_num = len(existing_files) + 1
        seq_str = f"{seq_num:03d}"
        
        # Create filename
        filename = os.path.join(exp_folder, f"{daily_folder}{seq_str}{config['file_suffix']}.csv")

        # Create DataFrame with the data
        data_dict = {
            config['x_column']: x_data,
            'Count_Rate_cps': count_rates
        }
        
        # Add converted columns (including SI units)
        if 'x_columns_converted' in config:
            for conv_name, conv_factor in config['x_columns_converted']:
                data_dict[conv_name] = np.array(x_data) * conv_factor

        df = pd.DataFrame(data_dict)

        # Write data to file
        with open(filename, 'w', encoding='utf-8', newline='') as f:
            # Write measurement date and time
            measurement_time = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"# Measurement Time: {measurement_time}\n")
            f.write(f"# Experiment Type: {config['folder_name']}\n")
            
            # Write data range
            if len(x_data) > 0:
                f.write(f"# {config['x_label']} Range: {config['x_range_format'](min(x_data), max(x_data))}\n")
                f.write(f"# Number of Points: {len(x_data)}\n")
            
            # Write measurement parameters (excluding the data list)
            save_params = parameters.copy()
            if config['data_key'] in save_params:
                del save_params[config['data_key']]
            
            for key, value in save_params.items():
                f.write(f"# {key}: {value}\n")
            
            f.write("#\n")  # Empty line to separate header from data
            
            # Write the data
            df.to_csv(f, index=False, float_format='%.9f')  # Increased precision for SI units
        
        return filename