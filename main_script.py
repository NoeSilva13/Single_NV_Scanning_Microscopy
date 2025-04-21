import numpy as np
from galvo_controller import GalvoScannerController
from scan_visualizer import plot_scan_results

def main():
    scanner = GalvoScannerController()
    try:
        x_points = np.linspace(-5, 5, 20)
        y_points = np.linspace(-5, 5, 20)
        
        # Run scan and get data
        scan_data = scanner.scan_pattern(x_points, y_points, dwell_time=0.05)
        
        # Visualize results
        plot_scan_results(scan_data)
        
    finally:
        scanner.close()

if __name__ == "__main__":
    main()