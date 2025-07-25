"""
live_plot_pyqtgraph_widget
========================================================================
A high-performance napari-compatible widget for live plotting using PyQtGraph
"""

import pyqtgraph as pg
from qtpy.QtCore import QTimer
from qtpy.QtWidgets import QWidget, QVBoxLayout
import numpy as np
from time import time

class LivePlotPyQtGraphWidget(QWidget):
    def __init__(
        self,
        measure_function,
        histogram_range=100,
        dt=100,  # dt in milliseconds
        widget_height=250,
        figsize=(4, 2),  # For compatibility, but not directly used
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
        
        # Create the pyqtgraph plot widget
        self.plot_widget = pg.PlotWidget(background=self.bg_color)
        self.plot_item = self.plot_widget.getPlotItem()
        
        # Style the plot to match napari's dark theme
        self.plot_item.getAxis('left').setPen(pg.mkPen(color='white'))
        self.plot_item.getAxis('bottom').setPen(pg.mkPen(color='white'))
        self.plot_item.getAxis('left').setTextPen(pg.mkPen(color='white'))
        self.plot_item.getAxis('bottom').setTextPen(pg.mkPen(color='white'))
        self.plot_item.setLabel('left', 'Signal', color='white')
        self.plot_item.setLabel('bottom', 'Time (s)', color='white')
        
        # Add grid
        self.plot_item.showGrid(x=True, y=True, alpha=0.3)
        
        # Setup the layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.plot_widget)
        self.setLayout(layout)
        
        # Initialize data
        self.x_data = []
        self.y_data = []
        self.t0 = time()
        
        # Create the plot curve
        self.curve = self.plot_item.plot(
            pen=pg.mkPen(color=self.plot_color, width=1),
            name='Signal'
        )
        
        # Setup timer for updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(dt)  # Update every dt milliseconds
    
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
            
            # Update the plot - this is much faster than matplotlib
            self.curve.setData(self.x_data, self.y_data)
            
        except Exception as e:
            print(f"Error updating plot: {e}")
    
    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)

    def clear(self):
        """Clear the current plot"""
        self.curve.clear()

def live_plot_pyqtgraph(
    measure_function,
    histogram_range=100,
    dt=0.1,
    widget_height=250,
    figsize=(4, 2),
    bg_color='#262930',
    plot_color='#00ff00'
):
    '''
    Creates a high-performance LivePlotPyQtGraphWidget using PyQtGraph
    
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
        For API compatibility (not used in pyqtgraph version)
    bg_color : str
        Background color of the plot
    plot_color : str
        Color of the plot line
    
    Returns
    ---------------------------------------------------------------------------------
    LivePlotPyQtGraphWidget
        A Qt widget that can be added to napari's viewer
    '''
    return LivePlotPyQtGraphWidget(
        measure_function,
        histogram_range,
        int(dt * 1000),
        widget_height,
        figsize,
        bg_color,
        plot_color
    )

# Optional: High-performance version with more advanced features
class AdvancedLivePlotPyQtGraphWidget(LivePlotPyQtGraphWidget):
    """
    Advanced version with additional performance optimizations
    """
    def __init__(self, *args, **kwargs):
        # Enable OpenGL if available for even better performance
        try:
            pg.setConfigOptions(useOpenGL=True)
        except:
            pass  # OpenGL not available
        
        super().__init__(*args, **kwargs)
        
        # Pre-allocate data arrays for better performance
        self._x_buffer = np.full(self.histogram_range, np.nan)
        self._y_buffer = np.full(self.histogram_range, np.nan)
        self._buffer_index = 0
        self._buffer_full = False
    
    def update_plot(self):
        try:
            # Get new data
            new_data = self.measure_function()
            current_time = time() - self.t0
            
            # Use circular buffer for better performance
            self._x_buffer[self._buffer_index] = current_time
            self._y_buffer[self._buffer_index] = new_data
            
            self._buffer_index = (self._buffer_index + 1) % self.histogram_range
            if self._buffer_index == 0:
                self._buffer_full = True
            
            # Update plot with valid data
            if self._buffer_full:
                # Use the entire circular buffer
                x_data = np.concatenate([
                    self._x_buffer[self._buffer_index:],
                    self._x_buffer[:self._buffer_index]
                ])
                y_data = np.concatenate([
                    self._y_buffer[self._buffer_index:],
                    self._y_buffer[:self._buffer_index]
                ])
            else:
                # Use only filled portion
                x_data = self._x_buffer[:self._buffer_index]
                y_data = self._y_buffer[:self._buffer_index]
            
            # Remove NaN values and update plot
            valid_mask = ~np.isnan(y_data)
            self.curve.setData(x_data[valid_mask], y_data[valid_mask])
            
        except Exception as e:
            print(f"Error updating plot: {e}") 