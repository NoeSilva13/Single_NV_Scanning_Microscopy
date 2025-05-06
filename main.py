import numpy as np
import time
from galvo_controller import GalvoScannerController
from scan_visualizer import RealTimeScanVisualizer, plot_scan_results
import argparse
import json
import os
import sys

class ScanningMicroscope:
    def __init__(self, config_file=None):
        """
        Initialize the scanning microscope system.
        
        Args:
            config_file (str): Path to configuration file (optional)
        """
        try:
            self.controller = GalvoScannerController()
            self.config = self._load_config(config_file) if config_file else self._default_config()
            self.visualizer = None
        except Exception as e:
            print(f"Error initializing scanning microscope: {str(e)}")
            sys.exit(1)
        
    def _load_config(self, config_file):
        """Load configuration from file."""
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Configuration file {config_file} not found. Using default configuration.")
            return self._default_config()
        except json.JSONDecodeError:
            print(f"Error parsing configuration file {config_file}. Using default configuration.")
            return self._default_config()
    
    def _default_config(self):
        """Return default configuration."""
        return {
            'scan_range': {
                'x': [-1.0, 1.0],
                'y': [-1.0, 1.0]
            },
            'resolution': {
                'x': 10,
                'y': 10
            },
            'dwell_time': 0.01,
            'scan_mode': 'realtime'  # or 'buffered'
        }
    
    def save_config(self, filename):
        """Save current configuration to file."""
        try:
            with open(filename, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Warning: Could not save configuration: {str(e)}")
    
    def setup_scan(self):
        """Set up scan parameters based on configuration."""
        try:
            x_range = self.config['scan_range']['x']
            y_range = self.config['scan_range']['y']
            x_res = self.config['resolution']['x']
            y_res = self.config['resolution']['y']
            
            self.x_points = np.linspace(x_range[0], x_range[1], x_res)
            self.y_points = np.linspace(y_range[0], y_range[1], y_res)
            
            # Initialize visualizer
            self.visualizer = RealTimeScanVisualizer(self.x_points, self.y_points)
        except Exception as e:
            print(f"Error setting up scan: {str(e)}")
            raise
    
    def run_scan(self):
        """Run the scan with current configuration."""
        try:
            if not self.visualizer:
                self.setup_scan()
            
            if self.config['scan_mode'] == 'realtime':
                self._run_realtime_scan()
            else:
                self._run_buffered_scan()
        except Exception as e:
            print(f"Error during scan: {str(e)}")
            raise
    
    def _run_realtime_scan(self):
        """Run scan with real-time visualization."""
        try:
            def data_generator():
                for x_idx, y_idx, counts in self.controller.scan_pattern_realtime(
                    self.x_points, self.y_points, self.config['dwell_time']
                ):
                    yield x_idx, y_idx, counts
                    # Allow for keyboard interrupt between points
                    time.sleep(0.001)
            
            print("Starting continuous scanning. Press Ctrl+C to stop.")
            self.visualizer.start_animation(data_generator())
        except Exception as e:
            print(f"Error during real-time scan: {str(e)}")
            raise
    
    def _run_buffered_scan(self):
        """Run scan with buffered acquisition."""
        try:
            scan_data = self.controller.scan_pattern_buffered(
                self.x_points, self.y_points, self.config['dwell_time']
            )
            plot_scan_results(scan_data)
        except Exception as e:
            print(f"Error during buffered scan: {str(e)}")
            raise
    
    def close(self):
        """Safely close the system."""
        try:
            if self.visualizer:
                self.visualizer.stop_animation()
            self.controller.close()
        except Exception as e:
            print(f"Warning: Error during shutdown: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description='Single NV Scanning Microscope Control')
    parser.add_argument('--config', type=str, help='Path to configuration file')
    parser.add_argument('--mode', choices=['realtime', 'buffered'], help='Scanning mode')
    args = parser.parse_args()
    
    try:
        # Initialize microscope
        microscope = ScanningMicroscope(args.config)
        
        if args.mode:
            microscope.config['scan_mode'] = args.mode
        
        # Run scan
        microscope.run_scan()
    except KeyboardInterrupt:
        print("\nScan interrupted by user")
    except Exception as e:
        print(f"\nError: {str(e)}")
    finally:
        try:
            microscope.close()
        except:
            pass

if __name__ == '__main__':
    main()