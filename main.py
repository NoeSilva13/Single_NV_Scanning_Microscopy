import numpy as np
from galvo_controller import GalvoScannerController
from scan_visualizer import plot_scan_results

def single_axis_scan(scanner, axis='x'):
    scanner.scan_single_axis(axis, start=0, end=0.5, points=2, fixed_voltage=0.0, dwell_time=0.1)
    return 

def two_dimensional_scan(scanner):
    """Perform a full 2D raster scan"""
    x_points = np.linspace(-0.05, 0.05, 10)
    y_points = np.linspace(-0.1, 0.1, 10)
    
    scan_data = scanner.scan_pattern(x_points, y_points, dwell_time=1)
    #scan_data = scanner.scan_pattern_opm(x_points, y_points, dwell_time=0.05)
    #scan_data = scanner.scan_pattern_pd(x_points, y_points, dwell_time=0.01)
    plot_scan_results(scan_data)
    return scan_data

def show_menu():
    """Display the menu options"""
    print("\nGalvo Scanner Control Menu")
    print("1. Perform X-axis scan (Y=0)")
    print("2. Perform Y-axis scan (X=0)")
    print("3. Perform 2D raster scan")
    print("4. Set to (x,y)")
    print("5. Reset to (0,0)")
    print("6. Exit")
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
                x=input("Input x:")
                y=input("Input y:")
                scanner.set(float(x), float(y))
            elif choice == '5':
                scanner.close()
                print("Scanner safely reset to (0,0)")
            elif choice == '6':
                print("Exiting program...")
                break
            else:
                print("Invalid option. Please try again.")
                
    finally:
        scanner.close()
        print("Scanner safely reset to (0,0)")

if __name__ == "__main__":
    main()