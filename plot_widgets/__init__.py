"""
Plot Widgets Package
------------------
This package contains reusable plotting widgets for the NV scanning microscopy application.
"""

from .single_axis_plot import SingleAxisPlot
from .live_plot_pyqtgraph_widget import live_plot_pyqtgraph as live_plot

__all__ = ['SingleAxisPlot', 'live_plot'] 