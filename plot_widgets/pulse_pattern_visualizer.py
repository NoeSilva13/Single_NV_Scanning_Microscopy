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
            - sequence_interval: Time between two complete sequences (ns)
            - repetitions: Number of sequence repetitions (if > 1, shows two sequences)
            
        Notes
        -----
        The sequence length is calculated as max(laser_delay + laser_duration, 
        mw_delay + mw_duration, detection_delay + detection_duration).
        The sequence_interval represents the time between consecutive sequences.
        When repetitions > 1, the second sequence starts at sequence_length + sequence_interval,
        and the total display length is sequence_length + sequence_interval + sequence_length.
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
        repetitions = int(parameters.get('repetitions', 1))
        
        # Calculate timing
        laser_start = laser_delay
        laser_end = laser_start + laser_duration
        
        mw_start = laser_start + mw_delay
        mw_end = mw_start + mw_duration
        
        detection_start = laser_start + detection_delay
        detection_end = detection_start + detection_duration
        
        # Calculate sequence length as max of all pulse end times
        sequence_length = max(laser_end, mw_end, detection_end)
        
        # Determine x-axis range based on repetitions
        if repetitions > 1:
            # Show two complete sequences: sequence_length + sequence_interval + sequence_length
            x_max = sequence_length + sequence_interval + sequence_length
        else:
            # Show just one sequence
            x_max = sequence_length
        
        # Set up the plot
        self.ax.set_xlim(0, x_max)
        self.ax.set_ylim(0, 4)
        
        # Plot laser pulse
        self.ax.fill_between([laser_start, laser_end], 0, 1, 
                           color='#4caf50', alpha=0.8, label='Laser (AOM)')
        self.ax.text((laser_start + laser_end) / 2, 0.5, 'LASER', 
                    ha='center', va='center', color='white', fontweight='bold', fontsize=10)
        
        # Plot microwave pulse
        self.ax.fill_between([mw_start, mw_end], 1, 2, 
                           color='#2196f3', alpha=0.8, label='Microwave (MW)')
        self.ax.text((mw_start + mw_end) / 2, 1.5, 'MW', 
                    ha='center', va='center', color='white', fontweight='bold', fontsize=10)
        
        # Plot detection window
        self.ax.fill_between([detection_start, detection_end], 2, 3, 
                           color='#f44336', alpha=0.8, label='Detection (SPD)')
        self.ax.text((detection_start + detection_end) / 2, 2.5, 'DETECT', 
                    ha='center', va='center', color='white', fontweight='bold', fontsize=10)
        
        # If repetitions > 1, plot second sequence
        if repetitions > 1:
            # Second sequence timing - starts after sequence_interval
            laser_start_2 = sequence_length + sequence_interval
            laser_end_2 = laser_start_2 + laser_duration
            mw_start_2 = laser_start_2 + mw_delay
            mw_end_2 = mw_start_2 + mw_duration
            detection_start_2 = laser_start_2 + detection_delay
            detection_end_2 = detection_start_2 + detection_duration
            
            # Plot second laser pulse (slightly transparent)
            self.ax.fill_between([laser_start_2, laser_end_2], 0, 1, 
                               color='#4caf50', alpha=0.4)
            self.ax.text((laser_start_2 + laser_end_2) / 2, 0.5, 'LASER', 
                        ha='center', va='center', color='white', fontweight='bold', fontsize=8)
            
            # Plot second microwave pulse (slightly transparent)
            self.ax.fill_between([mw_start_2, mw_end_2], 1, 2, 
                               color='#2196f3', alpha=0.4)
            self.ax.text((mw_start_2 + mw_end_2) / 2, 1.5, 'MW', 
                        ha='center', va='center', color='white', fontweight='bold', fontsize=8)
            
            # Plot second detection window (slightly transparent)
            self.ax.fill_between([detection_start_2, detection_end_2], 2, 3, 
                               color='#f44336', alpha=0.4)
            self.ax.text((detection_start_2 + detection_end_2) / 2, 2.5, 'DETECT', 
                        ha='center', va='center', color='white', fontweight='bold', fontsize=8)
        
        # Add timeline markers
        time_points = [0, laser_start, laser_end, mw_start, mw_end, detection_start, detection_end, sequence_length]
        if repetitions > 1:
            time_points.extend([sequence_interval, sequence_length + sequence_interval, 
                              laser_start_2, laser_end_2, mw_start_2, mw_end_2, 
                              detection_start_2, detection_end_2])
        time_points = sorted(list(set(time_points)))  # Remove duplicates and sort
        
        for t in time_points:
            if t <= x_max:
                self.ax.axvline(x=t, color='#666666', linestyle='--', alpha=0.5, linewidth=0.5)
                self.ax.text(t, 3.5, f'{int(t)}', ha='center', va='bottom', 
                           color='#cccccc', fontsize=8, rotation=45)
        
        # Style the plot
        self.ax.set_xlabel('Time (ns)', color='white', fontsize=10)
        self.ax.set_ylabel('Channels', color='white', fontsize=10)
        self.ax.set_title('Pulse Sequence', color='white', fontsize=12, fontweight='bold')
        
        # Set y-axis ticks
        self.ax.set_yticks([0.5, 1.5, 2.5])
        self.ax.set_yticklabels(['Laser', 'Microwave', 'Detection'])
        self.ax.tick_params(colors='white')
        
        # Add grid
        self.ax.grid(True, alpha=0.2, color='#666666')
        
        # Add sequence interval indicator if it's greater than sequence length (only for single sequence)
        if sequence_interval > sequence_length and repetitions == 1:
            # Draw a gap to show the interval
            self.ax.axvspan(sequence_length, sequence_interval, alpha=0.1, color='#666666', 
                           label=f'Interval ({int(sequence_interval - sequence_length)} ns)')
            # Add interval marker
            self.ax.axvline(x=sequence_interval, color='#ff9800', linestyle='-', alpha=0.8, linewidth=2)
            self.ax.text(sequence_interval, 3.5, f'Interval\n{int(sequence_interval)}', 
                        ha='center', va='bottom', color='#ff9800', fontsize=8, fontweight='bold')
            # Update x-axis to show the full interval
            self.ax.set_xlim(0, sequence_interval)
        
        # Add sequence information text
        info_text = f'Seq. Length: {int(sequence_length)} ns'
        if repetitions > 1:
            info_text += f'\nRepetitions: {repetitions}'
        self.ax.text(0.02, 0.90, info_text, transform=self.ax.transAxes, 
                    fontsize=9, color='#cccccc', verticalalignment='top',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor=self.bg_color, alpha=0.8))
        
        # Add legend
        self.ax.legend(loc='upper right', framealpha=0.8, facecolor=self.bg_color, 
                      edgecolor='white', fontsize=8, labelcolor='white')
        
        # Adjust layout
        self.fig.tight_layout()
        self.canvas.draw()
    
    def update_t1_pulse_pattern(self, parameters):
        """
        Update the T1 pulse pattern visualization based on the provided parameters.
        
        Parameters
        ----------
        parameters : dict
            Dictionary containing T1 pulse timing parameters:
            - init_laser_duration: Duration of initialization laser pulse (ns)
            - readout_laser_duration: Duration of readout laser pulse (ns)
            - detection_duration: Duration of detection window (ns)
            - init_laser_delay: Delay before initialization laser pulse (ns)
            - readout_laser_delay: Delay before readout laser pulse (ns)
            - detection_delay: Delay before detection window (ns)
            - sequence_interval: Time between two complete sequences (ns)
            - repetitions: Number of sequence repetitions (if > 1, shows two sequences)
            
        Notes
        -----
        T1 sequence: Init Laser -> Delay -> Readout Laser + Detection
        The sequence length is calculated as max(init_laser_end, readout_laser_end, detection_end).
        The sequence_interval represents the time between consecutive sequences.
        When repetitions > 1, the second sequence starts at sequence_length + sequence_interval,
        and the total display length is sequence_length + sequence_interval + sequence_length.
        """
        # Clear previous plot
        self.ax.clear()
        
        # Extract parameters with defaults
        init_laser_duration = float(parameters.get('init_laser_duration', 1000))
        readout_laser_duration = float(parameters.get('readout_laser_duration', 1000))
        detection_duration = float(parameters.get('detection_duration', 500))
        init_laser_delay = float(parameters.get('init_laser_delay', 0))
        readout_laser_delay = float(parameters.get('readout_laser_delay', 1000))
        detection_delay = float(parameters.get('detection_delay', 1000))
        sequence_interval = float(parameters.get('sequence_interval', 10000))
        repetitions = int(parameters.get('repetitions', 1))
        
        # Calculate timing for T1 sequence
        init_laser_start = init_laser_delay
        init_laser_end = init_laser_start + init_laser_duration
        
        readout_laser_start = init_laser_start + readout_laser_delay
        readout_laser_end = readout_laser_start + readout_laser_duration
        
        detection_start = init_laser_start + detection_delay
        detection_end = detection_start + detection_duration
        
        # Calculate sequence length as max of all pulse end times
        sequence_length = max(init_laser_end, readout_laser_end, detection_end)
        
        # Determine x-axis range based on repetitions
        if repetitions > 1:
            # Show two complete sequences: sequence_length + sequence_interval + sequence_length
            x_max = sequence_length + sequence_interval + sequence_length
        else:
            # Show just one sequence
            x_max = sequence_length
        
        # Set up the plot
        self.ax.set_xlim(0, x_max)
        self.ax.set_ylim(0, 4)
        
        # Plot initialization laser pulse
        self.ax.fill_between([init_laser_start, init_laser_end], 0, 1, 
                           color='#4caf50', alpha=0.8, label='Init Laser')
        self.ax.text((init_laser_start + init_laser_end) / 2, 0.5, 'INIT', 
                    ha='center', va='center', color='white', fontweight='bold', fontsize=10)
        
        # Plot readout laser pulse
        self.ax.fill_between([readout_laser_start, readout_laser_end], 1, 2, 
                           color='#8bc34a', alpha=0.8, label='Readout Laser')
        self.ax.text((readout_laser_start + readout_laser_end) / 2, 1.5, 'READOUT', 
                    ha='center', va='center', color='white', fontweight='bold', fontsize=10)
        
        # Plot detection window
        self.ax.fill_between([detection_start, detection_end], 2, 3, 
                           color='#f44336', alpha=0.8, label='Detection (SPD)')
        self.ax.text((detection_start + detection_end) / 2, 2.5, 'DETECT', 
                    ha='center', va='center', color='white', fontweight='bold', fontsize=10)
        
        # If repetitions > 1, plot second sequence
        if repetitions > 1:
            # Second sequence timing - starts after sequence_length + sequence_interval
            init_laser_start_2 = sequence_length + sequence_interval
            init_laser_end_2 = init_laser_start_2 + init_laser_duration
            readout_laser_start_2 = init_laser_start_2 + readout_laser_delay
            readout_laser_end_2 = readout_laser_start_2 + readout_laser_duration
            detection_start_2 = init_laser_start_2 + detection_delay
            detection_end_2 = detection_start_2 + detection_duration
            
            # Plot second init laser pulse (slightly transparent)
            self.ax.fill_between([init_laser_start_2, init_laser_end_2], 0, 1, 
                               color='#4caf50', alpha=0.4)
            self.ax.text((init_laser_start_2 + init_laser_end_2) / 2, 0.5, 'INIT', 
                        ha='center', va='center', color='white', fontweight='bold', fontsize=8)
            
            # Plot second readout laser pulse (slightly transparent)
            self.ax.fill_between([readout_laser_start_2, readout_laser_end_2], 1, 2, 
                               color='#8bc34a', alpha=0.4)
            self.ax.text((readout_laser_start_2 + readout_laser_end_2) / 2, 1.5, 'READOUT', 
                        ha='center', va='center', color='white', fontweight='bold', fontsize=8)
            
            # Plot second detection window (slightly transparent)
            self.ax.fill_between([detection_start_2, detection_end_2], 2, 3, 
                               color='#f44336', alpha=0.4)
            self.ax.text((detection_start_2 + detection_end_2) / 2, 2.5, 'DETECT', 
                        ha='center', va='center', color='white', fontweight='bold', fontsize=8)
        
        # Add timeline markers
        time_points = [0, init_laser_start, init_laser_end, readout_laser_start, 
                      readout_laser_end, detection_start, detection_end, sequence_length]
        if repetitions > 1:
            time_points.extend([sequence_interval, sequence_length + sequence_interval, 
                              init_laser_start_2, init_laser_end_2, readout_laser_start_2, 
                              readout_laser_end_2, detection_start_2, detection_end_2])
        time_points = sorted(list(set(time_points)))  # Remove duplicates and sort
        
        for t in time_points:
            if t <= x_max:
                self.ax.axvline(x=t, color='#666666', linestyle='--', alpha=0.5, linewidth=0.5)
                self.ax.text(t, 3.5, f'{int(t)}', ha='center', va='bottom', 
                           color='#cccccc', fontsize=8, rotation=45)
        
        # Style the plot
        self.ax.set_xlabel('Time (ns)', color='white', fontsize=10)
        self.ax.set_ylabel('Channels', color='white', fontsize=10)
        self.ax.set_title('T1 Decay Pulse Sequence', color='white', fontsize=12, fontweight='bold')
        
        # Set y-axis ticks
        self.ax.set_yticks([0.5, 1.5, 2.5])
        self.ax.set_yticklabels(['Init Laser', 'Readout Laser', 'Detection'])
        self.ax.tick_params(colors='white')
        
        # Add grid
        self.ax.grid(True, alpha=0.2, color='#666666')
        
        # Add sequence interval indicator if it's greater than sequence length (only for single sequence)
        if sequence_interval > sequence_length and repetitions == 1:
            # Draw a gap to show the interval
            self.ax.axvspan(sequence_length, sequence_interval, alpha=0.1, color='#666666', 
                           label=f'Interval ({int(sequence_interval - sequence_length)} ns)')
            # Add interval marker
            self.ax.axvline(x=sequence_interval, color='#ff9800', linestyle='-', alpha=0.8, linewidth=2)
            self.ax.text(sequence_interval, 3.5, f'Interval\n{int(sequence_interval)}', 
                        ha='center', va='bottom', color='#ff9800', fontsize=8, fontweight='bold')
            # Update x-axis to show the full interval
            self.ax.set_xlim(0, sequence_interval)
        
        # Add sequence information text
        info_text = f'Seq. Length: {int(sequence_length)} ns'
        if sequence_interval > sequence_length:
            info_text += f'\nInterval: {int(sequence_interval)} ns'
        if repetitions > 1:
            info_text += f'\nRepetitions: {repetitions}'
            info_text += f'\nTotal Length: {int(sequence_length + sequence_interval + sequence_length)} ns'
        self.ax.text(0.02, 0.90, info_text, transform=self.ax.transAxes, 
                     fontsize=9, color='#cccccc', verticalalignment='top',
                     bbox=dict(boxstyle='round,pad=0.3', facecolor=self.bg_color, alpha=0.8))
        
        # Add legend
        self.ax.legend(loc='upper right', framealpha=0.8, facecolor=self.bg_color, 
                      edgecolor='white', fontsize=8, labelcolor='white')
        
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