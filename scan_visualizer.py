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
        self.cbar.set_label('Counts')
        
        # Set labels and title
        self.ax.set_xlabel('X Position (V)')
        self.ax.set_ylabel('Y Position (V)')
        self.ax.set_title('Real-time Scan Visualization')
        
        # Initialize animation
        self.animation = None
        
    def update(self, frame_data):
        """
        Update the visualization with new data.
        
        Args:
            frame_data (tuple): (x_idx, y_idx, count) for the current point
        """
        x_idx, y_idx, count = frame_data
        self.data[y_idx, x_idx] = count
        
        # Update the image data
        self.im.set_data(self.data)
        
        # Update colorbar limits
        self.im.set_clim(vmin=self.data.min(), vmax=self.data.max())
        
        return [self.im]
    
    def start_animation(self, data_generator):
        """
        Start real-time animation using the provided data generator.
        
        Args:
            data_generator: Generator function that yields (x_idx, y_idx, count)
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
            - 'counts': Array of measurement values (SPD counts)
    """
    # Convert data to numpy arrays for easier manipulation
    x = np.array(scan_data['x'])
    y = np.array(scan_data['y'])
    counts = np.array(scan_data['counts'])
    
    # Reshape 1D arrays into 2D grids for visualization
    # Determine number of unique points in each dimension
    n_x = len(np.unique(x))  # Number of x-axis points
    n_y = len(np.unique(y))  # Number of y-axis points
    
    # Reshape into 2D grids matching the scan pattern
    x_grid = x.reshape(n_y, n_x)  # X positions in grid format
    y_grid = y.reshape(n_y, n_x)  # Y positions in grid format
    counts_grid = counts.reshape(n_y, n_x)  # Measurement values in grid format

    # Create the plot figure with specified size
    plt.figure(figsize=(10, 8))
    
    # Create a pseudocolor plot (heatmap) of the measurement data
    # - shading='auto' automatically determines shading type
    # - Normalize ensures consistent color scaling between plots
    plt.pcolormesh(
        x_grid, 
        y_grid, 
        counts_grid, 
        shading='auto', 
        norm=Normalize(vmin=counts.min(), vmax=counts.max())
    )
    
    # Add colorbar with label
    plt.colorbar(label='SPD Counts')
    
    # Axis labels
    plt.xlabel("X Position (V)")
    plt.ylabel("Y Position (V)")
    
    # Title
    plt.title("SPD Counts Heatmap")
    
    # Overlay actual measurement positions as red dots
    plt.scatter(
        x, 
        y, 
        c='red', 
        s=10,  # Dot size
        label='Positions'  # For legend
    )
    
    # Add legend to identify the position markers
    plt.legend()
    
    # Display the plot
    plt.show()