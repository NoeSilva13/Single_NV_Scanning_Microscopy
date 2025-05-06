import numpy as np
import time
from galvo_controller import GalvoScannerController
from scan_visualizer import RealTimeScanVisualizer, plot_scan_results
import argparse
import json
import os

class ScanningMicroscope:
    def __init__(self, config_file=None):
        """
        Initialize the scanning microscope system.
        
        Args:
            config_file (str): Path to configuration file (optional)
        """
        self.controller = GalvoScannerController()
        self.config = self._load_config(config_file) if config_file else self._default_config()
        self.visualizer = None
        
    def _load_config(self, config_file):
        """Load configuration from file."""
        with open(config_file, 'r') as f:
            return json.load(f)
    
    def _default_config(self):
        """Return default configuration."""
        return {
            'scan_range': {
                'x': [-5.0, 5.0],
                'y': [-5.0, 5.0]
            },
            'resolution': {
                'x': 100,
                'y': 100
            },
            'dwell_time': 0.01,
            'scan_mode': 'realtime'  # or 'buffered'
        }
    
    def save_config(self, filename):
        """Save current configuration to file."""
        with open(filename, 'w') as f:
            json.dump(self.config, f, indent=4)
    
    def setup_scan(self):
        """Set up scan parameters based on configuration."""
        x_range = self.config['scan_range']['x']
        y_range = self.config['scan_range']['y']
        x_res = self.config['resolution']['x']
        y_res = self.config['resolution']['y']
        
        self.x_points = np.linspace(x_range[0], x_range[1], x_res)
        self.y_points = np.linspace(y_range[0], y_range[1], y_res)
        
        # Initialize visualizer
        self.visualizer = RealTimeScanVisualizer(self.x_points, self.y_points)
    
    def run_scan(self):
        """Run the scan with current configuration."""
        if not self.visualizer:
            self.setup_scan()
        
        if self.config['scan_mode'] == 'realtime':
            self._run_realtime_scan()
        else:
            self._run_buffered_scan()
    
    def _run_realtime_scan(self):
        """Run scan with real-time visualization."""
        def data_generator():
            for x_idx, y_idx, counts in self.controller.scan_pattern_realtime(
                self.x_points, self.y_points, self.config['dwell_time']
            ):
                yield x_idx, y_idx, counts
        
        self.visualizer.start_animation(data_generator())
    
    def _run_buffered_scan(self):
        """Run scan with buffered acquisition."""
        scan_data = self.controller.scan_pattern_buffered(
            self.x_points, self.y_points, self.config['dwell_time']
        )
        plot_scan_results(scan_data)
    
    def close(self):
        """Safely close the system."""
        if self.visualizer:
            self.visualizer.stop_animation()
        self.controller.close()

def main():
    parser = argparse.ArgumentParser(description='Single NV Scanning Microscope Control')
    parser.add_argument('--config', type=str, help='Path to configuration file')
    parser.add_argument('--mode', choices=['realtime', 'buffered'], help='Scanning mode')
    args = parser.parse_args()
    
    # Initialize microscope
    microscope = ScanningMicroscope(args.config)
    
    if args.mode:
        microscope.config['scan_mode'] = args.mode
    
    try:
        # Run scan
        microscope.run_scan()
    except KeyboardInterrupt:
        print("\nScan interrupted by user")
    finally:
        microscope.close()

if __name__ == '__main__':
    main()