import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Normalize

def plot_scan_results(scan_data):
    x = np.array(scan_data['x'])
    y = np.array(scan_data['y'])
    counts = np.array(scan_data['counts'])
    
    # Reshape for grid
    n_x = len(np.unique(x))
    n_y = len(np.unique(y))
    x_grid = x.reshape(n_y, n_x)
    y_grid = y.reshape(n_y, n_x)
    counts_grid = counts.reshape(n_y, n_x)

    # Plot
    plt.figure(figsize=(10, 8))
    plt.pcolormesh(x_grid, y_grid, counts_grid, shading='auto', norm=Normalize(vmin=counts.min(), vmax=counts.max()))
    plt.colorbar(label='SPD Counts')
    plt.xlabel("X Position (V)")
    plt.ylabel("Y Position (V)")
    plt.title("SPD Counts Heatmap")
    plt.scatter(x, y, c='red', s=10, label='Positions')
    plt.legend()
    plt.show()