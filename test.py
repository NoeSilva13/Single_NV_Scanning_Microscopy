import numpy as np
from galvo_controller import GalvoScannerController
from scan_visualizer import plot_scan_results

def single_axis_scan(scanner, axis='x'):
    scanner.scan_single_axis(axis, start=-1, end=1, points=200, fixed_voltage=0.0, dwell_time=0.05)
    return 

def two_dimensional_scan(scanner):
    """Perform a full 2D raster scan"""
    x_points = np.linspace(-0.5, 0.5, 20)
    y_points = np.linspace(-0.5, 0.5, 20)
    
    #scan_data = scanner.scan_pattern(x_points, y_points, dwell_time=0.05)
    scan_data = scanner.scan_pattern_opm(x_points, y_points, dwell_time=0.05)
    plot_scan_results(scan_data)
    return scan_data

def show_menu():
    """Display the menu options"""
    print("\nGalvo Scanner Control Menu")
    print("1. Perform X-axis scan (Y=0)")
    print("2. Perform Y-axis scan (X=0)")
    print("3. Perform 2D raster scan")
    print("4. Exit")
    return input("Select an option (1-4): ")

def main():
    scanner = GalvoScannerController()
    try:
        while True:
            choice = show_menu()
            
            if choice == '1':
                print("\nStarting X-axis scan...")
                while True:
                    single_axis_scan(scanner, axis='x')
            elif choice == '2':
                print("\nStarting Y-axis scan...")
                while True:
                    single_axis_scan(scanner, axis='y')
            elif choice == '3':
                print("\nStarting 2D raster scan...")
                two_dimensional_scan(scanner)
            elif choice == '4':
                print("Exiting program...")
                break
            else:
                print("Invalid option. Please try again.")
                
    finally:
        scanner.close()
        print("Scanner safely reset to (0,0)")

if __name__ == "__main__":
    main()