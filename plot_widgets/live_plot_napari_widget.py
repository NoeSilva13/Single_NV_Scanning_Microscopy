"""
live_plot_napari_widget
========================================================================
A napari-compatible widget for live plotting of measurements with overflow detection
"""

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from qtpy.QtCore import QTimer
from qtpy.QtWidgets import QWidget, QVBoxLayout, QGridLayout
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
        alarm_color='#ff0000',  # Red color for overflow alarm
        parent=None
    ):
        super().__init__(parent)
        self.measure_function = measure_function
        self.histogram_range = histogram_range
        self.bg_color = bg_color
        self.plot_color = plot_color
        self.alarm_color = alarm_color
        self.overflow_detected = False
        self.alarm_rect = None
        
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
        layout = QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
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
        self.line, = self.ax.plot([], [], color=self.plot_color)  # Line with markers
        self.ax.set_xlabel('Time (s)', color='white')
        self.ax.set_ylabel('Signal', color='white')
        self.ax.grid(True, color='gray', alpha=0.3)
        
        # Ensure the figure background matches napari
        self.fig.patch.set_facecolor(self.bg_color)
        self.fig.tight_layout()
        self.canvas.draw()
    
    def update_plot(self):
        try:
            # Get new data - can be a single value or a tuple (value, overflow_flag)
            result = self.measure_function()
            
            # Check if the result includes overflow information
            if isinstance(result, tuple) and len(result) == 2:
                new_data, overflow = result
                self.overflow_detected = overflow
            else:
                # If no overflow info, assume it's just the data value
                new_data = result
                self.overflow_detected = False
                
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
            
            # Display or hide overflow alarm
            self._update_overflow_alarm()
            
            self.fig.tight_layout()
            self.canvas.draw()
        except Exception as e:
            print(f"Error updating plot: {e}")
    
    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)

    def _update_overflow_alarm(self):
        """Update the overflow alarm visual indicator"""
        # Remove existing alarm if present
        if self.alarm_rect is not None:
            self.alarm_rect.remove()
            self.alarm_rect = None
            
        # If overflow detected, display the alarm
        if self.overflow_detected:
            # Get axis dimensions
            bbox = self.ax.get_window_extent().transformed(self.fig.dpi_scale_trans.inverted())
            width, height = bbox.width, bbox.height
            
            # Create a red rectangle at the top of the plot
            self.alarm_rect = Rectangle((0, 0), 1, 1, transform=self.ax.transAxes,
                                       color=self.alarm_color, alpha=0.3,
                                       zorder=1000)  # Ensure it's on top
            self.ax.add_patch(self.alarm_rect)
            
            # Add "OVERFLOW" text
            if not hasattr(self, 'overflow_text') or self.overflow_text not in self.ax.texts:
                self.overflow_text = self.ax.text(0.5, 0.5, "OVERFLOW", 
                                               transform=self.ax.transAxes,
                                               ha='center', va='center',
                                               color='white', fontsize=14, fontweight='bold',
                                               zorder=1001)  # Ensure text is on top of rectangle
        else:
            # Remove overflow text if it exists
            if hasattr(self, 'overflow_text') and self.overflow_text in self.ax.texts:
                self.overflow_text.remove()
                self.overflow_text = None
    
    def clear(self):
        """Clear the current plot"""
        self.ax.clear()
        self.overflow_detected = False
        self.alarm_rect = None
        if hasattr(self, 'overflow_text'):
            self.overflow_text = None
        self.canvas.draw()

def live_plot(
    measure_function,
    histogram_range=100,
    dt=0.1,
    widget_height=250,
    figsize=(4, 2),
    bg_color='#262930',
    plot_color='#00ff00',
    alarm_color='#ff0000'
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
    alarm_color : str
        Color of the overflow alarm
    
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
        plot_color,
        alarm_color
    )