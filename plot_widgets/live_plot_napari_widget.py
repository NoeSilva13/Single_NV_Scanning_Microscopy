"""
live_plot_napari_widget
========================================================================
A napari-compatible widget for live plotting of measurements with overflow
detection, built on pyqtgraph for fast real-time updates.

Provides lightweight user controls: pause/resume, clear, refresh rate,
window length (number of points), autoscale toggle and log-Y toggle.
"""

from collections import deque
from time import time

import numpy as np
import pyqtgraph as pg
from qtpy.QtCore import QTimer, Qt
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QSpinBox, QCheckBox, QLabel
)


class LivePlotNapariWidget(QWidget):
    def __init__(
        self,
        measure_function,
        histogram_range=100,
        dt=100,  # dt in milliseconds
        widget_height=250,
        figsize=(4, 2),  # kept for backward compatibility (unused with pyqtgraph)
        bg_color='#262930',
        plot_color='#00ff00',
        alarm_color='#ff0000',
        parent=None
    ):
        super().__init__(parent)
        self.measure_function = measure_function
        self.histogram_range = int(histogram_range)
        self.bg_color = bg_color
        self.plot_color = plot_color
        self.alarm_color = alarm_color
        self.overflow_detected = False
        self._dt_ms = int(dt)

        self.setMinimumHeight(widget_height)

        # Ring buffers for the rolling window
        self.x_data = deque(maxlen=self.histogram_range)
        self.y_data = deque(maxlen=self.histogram_range)
        self.t0 = time()

        self._build_ui()

        # Update timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(self._dt_ms)

    # --------------------------------------------------------------
    # UI
    # --------------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)
        self.setLayout(layout)

        layout.addLayout(self._build_controls())

        # pyqtgraph plot
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground(self.bg_color)
        self.plot_item = self.plot_widget.getPlotItem()
        self.plot_item.showGrid(x=True, y=True, alpha=0.3)
        self.plot_item.setLabel('bottom', 'Time (s)', color='white')
        self.plot_item.setLabel('left', 'Signal', color='white')
        for axis_name in ('left', 'bottom'):
            axis = self.plot_item.getAxis(axis_name)
            axis.setTextPen('white')
            axis.setPen('white')
        self.curve = self.plot_item.plot(pen=pg.mkPen(self.plot_color, width=1))

        # Overflow banner drawn over the plot, centered
        self.overflow_text = pg.TextItem('OVERFLOW', color='white', anchor=(0.5, 0.5))
        self.overflow_text.setVisible(False)
        self.plot_item.addItem(self.overflow_text)

        layout.addWidget(self.plot_widget)

        self._apply_autoscale()
        self._apply_log_mode()

    def _build_controls(self):
        controls = QHBoxLayout()
        controls.setSpacing(6)

        self.pause_btn = QPushButton('Pause')
        self.pause_btn.setCheckable(True)
        self.pause_btn.toggled.connect(self._on_pause_toggled)
        controls.addWidget(self.pause_btn)

        self.clear_btn = QPushButton('Clear')
        self.clear_btn.clicked.connect(self.clear)
        controls.addWidget(self.clear_btn)

        controls.addWidget(QLabel('Refresh (ms):'))
        self.refresh_spin = QSpinBox()
        self.refresh_spin.setRange(10, 5000)
        self.refresh_spin.setSingleStep(10)
        self.refresh_spin.setValue(self._dt_ms)
        self.refresh_spin.valueChanged.connect(self._on_refresh_changed)
        controls.addWidget(self.refresh_spin)

        controls.addWidget(QLabel('Window:'))
        self.window_spin = QSpinBox()
        self.window_spin.setRange(10, 100000)
        self.window_spin.setSingleStep(10)
        self.window_spin.setValue(self.histogram_range)
        self.window_spin.valueChanged.connect(self._on_window_changed)
        controls.addWidget(self.window_spin)

        self.autoscale_chk = QCheckBox('Auto Y')
        self.autoscale_chk.setChecked(True)
        self.autoscale_chk.toggled.connect(self._apply_autoscale)
        controls.addWidget(self.autoscale_chk)

        self.log_chk = QCheckBox('Log Y')
        self.log_chk.setChecked(False)
        self.log_chk.toggled.connect(self._apply_log_mode)
        controls.addWidget(self.log_chk)

        self.status_label = QLabel('')
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        controls.addWidget(self.status_label, stretch=1)

        return controls

    # --------------------------------------------------------------
    # Control callbacks
    # --------------------------------------------------------------
    def _on_pause_toggled(self, paused):
        if paused:
            self.timer.stop()
            self.pause_btn.setText('Resume')
        else:
            self.timer.start(self._dt_ms)
            self.pause_btn.setText('Pause')

    def _on_refresh_changed(self, value):
        self._dt_ms = int(value)
        if self.timer.isActive():
            self.timer.start(self._dt_ms)

    def _on_window_changed(self, value):
        self.histogram_range = int(value)
        # Recreate ring buffers preserving the most recent samples
        self.x_data = deque(self.x_data, maxlen=self.histogram_range)
        self.y_data = deque(self.y_data, maxlen=self.histogram_range)

    def _apply_autoscale(self, *_):
        self.plot_item.enableAutoRange('y', self.autoscale_chk.isChecked())

    def _apply_log_mode(self, *_):
        self.plot_item.setLogMode(y=self.log_chk.isChecked())

    # --------------------------------------------------------------
    # Data update
    # --------------------------------------------------------------
    def update_plot(self):
        try:
            result = self.measure_function()

            if isinstance(result, tuple) and len(result) == 2:
                new_data, overflow = result
                self.overflow_detected = bool(overflow)
            else:
                new_data = result
                self.overflow_detected = False

            self.x_data.append(time() - self.t0)
            self.y_data.append(new_data)

            self.curve.setData(np.fromiter(self.x_data, dtype=float),
                               np.fromiter(self.y_data, dtype=float))

            self._update_overflow_alarm()
        except Exception as e:
            print(f"Error updating plot: {e}")

    def _update_overflow_alarm(self):
        """Show/hide the overflow banner and status text."""
        if self.overflow_detected:
            self.status_label.setText('OVERFLOW')
            self.status_label.setStyleSheet(f'color: {self.alarm_color}; font-weight: bold;')
            # Center the banner in the current view
            view_range = self.plot_item.viewRange()
            cx = (view_range[0][0] + view_range[0][1]) / 2
            cy = (view_range[1][0] + view_range[1][1]) / 2
            self.overflow_text.setColor(self.alarm_color)
            self.overflow_text.setPos(cx, cy)
            self.overflow_text.setVisible(True)
        else:
            self.status_label.setText('')
            self.overflow_text.setVisible(False)

    def clear(self):
        """Clear the current plot data."""
        self.x_data.clear()
        self.y_data.clear()
        self.curve.setData([], [])
        self.overflow_detected = False
        self.overflow_text.setVisible(False)
        self.status_label.setText('')

    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)


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
    Creates a LivePlotNapariWidget that updates with new measurements.

    Parameters
    ---------------------------------------------------------------------------------
    measure_function : callable
        Function returning a data point, or a tuple (value, overflow_flag).
    histogram_range : int
        Number of points shown in the rolling window (adjustable in the UI).
    dt : float
        Time between updates in seconds (converted to milliseconds internally;
        adjustable in the UI).
    widget_height : int
        Minimum height of the widget in pixels.
    figsize : tuple
        Kept for backward compatibility (unused with pyqtgraph).
    bg_color : str
        Background color of the plot.
    plot_color : str
        Color of the plot line.
    alarm_color : str
        Color of the overflow alarm.

    Returns
    ---------------------------------------------------------------------------------
    LivePlotNapariWidget
        A Qt widget that can be added to napari's viewer.
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
