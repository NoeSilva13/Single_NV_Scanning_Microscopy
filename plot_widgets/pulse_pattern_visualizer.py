from PyQt5.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QGroupBox
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
import numpy as np

class PulsePatternVisualizer(QWidget):
    """
    A widget for visualizing pulse patterns based on user-defined parameters.
    Shows the timing of laser, microwave, and detection pulses for ODMR experiments.
    """
    def __init__(
        self,
        widget_height=300,
        figsize=(8, 3),
        bg_color='#262930',
        parent=None
    ):
        super().__init__(parent)
        self.bg_color = bg_color
        self.figsize = figsize
        
        # Setup widget
        self.setFixedHeight(widget_height)
        self._setup_layout()
        self._create_figure()
        
    def _setup_layout(self):
        """Initialize the widget layout"""
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(5)
        self.setLayout(self.layout)
        
    def _create_figure(self):
        """Create and setup the matplotlib figure"""
        self.fig = Figure(figsize=self.figsize, facecolor=self.bg_color)
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.ax = self.fig.add_subplot(111)
        
        # Style the plot for dark theme
        self.ax.set_facecolor(self.bg_color)
        self.ax.tick_params(colors='white')
        for spine in self.ax.spines.values():
            spine.set_color('white')
            
        # Add the canvas to the layout
        self.layout.addWidget(self.canvas)
        
    def update_pulse_pattern(self, parameters):
        """
        Update the pulse pattern visualization based on the provided parameters.
        
        Parameters
        ----------
        parameters : dict
            Dictionary containing pulse timing parameters:
            - laser_duration: Duration of laser pulse (ns)
            - mw_duration: Duration of microwave pulse (ns)
            - detection_duration: Duration of detection window (ns)
            - laser_delay: Delay before laser pulse (ns)
            - mw_delay: Delay before microwave pulse (ns)
            - detection_delay: Delay before detection window (ns)
            - sequence_interval: Time between sequence repetitions (ns)
        """
        # Clear previous plot
        self.ax.clear()
        
        # Extract parameters with defaults
        laser_duration = float(parameters.get('laser_duration', 2000))
        mw_duration = float(parameters.get('mw_duration', 2000))
        detection_duration = float(parameters.get('detection_duration', 1000))
        laser_delay = float(parameters.get('laser_delay', 0))
        mw_delay = float(parameters.get('mw_delay', 0))
        detection_delay = float(parameters.get('detection_delay', 0))
        sequence_interval = float(parameters.get('sequence_interval', 10000))
        
        # Calculate timing
        laser_start = laser_delay
        laser_end = laser_start + laser_duration
        
        mw_start = laser_start + mw_delay
        mw_end = mw_start + mw_duration
        
        detection_start = laser_start + detection_delay
        detection_end = detection_start + detection_duration
        
        # Set up the plot
        self.ax.set_xlim(0, sequence_interval)
        self.ax.set_ylim(0, 4)
        
        # Plot laser pulse
        self.ax.fill_between([laser_start, laser_end], 0, 1, 
                           color='#ff6b6b', alpha=0.8, label='Laser (AOM)')
        self.ax.text((laser_start + laser_end) / 2, 0.5, 'LASER', 
                    ha='center', va='center', color='white', fontweight='bold', fontsize=10)
        
        # Plot microwave pulse
        self.ax.fill_between([mw_start, mw_end], 1, 2, 
                           color='#9c27b0', alpha=0.8, label='Microwave (MW)')
        self.ax.text((mw_start + mw_end) / 2, 1.5, 'MW', 
                    ha='center', va='center', color='white', fontweight='bold', fontsize=10)
        
        # Plot detection window
        self.ax.fill_between([detection_start, detection_end], 2, 3, 
                           color='#45b7d1', alpha=0.8, label='Detection (SPD)')
        self.ax.text((detection_start + detection_end) / 2, 2.5, 'DETECT', 
                    ha='center', va='center', color='white', fontweight='bold', fontsize=10)
        
        # Add timeline markers
        time_points = [0, laser_start, laser_end, mw_start, mw_end, detection_start, detection_end, sequence_interval]
        time_points = sorted(list(set(time_points)))  # Remove duplicates and sort
        
        for t in time_points:
            if t <= sequence_interval:
                self.ax.axvline(x=t, color='#666666', linestyle='--', alpha=0.5, linewidth=0.5)
                self.ax.text(t, 3.5, f'{int(t)}', ha='center', va='bottom', 
                           color='#cccccc', fontsize=8, rotation=45)
        
        # Style the plot
        self.ax.set_xlabel('Time (ns)', color='white', fontsize=10)
        self.ax.set_ylabel('Channels', color='white', fontsize=10)
        self.ax.set_title('ODMR Pulse Sequence', color='white', fontsize=12, fontweight='bold')
        
        # Set y-axis ticks
        self.ax.set_yticks([0.5, 1.5, 2.5])
        self.ax.set_yticklabels(['Laser', 'Microwave', 'Detection'])
        self.ax.tick_params(colors='white')
        
        # Add grid
        self.ax.grid(True, alpha=0.2, color='#666666')
        
        # Add legend
        self.ax.legend(loc='upper right', framealpha=0.8, facecolor=self.bg_color, 
                      edgecolor='white', fontsize=8)
        
        # Adjust layout
        self.fig.tight_layout()
        self.canvas.draw()
        
    def clear(self):
        """Clear the plot"""
        self.ax.clear()
        self.ax.set_facecolor(self.bg_color)
        self.ax.tick_params(colors='white')
        for spine in self.ax.spines.values():
            spine.set_color('white')
        self.canvas.draw() 