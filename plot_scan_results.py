import matplotlib
matplotlib.use('PDF')  # Set the backend to PDF before importing pyplot
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Normalize
from pathlib import Path
from utils import calculate_scale

def plot_scan_results(scan_data, save_path):
    """
    Save 2D scan results as a PDF heatmap, automatically handling file extension.
    
    Args:
        scan_data (dict): Dictionary containing scan results
        save_path (str or Path): Path where to save the plot (will force .pdf extension)
    """
    save_path = Path(save_path)
    
    # Force .pdf extension regardless of input
    plot_path = save_path.with_suffix('.pdf')
    
    # Rest of plotting code...
    x_grid = np.array(scan_data['x_points'])
    y_grid = np.array(scan_data['y_points'])
    counts_grid = np.array(scan_data['image'])
    
    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.pcolormesh(
        x_grid,
        y_grid,
        counts_grid,
        shading='auto',
        norm=Normalize(vmin=counts_grid.min(), vmax=counts_grid.max()),
        cmap='viridis'
    )
    
    # Calculate the scale (microns per pixel)
    microns_per_pixel_x = calculate_scale(x_grid[0], x_grid[-1], 1)
    microns_per_pixel_y = calculate_scale(y_grid[0], y_grid[-1], 1)
    # Draw the scale bar
    ax.plot([x_grid[0], x_grid[-1]], [y_grid[0], y_grid[0]], color='white', linewidth=2)
    ax.text(x_grid[0] + (x_grid[-1] - x_grid[0])/2, y_grid[0] + 0.02, f'{microns_per_pixel_x:.1f} µm', color='white', horizontalalignment='center', verticalalignment='bottom')
    ax.plot([x_grid[0], x_grid[0]], [y_grid[0], y_grid[-1]], color='white', linewidth=2)
    ax.text(x_grid[0]*0.78, y_grid[0] + (y_grid[-1] - y_grid[0])/2, f'{microns_per_pixel_y:.1f} µm', color='white', horizontalalignment='right', verticalalignment='center')
    
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label('SPD Counts', rotation=270, labelpad=15)
    ax.set_xlabel("X Position (V)")
    ax.set_ylabel("Y Position (V)")
    ax.set_title("SPD Counts Heatmap")
    fig.tight_layout()
    
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(plot_path, format='pdf', bbox_inches='tight')
    plt.close(fig)