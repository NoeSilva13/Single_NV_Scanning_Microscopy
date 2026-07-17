"""
Single axis scan widget for the Napari Scanning SPD application.

Contains the SingleAxisScanWidget class for performing 1D scans along X or Y axis.
"""

import threading
import numpy as np
from nidaqmx.constants import TaskMode
from qtpy.QtWidgets import QWidget, QPushButton, QGridLayout
from qtpy.QtCore import Signal as pyqtSignal
from napari.utils.notifications import show_info
from plot_widgets.single_axis_plot import SingleAxisPlot
from scanning_core import run_hardware_timed_sweep, counts_to_rate


class SingleAxisScanWidget(QWidget):
    """Widget for performing single axis scans at current cursor position"""
    _plot_ready_signal = pyqtSignal(dict)

    def __init__(self, scan_params_manager, layer, output_task, tagger,
                 galvo_controller, scan_lock, scan_in_progress,
                 stop_scan_requested, scan_task_ref, cbm_ref, parent=None):
        super().__init__(parent)
        self._plot_ready_signal.connect(self._on_plot_ready)
        self.scan_params_manager = scan_params_manager
        self.layer = layer
        self.output_task = output_task
        self.tagger = tagger
        self.galvo_controller = galvo_controller
        self.scan_lock = scan_lock
        self.scan_in_progress = scan_in_progress
        self.stop_scan_requested = stop_scan_requested
        self.scan_task_ref = scan_task_ref
        self.cbm_ref = cbm_ref
        
        # Track current scanner position internally (default to center)
        self.current_x_voltage = 0.0
        self.current_y_voltage = 0.0
        
        layout = QGridLayout()
        layout.setSpacing(5)
        self.setLayout(layout)
        
        # Create buttons for X and Y scans
        self.x_scan_btn = QPushButton("⬌ X-Axis Scan")
        self.y_scan_btn = QPushButton("⬍ Y-Axis Scan")
        
        # Add widgets to layout
        layout.addWidget(self.x_scan_btn, 0, 0)
        layout.addWidget(self.y_scan_btn, 0, 1)
        
        # Connect buttons
        self.x_scan_btn.clicked.connect(lambda: self.start_scan('x'))
        self.y_scan_btn.clicked.connect(lambda: self.start_scan('y'))
        
        # Create plot widget
        self.plot_widget = SingleAxisPlot()
        layout.addWidget(self.plot_widget, 1, 0, 1, 2)
        
        # Initialize plot with zeros
        self._initialize_plot()
        
        # Set fixed height for better appearance
        self.setFixedHeight(300)
    
    def _initialize_plot(self):
        """Initialize the plot with current config values"""
        params = self.scan_params_manager.get_params()
        x_range = params['scan_range']['x']
        x_res = params['resolution']['x']
        
        x_data = np.linspace(x_range[0], x_range[1], x_res)
        y_data = np.zeros(x_res)
        self.plot_widget.plot_data(
            x_data=x_data,
            y_data=y_data,
            x_label='Position (V)',
            y_label='Counts',
            title='Single Axis Scan',
            mark_peak=False
        )
    
    def update_current_position(self, x_voltage, y_voltage):
        """Update the current scanner position"""
        self.current_x_voltage = x_voltage
        self.current_y_voltage = y_voltage
        
    def get_current_position(self):
        """Get the current scanner position from internal tracking"""
        return self.current_x_voltage, self.current_y_voltage
    
    def start_scan(self, axis):
        """Start a hardware-timed single axis scan using CountBetweenMarkers."""
        x_pos, y_pos = self.get_current_position()

        # Get current parameter values
        params = self.scan_params_manager.get_params()
        x_range = params['scan_range']['x']
        y_range = params['scan_range']['y']
        x_res = params['resolution']['x']
        y_res = params['resolution']['y']
        dwell_time = params['dwell_time']

        # Build the scanned-axis points and the constant fixed-axis waveform.
        if axis == 'x':
            scan_points = np.linspace(x_range[0], x_range[1], x_res)
            x_waveform = scan_points
            y_waveform = np.full(len(scan_points), y_pos)
            axis_label = 'X Position (V)'
        else:  # y-axis
            scan_points = np.linspace(y_range[0], y_range[1], y_res)
            x_waveform = np.full(len(scan_points), x_pos)
            y_waveform = scan_points
            axis_label = 'Y Position (V)'

        def run_scan():
            # Acquire exclusive access to the DAQ AO engine / Time Tagger clock.
            with self.scan_lock:
                if self.scan_in_progress[0]:
                    show_info('⚠️ A scan is already in progress')
                    return
                self.scan_in_progress[0] = True
                self.stop_scan_requested[0] = False

            try:
                # Release the galvo channels from the persistent on-demand task.
                self.output_task.stop()
                self.output_task.control(TaskMode.TASK_UNRESERVE)

                counts, bin_widths = run_hardware_timed_sweep(
                    self.tagger,
                    [self.galvo_controller.xin_control,
                     self.galvo_controller.yin_control],
                    np.array([x_waveform, y_waveform]),
                    1.0 / dwell_time,
                    stop_check=lambda: self.stop_scan_requested[0],
                    task_ref=self.scan_task_ref,
                    cbm_ref=self.cbm_ref,
                    lock=self.scan_lock,
                )

                if self.stop_scan_requested[0]:
                    show_info('🛑 Single-axis scan stopped by user')
                    return

                count_rates = counts_to_rate(counts, bin_widths)
                self._plot_ready_signal.emit({
                    'x_data': scan_points,
                    'y_data': count_rates,
                    'x_label': axis_label,
                    'y_label': 'Counts',
                    'title': f'Single Axis Scan ({axis.upper()})',
                    'mark_peak': True
                })

            except Exception as e:
                show_info(f'❌ Single-axis scan error: {str(e)}')
            finally:
                # Restore the persistent on-demand galvo task and original position.
                try:
                    self.output_task.start()
                    self.output_task.write([x_pos, y_pos])
                except Exception as e:
                    show_info(f'⚠️ Failed to restart galvo control: {e}')
                with self.scan_lock:
                    self.scan_in_progress[0] = False

        threading.Thread(target=run_scan, daemon=True).start()
        show_info(f"🔍 Starting {axis.upper()}-axis scan...")

    def _on_plot_ready(self, plot_args):
        """Update plot widget on the main thread"""
        self.plot_widget.plot_data(**plot_args) 