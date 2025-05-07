"""
Test live plotting with photon counting from the DAQ.
This script demonstrates how to use live_plot.py with real photon counting data.
"""

import numpy as np
import live_plot
import time
from galvo_controller import GalvoScannerController

def main():
    try:
        # Initialize the controller
        controller = GalvoScannerController()
        
        # Create a function that reads photon counts from the DAQ
        def measure_photons():
            try:
                # Read photon counts for 0.1 seconds
                counts = controller.read_spd_count(sampling_time=0.1)
                # Convert to counts per second
                return counts * 10  # Multiply by 10 since we sampled for 0.1s
            except Exception as e:
                print(f"Error reading photon counts: {str(e)}")
                return 0
        
        # Test live plotting with photon counting
        print("Starting live photon counting plot. Press Ctrl+C to stop.")
        try:
            live_plot.live_plot(
                measure_function=measure_photons,
                histogram_range=100,  # Show last 100 points
                dt=0.1  # Update every 0.1 seconds
            )
        except KeyboardInterrupt:
            print("\nPlotting stopped by user")
        except Exception as e:
            print(f"\nError during plotting: {str(e)}")
            
    except Exception as e:
        print(f"Error initializing controller: {str(e)}")
    finally:
        try:
            controller.close()
        except:
            pass

if __name__ == "__main__":
    main() 