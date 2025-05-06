import numpy as np
from galvo_controller import GalvoScannerController
from scan_visualizer import plot_scan_results

def single_axis_scan(scanner, axis='x'):
    """
    Perform a single axis scan (either X or Y) with fixed voltage on the other axis.
    
    Args:
        scanner (GalvoScannerController): The galvo scanner controller instance
        axis (str): Which axis to scan ('x' or 'y')
    """
    # Scan from 0V to 0.5V with 2 points (coarse scan for testing)
    # Other axis is fixed at 0V with 100ms dwell time at each point
    scanner.scan_single_axis(axis, start=0, end=0.5, points=2, fixed_voltage=0.0, dwell_time=0.1)
    return 

def two_dimensional_scan(scanner):
    """
    Perform a full 2D raster scan over a defined area.
    
    Args:
        scanner (GalvoScannerController): The galvo scanner controller instance
    
    Returns:
        dict: The collected scan data containing positions and measurements
    """
    # Define scan area: 
    # X-axis: -0.05V to 0.05V with 10 points
    # Y-axis: -0.1V to 0.1V with 10 points
    x_points = np.linspace(-0.05, 0.05, 10)
    y_points = np.linspace(-0.1, 0.1, 10)
    
    # Perform the scan with 1 second dwell time per point
    scan_data = scanner.scan_pattern(x_points, y_points, dwell_time=1)

    #scan_data = scanner.scan_pattern_pd(x_points, y_points, dwell_time=0.01) # Using photodiode

    # Visualize the results
    plot_scan_results(scan_data)
    return scan_data

def show_menu():
    """
    Display the interactive menu for scanner control.
    
    Returns:
        str: User's menu selection
    """
    print("\nGalvo Scanner Control Menu")
    print("1. Perform X-axis scan (Y=0)")
    print("2. Perform Y-axis scan (X=0)")
    print("3. Perform 2D raster scan")
    print("4. Set to (x,y)") # Manually set specific position
    print("5. Reset to (0,0)") # Zero position
    print("6. Exit")
    return input("Select an option (1-6): ")

def main():
    """
    Main program loop for interactive galvo scanner control.
    """
    # Initialize the scanner controller
    scanner = GalvoScannerController()
    try:
        # Main program loop
        while True:
            # Show menu and get user choice
            choice = show_menu()
            
            # Process user selection
            if choice == '1':
                print("\nStarting X-axis scan...")
                # Continuous X-axis scanning until interrupted
                while True:
                    single_axis_scan(scanner, axis='x')

            elif choice == '2':
                print("\nStarting Y-axis scan...")
                # Continuous Y-axis scanning until interrupted
                while True:
                    single_axis_scan(scanner, axis='y')

            elif choice == '3':
                print("\nStarting 2D raster scan...")
                # Perform single 2D scan
                two_dimensional_scan(scanner)

            elif choice == '4':
                # Manual position setting
                x=input("Input x:")
                y=input("Input y:")
                scanner.set(float(x), float(y))

            elif choice == '5':
                 # Reset to zero position
                scanner.close() # This sets voltages to (0,0)
                print("Scanner safely reset to (0,0)")

            elif choice == '6':
                # Exit program
                print("Exiting program...")
                break

            else:
                print("Invalid option. Please try again.")
                
    finally:
        # Ensure scanner is properly closed on exit
        scanner.close()
        print("Scanner safely reset to (0,0)")

if __name__ == "__main__":
    # Entry point for the program
    main()