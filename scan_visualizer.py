import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Normalize
from matplotlib.animation import FuncAnimation
import matplotlib as mpl

class RealTimeScanVisualizer:
    def __init__(self, x_points, y_points):
        """
        Initialize real-time scan visualizer.
        
        Args:
            x_points (array): X-axis voltage points
            y_points (array): Y-axis voltage points
        """
        self.x_points = x_points
        self.y_points = y_points
        self.n_x = len(x_points)
        self.n_y = len(y_points)
        
        # Initialize data array
        self.data = np.zeros((self.n_y, self.n_x))
        
        # Create figure and axis
        self.fig, self.ax = plt.subplots(figsize=(10, 8))
        self.im = self.ax.imshow(
            self.data,
            origin='lower',
            aspect='auto',
            extent=[x_points[0], x_points[-1], y_points[0], y_points[-1]],
            cmap='viridis'
        )
        
        # Add colorbar
        self.cbar = self.fig.colorbar(self.im, ax=self.ax)
        self.cbar.set_label('Counts per Second')
        
        # Set labels and title
        self.ax.set_xlabel('X Position (V)')
        self.ax.set_ylabel('Y Position (V)')
        self.ax.set_title('Real-time Scan Visualization')
        
        # Initialize animation
        self.animation = None
        self.scan_complete = False
        self.current_scan = 0
        
    def reset_data(self):
        """Reset the data array for a new scan."""
        self.data = np.zeros((self.n_y, self.n_x))
        self.scan_complete = False
        self.current_scan += 1
        self.ax.set_title(f'Real-time Scan Visualization - Scan {self.current_scan}')
        
    def update(self, frame_data):
        """
        Update the visualization with new data.
        
        Args:
            frame_data (tuple): (x_idx, y_idx, counts_per_second) for the current point
        """
        x_idx, y_idx, counts_per_second = frame_data
        
        # If we've completed a scan, reset the data
        if self.scan_complete:
            self.reset_data()
        
        # Update the data
        self.data[y_idx, x_idx] = counts_per_second
        
        # Check if we've completed a scan
        if x_idx == self.n_x - 1 and y_idx == self.n_y - 1:
            self.scan_complete = True
        
        # Update the image data
        self.im.set_data(self.data)
        
        # Update colorbar limits
        self.im.set_clim(vmin=self.data.min(), vmax=self.data.max())
        
        return [self.im]
    
    def start_animation(self, data_generator):
        """
        Start real-time animation using the provided data generator.
        
        Args:
            data_generator: Generator function that yields (x_idx, y_idx, counts_per_second)
        """
        self.animation = FuncAnimation(
            self.fig,
            self.update,
            frames=data_generator,
            interval=50,  # Update every 50ms
            blit=True
        )
        plt.show()
    
    def stop_animation(self):
        """Stop the animation if it's running."""
        if self.animation is not None:
            self.animation.event_source.stop()
    
    def save_animation(self, filename):
        """Save the animation to a file."""
        if self.animation is not None:
            self.animation.save(filename, writer='pillow', fps=20)

def plot_scan_results(scan_data):
    """
    Visualize 2D scan results as a heatmap with measurement positions marked.
    
    Args:
        scan_data (dict): Dictionary containing scan results with keys:
            - 'x': Array of x-axis positions (voltage values)
            - 'y': Array of y-axis positions (voltage values)
            - 'counts': Array of measurement values (counts per second)
    """
    # Convert data to numpy arrays for easier manipulation
    x = np.array(scan_data['x'])
    y = np.array(scan_data['y'])
    counts = np.array(scan_data['counts'])
    
    # Reshape 1D arrays into 2D grids for visualization
    n_x = len(np.unique(x))
    n_y = len(np.unique(y))
    
    x_grid = x.reshape(n_y, n_x)
    y_grid = y.reshape(n_y, n_x)
    counts_grid = counts.reshape(n_y, n_x)

    plt.figure(figsize=(10, 8))
    
    plt.pcolormesh(
        x_grid, 
        y_grid, 
        counts_grid, 
        shading='auto', 
        norm=Normalize(vmin=counts.min(), vmax=counts.max())
    )
    
    plt.colorbar(label='Counts per Second')
    plt.xlabel("X Position (V)")
    plt.ylabel("Y Position (V)")
    plt.title("SPD Counts Heatmap")
    
    plt.scatter(
        x, 
        y, 
        c='red', 
        s=10,
        label='Positions'
    )
    
    plt.legend()
    plt.show()