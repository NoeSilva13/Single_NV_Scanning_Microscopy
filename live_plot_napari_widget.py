"""
live_plot_napari_widget
========================================================================
A napari-compatible widget for live plotting of measurements
"""

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from qtpy.QtCore import QTimer
from qtpy.QtWidgets import QWidget, QVBoxLayout
import numpy as np
from time import time

class LivePlotNapariWidget(QWidget):
    def __init__(
        self,
        measure_function,
        histogram_range=100,
        dt=100,  # dt in milliseconds
        widget_height=250,
        figsize=(4, 2),
        bg_color='#262930',
        plot_color='#00ff00',
        parent=None
    ):
        super().__init__(parent)
        self.measure_function = measure_function
        self.histogram_range = histogram_range
        self.bg_color = bg_color
        self.plot_color = plot_color
        
        # Setup widget dimensions
        self.setFixedHeight(widget_height)
        
        # Setup the figure with a style that matches napari's dark theme
        self.fig = Figure(figsize=figsize, facecolor=self.bg_color)
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor(self.bg_color)
        
        # Style the plot to match napari's dark theme
        self.ax.tick_params(colors='white')
        for spine in self.ax.spines.values():
            spine.set_color('white')
        
        # Setup the layout
        layout = QVBoxLayout()
        layout.addWidget(self.canvas)
        self.setLayout(layout)
        
        # Initialize data
        self.x_data = []
        self.y_data = []
        self.t0 = time()
        
        # Setup timer for updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(dt)  # Update every dt milliseconds
        
        # Setup the plot
        self.line, = self.ax.plot([], [], 'o-', color=self.plot_color)  # Line with markers
        self.ax.set_xlabel('Time (s)', color='white')
        self.ax.set_ylabel('Signal', color='white')
        self.ax.grid(True, color='gray', alpha=0.3)
        
        # Ensure the figure background matches napari
        self.fig.patch.set_facecolor(self.bg_color)
        self.fig.tight_layout()
        self.canvas.draw()
    
    def update_plot(self):
        try:
            # Get new data
            new_data = self.measure_function()
            current_time = time() - self.t0
            
            # Update data lists
            self.x_data.append(current_time)
            self.y_data.append(new_data)
            
            # Keep only the last histogram_range points
            if len(self.x_data) > self.histogram_range:
                self.x_data = self.x_data[-self.histogram_range:]
                self.y_data = self.y_data[-self.histogram_range:]
            
            # Update the plot
            self.line.set_data(self.x_data, self.y_data)
            self.ax.relim()
            self.ax.autoscale_view()
            self.fig.tight_layout()
            self.canvas.draw()
        except Exception as e:
            print(f"Error updating plot: {e}")
    
    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)

    def clear(self):
        """Clear the current plot"""
        self.ax.clear()
        self.canvas.draw()

def live_plot(
    measure_function,
    histogram_range=100,
    dt=0.1,
    widget_height=250,
    figsize=(4, 2),
    bg_color='#262930',
    plot_color='#00ff00'
):
    '''
    Creates a LivePlotNapariWidget that updates with new measurements
    
    Parameters
    ---------------------------------------------------------------------------------
    measure_function : callable
        Function that generates a data point or array of points
    histogram_range : int
        Total number of data points plotted before overwriting
    dt : float
        Time between datapoints in seconds (converted to milliseconds internally)
    widget_height : int
        Height of the widget in pixels
    figsize : tuple
        Figure size in inches (width, height)
    bg_color : str
        Background color of the plot
    plot_color : str
        Color of the plot line
    
    Returns
    ---------------------------------------------------------------------------------
    LivePlotNapariWidget
        A Qt widget that can be added to napari's viewer
    '''
    return LivePlotNapariWidget(
        measure_function,
        histogram_range,
        int(dt * 1000),
        widget_height,
        figsize,
        bg_color,
        plot_color
    )
