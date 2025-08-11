from PyQt5.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QProgressBar, QLabel
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
import numpy as np

class SingleAxisPlot(QWidget):
    """
    A widget for plotting single-axis data with optional peak marking.
    Useful for measurements like auto-focus, where we want to track a signal
    along one axis and potentially mark optimal points.
    """
    def __init__(
        self,
        widget_height=250,
        figsize=(4, 2),
        bg_color='#262930',
        plot_color='#00ff00',
        peak_color='red',
        show_progress_bar=False,
        parent=None
    ):
        super().__init__(parent)
        self.bg_color = bg_color
        self.plot_color = plot_color
        self.peak_color = peak_color
        self.show_progress_bar = show_progress_bar
        
        # Setup widget
        self.setFixedHeight(widget_height)
        self._setup_layout()
        self._create_figure(figsize)
        if show_progress_bar:
            self._create_progress_bar()
        
    def _setup_layout(self):
        """Initialize the widget layout"""
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)
        self.setLayout(self.layout)
        
    def _create_figure(self, figsize):
        """Create and setup the matplotlib figure"""
        self.fig = Figure(figsize=figsize, facecolor=self.bg_color)
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.ax = self.fig.add_subplot(111)
        
        # Style the plot for dark theme
        self.ax.set_facecolor(self.bg_color)
        self.ax.tick_params(colors='white')
        for spine in self.ax.spines.values():
            spine.set_color('white')
            
        # Add the canvas to the layout
        self.layout.addWidget(self.canvas)
    
    def _create_progress_bar(self):
        """Create and setup the progress bar"""
        # Status label
        self.status_label = QLabel('Ready')
        self.status_label.setStyleSheet("QLabel { font-weight: bold; color: white; }")
        self.status_label.setVisible(False)
        self.layout.addWidget(self.status_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat('%p%')
        self.progress_bar.setVisible(False)
        self.layout.addWidget(self.progress_bar)
    
    def show_progress(self):
        """Show the progress bar and status label"""
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setVisible(True)
            self.status_label.setVisible(True)
            self.progress_bar.setValue(0)
            self.status_label.setText('Initializing...')
    
    def hide_progress(self):
        """Hide the progress bar and status label"""
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setVisible(False)
            self.status_label.setVisible(False)
    
    def update_progress(self, value, text):
        """Update the progress bar and status text"""
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setValue(value)
            self.status_label.setText(text)
        
    def plot_data(
        self,
        x_data,
        y_data,
        x_label,
        y_label,
        title,
        mark_peak=True,
        peak_annotation=None,
        clear_previous=True
    ):
        """
        Plot the data and optionally mark the peak.
        
        Parameters
        ----------
        x_data : array-like
            The x-axis data
        y_data : array-like
            The y-axis data
        x_label : str
            Label for x-axis
        y_label : str
            Label for y-axis
        title : str
            Plot title
        mark_peak : bool, optional
            Whether to mark the peak point, by default True
        peak_annotation : str, optional
            Custom annotation for the peak point. If None, will use x-value
        clear_previous : bool, optional
            Whether to clear previous plot, by default True
        """
        if clear_previous:
            self.ax.clear()
            
        # Plot main data
        self.ax.plot(x_data, y_data, 'o-', color=self.plot_color)
        
        # Mark peak if requested
        if mark_peak and len(y_data) > 0:
            peak_idx = np.argmax(y_data)
            peak_x = x_data[peak_idx]
            peak_y = y_data[peak_idx]
            
            # Plot peak point
            self.ax.plot(peak_x, peak_y, 'o', color=self.peak_color, markersize=8)
            
            # Add peak annotation
            if peak_annotation is None:
                peak_annotation = f'Peak: {peak_x:.2f}'
                
            self.ax.annotate(
                peak_annotation,
                xy=(peak_x, peak_y),
                xytext=(10, -20),
                textcoords='offset points',
                color='white',
                arrowprops=dict(arrowstyle='->', color='white')
            )
        
        # Set labels and styling
        self.ax.set_xlabel(x_label, color='white')
        self.ax.set_ylabel(y_label, color='white')
        #self.ax.set_title(title, color='white')
        self.ax.grid(True, color='gray', alpha=0.3)
        
        # Update the plot
        self.fig.tight_layout()
        self.canvas.draw()
        
    def clear(self):
        """Clear the current plot"""
        self.ax.clear()
        self.canvas.draw() 