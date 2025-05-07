import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Normalize
from matplotlib.animation import FuncAnimation
import matplotlib as mpl
from matplotlib.widgets import RangeSlider

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
        
        # Create figure with subplots for sliders
        self.fig = plt.figure(figsize=(10, 10))
        gs = self.fig.add_gridspec(3, 1, height_ratios=[0.1, 0.1, 0.8])
        
        # Create slider axes
        self.ax_x_slider = self.fig.add_subplot(gs[0])
        self.ax_y_slider = self.fig.add_subplot(gs[1])
        self.ax = self.fig.add_subplot(gs[2])
        
        # Create range sliders
        self.x_slider = RangeSlider(
            self.ax_x_slider,
            'X Range',
            x_points[0],
            x_points[-1],
            valinit=(x_points[0], x_points[-1]),
            valstep=0.1
        )
        
        self.y_slider = RangeSlider(
            self.ax_y_slider,
            'Y Range',
            y_points[0],
            y_points[-1],
            valinit=(y_points[0], y_points[-1]),
            valstep=0.1
        )
        
        # Create image plot
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
        
        # Connect slider events
        self.x_slider.on_changed(self.update_x_range)
        self.y_slider.on_changed(self.update_y_range)
        
        # Adjust layout
        self.fig.tight_layout()
        
    def update_x_range(self, val):
        """Update X-axis range when slider changes."""
        self.ax.set_xlim(val)
        self.fig.canvas.draw_idle()
        
    def update_y_range(self, val):
        """Update Y-axis range when slider changes."""
        self.ax.set_ylim(val)
        self.fig.canvas.draw_idle()
        
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
        self.fig.canvas.draw_idle()
        
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
            - 'counts': 2D array of measurement values (counts per second)
    """
    # Close any existing figures
    plt.close('all')
    
    # Get the data
    x = scan_data['x']
    y = scan_data['y']
    counts = scan_data['counts']  # This is already a 2D array

    # Create new figure
    fig = plt.figure(figsize=(10, 8))
    
    # Create meshgrid for plotting
    X, Y = np.meshgrid(x, y)
    
    plt.pcolormesh(
        X, 
        Y, 
        counts, 
        shading='auto', 
        norm=Normalize(vmin=counts.min(), vmax=counts.max())
    )
    
    plt.colorbar(label='Counts per Second')
    plt.xlabel("X Position (V)")
    plt.ylabel("Y Position (V)")
    plt.title("SPD Counts Heatmap")
    
    # Plot measurement positions
    for i in range(len(y)):
        for j in range(len(x)):
            plt.scatter(x[j], y[i], c='red', s=10, alpha=0.5)
    
    plt.legend()
    plt.show(block=True)  # Use block=True to ensure only one figure is shown