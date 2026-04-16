import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_pdf import FigureCanvasPdf
from matplotlib.colors import Normalize
from pathlib import Path
from utils import calculate_scale


def plot_scan_results(scan_data, save_path):
    """
    Save 2D scan results as a PDF heatmap, automatically handling file extension.

    Uses the OO matplotlib API (Figure + FigureCanvasPdf) so that no global
    pyplot state is touched — this makes the function safe to call from any
    thread without contending with the main-thread event loop.

    Args:
        scan_data (dict): Dictionary containing scan results
        save_path (str or Path): Path where to save the plot (will force .pdf extension)
    """
    save_path = Path(save_path)
    plot_path = save_path.with_suffix('.pdf')

    x_grid = np.array(scan_data['x_points'])
    y_grid = np.array(scan_data['y_points'])
    counts_grid = np.array(scan_data['image'])

    fig = Figure(figsize=(10, 8))
    FigureCanvasPdf(fig)
    ax = fig.add_subplot(111)

    im = ax.pcolormesh(
        x_grid,
        y_grid,
        counts_grid,
        shading='auto',
        norm=Normalize(vmin=counts_grid.min(), vmax=counts_grid.max()),
        cmap='viridis'
    )

    microns_per_pixel_x = calculate_scale(x_grid[0], x_grid[-1], 1)
    microns_per_pixel_y = calculate_scale(y_grid[0], y_grid[-1], 1)

    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label('SPD Counts', rotation=270, labelpad=15)
    ax.set_xlabel(f"X Position (V) ({microns_per_pixel_x:.1f} µm)")
    ax.set_ylabel(f"Y Position (V) ({microns_per_pixel_y:.1f} µm)")
    ax.set_title("SPD Counts Heatmap")
    fig.tight_layout()

    plot_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(plot_path, format='pdf', bbox_inches='tight')