"""
Single axis scan widget for the Napari Scanning SPD application.

Contains the SingleAxisScanWidget class for performing hardware-timed 1D scans
along the X or Y axis, with a pyqtgraph plot per axis shown in separate tabs.
"""

import threading
import numpy as np
import pyqtgraph as pg
from nidaqmx.constants import TaskMode
from qtpy.QtWidgets import QWidget, QPushButton, QVBoxLayout, QTabWidget
from qtpy.QtCore import Signal as pyqtSignal
from napari.utils.notifications import show_info
from scanning_core import run_hardware_timed_sweep, counts_to_rate
from utils import MICRONS_PER_VOLT


def _um_to_volt(um):
    """Convert galvo positions in micrometers to a clamped ±10 V command."""
    return np.clip(np.asarray(um, dtype=float) / MICRONS_PER_VOLT, -10.0, 10.0)


class SingleAxisScanWidget(QWidget):
    """Widget for performing single axis scans at the current cursor position."""

    _plot_ready_signal = pyqtSignal(str, list, list)
    _finished_signal = pyqtSignal(str)

    def __init__(self, scan_params_manager, layer, output_task, tagger,
                 galvo_controller, scan_lock, scan_in_progress,
                 stop_scan_requested, scan_task_ref, cbm_ref,
                 bg_color='#262930', parent=None):
        super().__init__(parent)
        self._plot_ready_signal.connect(self._on_plot_ready)
        self._finished_signal.connect(self._on_finished)
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

        # Track current scanner position internally, in micrometers.
        self.current_x_um = 0.0
        self.current_y_um = 0.0

        # Per-axis plot handles
        self.curves = {}
        self.peak_markers = {}
        self.scan_btns = {}

        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        self.setLayout(layout)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_axis_tab('x', 'X Position (µm)', bg_color), 'X Axis')
        self.tabs.addTab(self._build_axis_tab('y', 'Y Position (µm)', bg_color), 'Y Axis')
        layout.addWidget(self.tabs)

        self._initialize_plot()
        # Constrain the height so the tabs stay compact and don't stretch to
        # fill extra vertical space in the dock area.
        self.setMinimumHeight(320)
        self.setMaximumHeight(420)

    def add_z_tab(self, widget, title='Z Axis'):
        """Embed an external widget (e.g. the Scan Z / auto-focus panel) as a tab."""
        self.tabs.addTab(widget, title)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_axis_tab(self, axis, x_label, bg_color):
        tab = QWidget()
        v = QVBoxLayout()
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(4)
        tab.setLayout(v)

        arrow = '⬌' if axis == 'x' else '⬍'
        btn = QPushButton(f"{arrow} Scan {axis.upper()}")
        btn.clicked.connect(lambda _=False, a=axis: self.start_scan(a))
        self.scan_btns[axis] = btn
        v.addWidget(btn)

        plot_widget = pg.PlotWidget()
        plot_widget.setBackground(bg_color)
        plot_item = plot_widget.getPlotItem()
        plot_item.showGrid(x=True, y=True, alpha=0.3)
        plot_item.setLabel('bottom', x_label, color='white')
        plot_item.setLabel('left', 'Counts', color='white')
        for axis_name in ('left', 'bottom'):
            ax = plot_item.getAxis(axis_name)
            ax.setTextPen('white')
            ax.setPen('white')
        curve = plot_item.plot(
            [], [], pen=pg.mkPen('#00ff00', width=1),
            symbol='o', symbolSize=5, symbolBrush='#00ff00'
        )
        peak_marker = plot_item.plot(
            [], [], pen=None, symbol='o', symbolSize=12,
            symbolBrush=None, symbolPen=pg.mkPen('red', width=2)
        )
        self.curves[axis] = curve
        self.peak_markers[axis] = peak_marker
        plot_widget.setMinimumHeight(160)
        v.addWidget(plot_widget)
        return tab

    def _initialize_plot(self):
        """Initialize each axis plot with its configured range and zeros."""
        params = self.scan_params_manager.get_params()
        for axis in ('x', 'y'):
            rng = params['scan_range'][axis]
            res = params['resolution'][axis]
            x = list(np.linspace(rng[0], rng[1], res))
            self.curves[axis].setData(x, [0.0] * len(x))
            self.peak_markers[axis].setData([], [])

    # ------------------------------------------------------------------
    # Position tracking
    # ------------------------------------------------------------------
    def update_current_position(self, x_um, y_um):
        """Update the current scanner position (micrometers)."""
        self.current_x_um = x_um
        self.current_y_um = y_um

    def get_current_position(self):
        """Get the current scanner position (micrometers) from internal tracking."""
        return self.current_x_um, self.current_y_um

    # ------------------------------------------------------------------
    # Scan control
    # ------------------------------------------------------------------
    def start_scan(self, axis):
        """Start a hardware-timed single axis scan using CountBetweenMarkers.

        Positions are handled in micrometers and converted to galvo volts only
        when building the DAQ waveform.
        """
        x_pos_um, y_pos_um = self.get_current_position()

        # Get current parameter values (µm canonical)
        params = self.scan_params_manager.get_params()
        x_range = params['scan_range']['x']
        y_range = params['scan_range']['y']
        x_res = params['resolution']['x']
        y_res = params['resolution']['y']
        dwell_time = params['dwell_time']

        # Build the scanned-axis points (µm) and the constant fixed-axis value.
        if axis == 'x':
            scan_points = np.linspace(x_range[0], x_range[1], x_res)
            x_waveform_um = scan_points
            y_waveform_um = np.full(len(scan_points), y_pos_um)
        else:  # y-axis
            scan_points = np.linspace(y_range[0], y_range[1], y_res)
            x_waveform_um = np.full(len(scan_points), x_pos_um)
            y_waveform_um = scan_points

        # Convert to galvo volts at the DAQ boundary.
        x_waveform = _um_to_volt(x_waveform_um)
        y_waveform = _um_to_volt(y_waveform_um)

        # Show the relevant tab and disable its button for feedback.
        self.tabs.setCurrentIndex(0 if axis == 'x' else 1)
        self.scan_btns[axis].setEnabled(False)

        def run_scan():
            # Acquire exclusive access to the DAQ AO engine / Time Tagger clock.
            with self.scan_lock:
                if self.scan_in_progress[0]:
                    show_info('⚠️ A scan is already in progress')
                    self._finished_signal.emit(axis)
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
                self._plot_ready_signal.emit(
                    axis, list(scan_points), list(count_rates)
                )

            except Exception as e:
                show_info(f'❌ Single-axis scan error: {str(e)}')
            finally:
                # Restore the persistent on-demand galvo task and original position.
                try:
                    self.output_task.start()
                    self.output_task.write([float(_um_to_volt(x_pos_um)),
                                            float(_um_to_volt(y_pos_um))])
                except Exception as e:
                    show_info(f'⚠️ Failed to restart galvo control: {e}')
                with self.scan_lock:
                    self.scan_in_progress[0] = False
                self._finished_signal.emit(axis)

        threading.Thread(target=run_scan, daemon=True).start()
        show_info(f"🔍 Starting {axis.upper()}-axis scan...")

    # ------------------------------------------------------------------
    # Main-thread slots
    # ------------------------------------------------------------------
    def _on_plot_ready(self, axis, x_data, y_data):
        """Update the axis plot on the main thread."""
        self.curves[axis].setData(x_data, y_data)
        peak_x, peak_y = self._peak(x_data, y_data)
        if peak_x is None:
            self.peak_markers[axis].setData([], [])
        else:
            self.peak_markers[axis].setData([peak_x], [peak_y])

    def _on_finished(self, axis):
        self.scan_btns[axis].setEnabled(True)

    @staticmethod
    def _peak(x, y):
        arr = np.asarray(y, dtype=float)
        if arr.size == 0 or np.all(np.isnan(arr)):
            return None, None
        idx = int(np.nanargmax(arr))
        return float(x[idx]), float(arr[idx])
