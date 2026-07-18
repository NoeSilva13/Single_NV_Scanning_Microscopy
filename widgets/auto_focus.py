"""
Z-axis scan widget for the Napari Scanning SPD application.

Contains a self-contained ``AutoFocusWidget`` (pyqtgraph) with a "Scan Z"
button and result plot, plus the hardware-timed linear Z-sweep logic.
Z range, resolution and dwell time come from the Scan Parameters panel
(``scan_params_manager``), not from fields on this widget.
"""

import threading

import numpy as np
import pyqtgraph as pg
from qtpy.QtCore import Signal as pyqtSignal
from qtpy.QtWidgets import QWidget, QVBoxLayout, QPushButton
from napari.utils.notifications import show_info

from scanning_core import run_hardware_timed_sweep, counts_to_rate


def _sweep_phase(tagger, z_controller, positions, rate, stage,
                 plot_callback, stop_check, task_ref, cbm_ref, lock):
    """Run one hardware-timed Z sweep over ``positions`` and return count rates.

    The positions (micrometers) are converted to EXT IN voltages and clocked
    out on the piezo analog-output channel; CountBetweenMarkers counts photons
    between clock edges (one value per position). ``plot_callback`` is called
    during the sweep with the accumulated ``(stage, positions, rates)`` so the
    caller can plot the data in real time.
    """
    voltages = np.array([[z_controller.position_to_voltage(p) for p in positions]])

    def _on_progress(counts, bin_widths):
        if plot_callback is None:
            return
        done = int(np.count_nonzero(np.asarray(bin_widths) > 0))
        done = min(done, len(positions))
        if done > 0:
            rates = counts_to_rate(counts, bin_widths)
            plot_callback(stage, list(positions[:done]), list(rates[:done]))

    counts, bin_widths = run_hardware_timed_sweep(
        tagger,
        [z_controller.ao_channel],
        voltages,
        rate,
        on_progress=_on_progress,
        stop_check=stop_check,
        task_ref=task_ref,
        cbm_ref=cbm_ref,
        lock=lock,
    )
    return counts_to_rate(counts, bin_widths)


def run_z_sweep(tagger,
                z_controller,
                positions,
                dwell_time,
                plot_callback=None,
                stop_check=None,
                task_ref=None,
                cbm_ref=None,
                lock=None):
    """Run a single hardware-timed linear Z sweep.

    Parameters
    ----------
    tagger : TimeTagger.TimeTagger
        Time Tagger instance.
    z_controller : DAQZController
        Controller exposing ``position_to_voltage``, ``set_position(um)``,
        ``max_travel`` and ``ao_channel``.
    positions : sequence of float
        Z positions in micrometers to visit (e.g. from ``np.linspace``).
    dwell_time : float
        Per-point integration time in seconds (clock period = ``1/dwell_time``).
    plot_callback : Optional[Callable[[str, list, list], None]]
        Called during the sweep with ``(stage, positions, rates)`` accumulated
        so far, for real-time plotting.
    stop_check : Optional[Callable[[], bool]]
        Returns True to abort the sweep early.
    task_ref, cbm_ref, lock :
        Passed through to ``run_hardware_timed_sweep`` for Stop integration.

    Returns
    -------
    Tuple[list, list]
        (positions, count_rates)
    """
    positions = list(positions)
    if not positions:
        return [], []

    rate = 1.0 / dwell_time
    print(f"Starting Z scan ({len(positions)} points, dwell={dwell_time*1e3:.1f} ms)...")
    rates = _sweep_phase(
        tagger, z_controller, positions, rate, "Z Scan",
        plot_callback, stop_check, task_ref, cbm_ref, lock
    )
    print("Z scan complete.")
    return positions, list(rates)


class AutoFocusWidget(QWidget):
    """Scan Z panel: start button and pyqtgraph result plot.

    Parameters (Z min/max, resolution, dwell) are read from
    ``scan_params_manager`` (Scan Parameters widget), not from this UI.
    The sweep does not move the piezo to the peak; it leaves Z at the last
    commanded point of the ramp (Z max).
    """

    # Cross-thread signals (emitted from the worker, handled on the main thread).
    _live_signal = pyqtSignal(str, list, list)
    _plot_signal = pyqtSignal(list, list)
    _notify_signal = pyqtSignal(str)
    _zupdate_signal = pyqtSignal()
    _finished_signal = pyqtSignal()

    def __init__(self, tagger, z_controller, scan_params_manager,
                 scan_lock, scan_in_progress, stop_scan_requested,
                 scan_task_ref, cbm_ref,
                 bg_color='#262930', parent=None):
        super().__init__(parent)
        self.tagger = tagger
        self.z_controller = z_controller
        self.scan_params_manager = scan_params_manager
        self.scan_lock = scan_lock
        self.scan_in_progress = scan_in_progress
        self.stop_scan_requested = stop_scan_requested
        self.scan_task_ref = scan_task_ref
        self.cbm_ref = cbm_ref
        # Optional piezo control widget refreshed after a successful scan.
        self.z_control_widget = None

        self._live_signal.connect(self._on_live)
        self._plot_signal.connect(self._on_plot)
        self._notify_signal.connect(show_info)
        self._zupdate_signal.connect(self._on_zupdate)
        self._finished_signal.connect(self._on_finished)

        self._build_ui(bg_color)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self, bg_color):
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        self.setLayout(layout)

        self.focus_btn = QPushButton('🔍 Scan Z')
        self.focus_btn.clicked.connect(self._start)
        layout.addWidget(self.focus_btn)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground(bg_color)
        self.plot_item = self.plot_widget.getPlotItem()
        self.plot_item.showGrid(x=True, y=True, alpha=0.3)
        self.plot_item.setLabel('bottom', 'Z Position (µm)', color='white')
        self.plot_item.setLabel('left', 'Counts', color='white')
        for axis_name in ('left', 'bottom'):
            axis = self.plot_item.getAxis(axis_name)
            axis.setTextPen('white')
            axis.setPen('white')
        self.curve = self.plot_item.plot(
            [], [], pen=pg.mkPen('#00ff00', width=1),
            symbol='o', symbolSize=5, symbolBrush='#00ff00'
        )
        self.peak_marker = self.plot_item.plot(
            [], [], pen=None, symbol='o', symbolSize=12,
            symbolBrush=None, symbolPen=pg.mkPen('red', width=2)
        )
        # Let the plot expand to fill the tab so the Z tab matches X/Y.
        self.plot_widget.setMinimumHeight(160)
        layout.addWidget(self.plot_widget)

    # ------------------------------------------------------------------
    # Worker control
    # ------------------------------------------------------------------
    def _start(self):
        if self.scan_in_progress[0]:
            show_info('⚠️ A scan is already in progress')
            return
        self.focus_btn.setEnabled(False)
        # Clear previous traces so the new sweep plots from scratch in real time.
        self.curve.setData([], [])
        self.peak_marker.setData([], [])
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        # Acquire exclusive access to the DAQ AO engine / Time Tagger clock.
        with self.scan_lock:
            if self.scan_in_progress[0]:
                self._notify_signal.emit('⚠️ A scan is already in progress')
                self._finished_signal.emit()
                return
            self.scan_in_progress[0] = True
            self.stop_scan_requested[0] = False

        try:
            self._notify_signal.emit('🔍 Starting Z scan...')

            if not self.z_controller.available:
                self._notify_signal.emit('❌ Z control via DAQ not available')
                return

            params = self.scan_params_manager.get_params()
            z_scan = params['z_scan']
            z_min, z_max = z_scan['range']
            z_res = int(z_scan['resolution'])
            dwell_time = float(z_scan['dwell_time'])

            if z_max <= z_min:
                self._notify_signal.emit('❌ Z Max must be greater than Z Min')
                return
            if z_res < 2:
                self._notify_signal.emit('❌ Z Resolution must be at least 2')
                return

            positions = np.linspace(z_min, z_max, z_res)

            def plot_callback(stage, pos, rates):
                self._live_signal.emit(stage, pos, rates)

            positions, rates = run_z_sweep(
                self.tagger,
                self.z_controller,
                positions,
                dwell_time,
                plot_callback=plot_callback,
                stop_check=lambda: self.stop_scan_requested[0],
                task_ref=self.scan_task_ref,
                cbm_ref=self.cbm_ref,
                lock=self.scan_lock,
            )

            self._plot_signal.emit(list(positions), list(rates))

            if self.stop_scan_requested[0]:
                self._notify_signal.emit('🛑 Z scan stopped by user')
                return

            # Leave the piezo at the end of the ramp (Z max); do not move to peak.
            if positions:
                self.z_controller.set_position(positions[-1])
                self._zupdate_signal.emit()

            peak_x, _ = self._peak(positions, rates)
            if peak_x is not None:
                self._notify_signal.emit(
                    f'✅ Z scan done. Peak at Z = {peak_x:.2f} µm'
                )
            else:
                self._notify_signal.emit('✅ Z scan done')

        except Exception as e:
            self._notify_signal.emit(f'❌ Z scan error: {str(e)}')
        finally:
            with self.scan_lock:
                self.scan_in_progress[0] = False
            self._finished_signal.emit()

    # ------------------------------------------------------------------
    # Main-thread slots
    # ------------------------------------------------------------------
    def _on_live(self, stage, positions, rates):
        """Plot accumulated points in real time."""
        self.curve.setData(positions, rates)
        self._refresh_peak_marker()

    def _on_plot(self, positions, rates):
        self.curve.setData(positions, rates)
        self._refresh_peak_marker()

    def _refresh_peak_marker(self):
        """Mark the peak of the Z curve."""
        peak_x, peak_y = self._peak(*self.curve.getData())
        if peak_x is None:
            self.peak_marker.setData([], [])
        else:
            self.peak_marker.setData([peak_x], [peak_y])

    def _on_zupdate(self):
        if self.z_control_widget is not None:
            self.z_control_widget._update_ui_with_current_position()

    def _on_finished(self):
        self.focus_btn.setEnabled(True)

    @staticmethod
    def _peak(x, y):
        if x is None or y is None:
            return None, None
        arr = np.asarray(y, dtype=float)
        if arr.size == 0 or np.all(np.isnan(arr)):
            return None, None
        idx = int(np.nanargmax(arr))
        return float(x[idx]), float(arr[idx])
