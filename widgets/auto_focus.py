"""
Auto-focus widget for the Napari Scanning SPD application.

Contains a single self-contained ``AutoFocusWidget`` (pyqtgraph) that bundles
the dwell-time control, the "Auto Focus" button, a progress bar, and the
coarse/fine result plot, plus the hardware-timed Z-sweep logic.
"""

import threading

import numpy as np
import pyqtgraph as pg
from qtpy.QtCore import Signal as pyqtSignal
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QPushButton,
    QDoubleSpinBox, QLabel, QSizePolicy
)
from napari.utils.notifications import show_info

from scanning_core import run_hardware_timed_sweep, counts_to_rate

# Default auto-focus sweep parameters (micrometers). These are only initial
# values for the widget's fields; the user edits them live from the UI.
DEFAULT_COARSE_STEP = 5.0   # Step size for the coarse focus scan
DEFAULT_FINE_STEP = 0.5     # Step size for the fine focus scan
DEFAULT_FINE_RANGE = 10.0   # Span around the coarse peak for the fine scan


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


def run_focus_sweep(tagger,
                    z_controller,
                    dwell_time,
                    plot_callback=None,
                    coarse_step=DEFAULT_COARSE_STEP,
                    fine_step=DEFAULT_FINE_STEP,
                    fine_range=DEFAULT_FINE_RANGE,
                    stop_check=None,
                    task_ref=None,
                    cbm_ref=None,
                    lock=None):
    """Find the optimal Z position with hardware-timed piezo sweeps.

    Performs a coarse sweep over the full travel followed by a fine sweep
    around the coarse peak. Each sweep is a finite hardware-timed analog-output
    ramp on the piezo channel, with photon counts acquired per point by the
    Time Tagger's CountBetweenMarkers (bins defined by the DAQ clock).

    Parameters
    ----------
    tagger : TimeTagger.TimeTagger
        Time Tagger instance.
    z_controller : DAQZController
        Controller exposing ``position_to_voltage``, ``set_position(um)``,
        ``max_travel`` and ``ao_channel``.
    dwell_time : float
        Per-point integration time in seconds (clock period = ``1/dwell_time``).
    plot_callback : Optional[Callable[[str, list, list], None]]
        Called during each phase with ``(stage, positions, rates)`` accumulated
        so far, for real-time plotting.
    coarse_step, fine_step, fine_range : float
        Sweep parameters in micrometers.
    stop_check : Optional[Callable[[], bool]]
        Returns True to abort the sweep early.
    task_ref, cbm_ref, lock :
        Passed through to ``run_hardware_timed_sweep`` for Stop integration.

    Returns
    -------
    Tuple[list, list, list, list, float]
        (coarse_positions, coarse_counts, fine_positions, fine_counts, optimal_position)
    """
    max_pos = z_controller.max_travel
    rate = 1.0 / dwell_time

    # Coarse sweep positions across the full travel.
    coarse_positions = []
    pos = 0.0
    while pos <= max_pos:
        coarse_positions.append(pos)
        pos += coarse_step

    print("Starting coarse auto-focus scan...")
    coarse_counts = _sweep_phase(
        tagger, z_controller, coarse_positions, rate, "Coarse Scan",
        plot_callback, stop_check, task_ref, cbm_ref, lock
    )

    if stop_check is not None and stop_check():
        return coarse_positions, list(coarse_counts), [], [], coarse_positions[int(np.argmax(coarse_counts))]

    coarse_optimal_pos = coarse_positions[int(np.argmax(coarse_counts))]
    print(f"Coarse scan complete. Peak found at {coarse_optimal_pos:.1f} µm")

    # Fine sweep around the coarse peak.
    print("Starting fine-tuning scan...")
    fine_start = max(0.0, coarse_optimal_pos - fine_range / 2)
    fine_end = min(max_pos, coarse_optimal_pos + fine_range / 2)

    fine_positions = []
    fine_pos = fine_start
    while fine_pos <= fine_end:
        fine_positions.append(fine_pos)
        fine_pos += fine_step

    fine_counts = _sweep_phase(
        tagger, z_controller, fine_positions, rate, "Fine Scan",
        plot_callback, stop_check, task_ref, cbm_ref, lock
    )

    optimal_pos = fine_positions[int(np.argmax(fine_counts))]
    print(f"Fine scan complete. Refined peak found at {optimal_pos:.2f} µm")

    # Move to the final optimal position (ephemeral single write on ao2).
    z_controller.set_position(optimal_pos)
    print(f"Auto-focus complete. Final position: {optimal_pos:.2f} µm")

    return (coarse_positions, list(coarse_counts),
            fine_positions, list(fine_counts), optimal_pos)


class AutoFocusWidget(QWidget):
    """Self-contained auto-focus panel: dwell control, button, progress and plot.

    The piezo objective settles far slower than the galvos (~25 ms for a
    1-100 µm step per the datasheet), so this widget uses its own dwell time
    (default 25 ms), independent of the scan ``dwell_time``.
    """

    # Cross-thread signals (emitted from the worker, handled on the main thread).
    _live_signal = pyqtSignal(str, list, list)
    _plot_signal = pyqtSignal(list, list, list, list)
    _notify_signal = pyqtSignal(str)
    _zupdate_signal = pyqtSignal()
    _finished_signal = pyqtSignal()

    def __init__(self, tagger, z_controller, scan_lock, scan_in_progress,
                 stop_scan_requested, scan_task_ref, cbm_ref,
                 default_dwell_ms=25.0,
                 default_coarse_step=DEFAULT_COARSE_STEP,
                 default_fine_step=DEFAULT_FINE_STEP,
                 default_fine_range=DEFAULT_FINE_RANGE,
                 bg_color='#262930', parent=None):
        super().__init__(parent)
        self.tagger = tagger
        self.z_controller = z_controller
        self.scan_lock = scan_lock
        self.scan_in_progress = scan_in_progress
        self.stop_scan_requested = stop_scan_requested
        self.scan_task_ref = scan_task_ref
        self.cbm_ref = cbm_ref
        # Optional piezo control widget refreshed after a successful focus.
        self.z_control_widget = None

        self._live_signal.connect(self._on_live)
        self._plot_signal.connect(self._on_plot)
        self._notify_signal.connect(show_info)
        self._zupdate_signal.connect(self._on_zupdate)
        self._finished_signal.connect(self._on_finished)

        self._build_ui(default_dwell_ms, default_coarse_step,
                       default_fine_step, default_fine_range, bg_color)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self, default_dwell_ms, default_coarse_step,
                  default_fine_step, default_fine_range, bg_color):
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        self.setLayout(layout)

        # Controls: parameters in a 2x2 grid (left), start button (right column).
        controls = QGridLayout()
        controls.setSpacing(6)

        self.dwell_spin = QDoubleSpinBox()
        self.dwell_spin.setRange(1.0, 2000.0)
        self.dwell_spin.setSingleStep(1.0)
        self.dwell_spin.setValue(default_dwell_ms)
        self.dwell_spin.setMaximumWidth(110)
        self.dwell_spin.setToolTip('Per-point dwell time; allow the piezo to settle')
        self.coarse_step_spin = self._make_um_spin(
            default_coarse_step, 'Coarse step across the full travel (µm)')
        self.fine_step_spin = self._make_um_spin(
            default_fine_step, 'Fine step around the coarse peak (µm)')
        self.fine_range_spin = self._make_um_spin(
            default_fine_range, 'Fine sweep span around the coarse peak (µm)')

        # Row 0
        controls.addWidget(QLabel('Dwell (ms):'), 0, 0)
        controls.addWidget(self.dwell_spin, 0, 1)
        controls.addWidget(QLabel('Coarse (µm):'), 0, 2)
        controls.addWidget(self.coarse_step_spin, 0, 3)
        # Row 1
        controls.addWidget(QLabel('Fine (µm):'), 1, 0)
        controls.addWidget(self.fine_step_spin, 1, 1)
        controls.addWidget(QLabel('Range (µm):'), 1, 2)
        controls.addWidget(self.fine_range_spin, 1, 3)

        # Second column: the start button spanning both rows
        self.focus_btn = QPushButton('🔍 Scan Z')
        self.focus_btn.clicked.connect(self._start)
        self.focus_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        controls.addWidget(self.focus_btn, 0, 4, 2, 1)

        # Give the extra horizontal space to the button's column so it widens.
        controls.setColumnStretch(4, 1)
        layout.addLayout(controls)

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
        self.plot_item.addLegend(offset=(10, 10))
        self.coarse_curve = self.plot_item.plot(
            [], [], pen=pg.mkPen('#90a4ae', width=1),
            symbol='o', symbolSize=5, symbolBrush='#90a4ae', name='Coarse'
        )
        self.fine_curve = self.plot_item.plot(
            [], [], pen=pg.mkPen('#00ff00', width=1),
            symbol='o', symbolSize=5, symbolBrush='#00ff00', name='Fine'
        )
        self.peak_marker = self.plot_item.plot(
            [], [], pen=None, symbol='o', symbolSize=12,
            symbolBrush=None, symbolPen=pg.mkPen('red', width=2)
        )
        # Let the plot expand to fill the tab so the Z tab matches X/Y.
        self.plot_widget.setMinimumHeight(160)
        layout.addWidget(self.plot_widget)

    @staticmethod
    def _make_um_spin(value, tooltip):
        spin = QDoubleSpinBox()
        # 3 decimals -> 0.001 µm (1 nm) steps; the piezo resolves down to ~3 nm.
        spin.setRange(0.001, 1000.0)
        spin.setSingleStep(0.001)
        spin.setDecimals(3)
        spin.setValue(value)
        spin.setMaximumWidth(110)
        spin.setToolTip(tooltip)
        return spin

    # ------------------------------------------------------------------
    # Worker control
    # ------------------------------------------------------------------
    def _start(self):
        if self.scan_in_progress[0]:
            show_info('⚠️ A scan is already in progress')
            return
        dwell_ms = self.dwell_spin.value()
        coarse_step = self.coarse_step_spin.value()
        fine_step = self.fine_step_spin.value()
        fine_range = self.fine_range_spin.value()
        self.focus_btn.setEnabled(False)
        # Clear previous traces so the new sweep plots from scratch in real time.
        self.coarse_curve.setData([], [])
        self.fine_curve.setData([], [])
        self.peak_marker.setData([], [])
        threading.Thread(
            target=self._run,
            args=(dwell_ms, coarse_step, fine_step, fine_range),
            daemon=True,
        ).start()

    def _run(self, dwell_ms, coarse_step, fine_step, fine_range):
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

            # Independent piezo dwell (ms -> s) to allow the slow piezo to settle.
            dwell_time = dwell_ms / 1000.0

            def plot_callback(stage, positions, rates):
                self._live_signal.emit(stage, positions, rates)

            coarse_pos, coarse_counts, fine_pos, fine_counts, optimal = run_focus_sweep(
                self.tagger,
                self.z_controller,
                dwell_time,
                plot_callback=plot_callback,
                coarse_step=coarse_step,
                fine_step=fine_step,
                fine_range=fine_range,
                stop_check=lambda: self.stop_scan_requested[0],
                task_ref=self.scan_task_ref,
                cbm_ref=self.cbm_ref,
                lock=self.scan_lock,
            )

            self._plot_signal.emit(
                list(coarse_pos), list(coarse_counts), list(fine_pos), list(fine_counts)
            )

            if self.stop_scan_requested[0]:
                self._notify_signal.emit('🛑 Auto-focus stopped by user')
                return

            self._notify_signal.emit(f'✅ Focus optimized at Z = {optimal:.2f} µm')
            self._zupdate_signal.emit()

        except Exception as e:
            self._notify_signal.emit(f'❌ Auto-focus error: {str(e)}')
        finally:
            with self.scan_lock:
                self.scan_in_progress[0] = False
            self._finished_signal.emit()

    # ------------------------------------------------------------------
    # Main-thread slots
    # ------------------------------------------------------------------
    def _on_live(self, stage, positions, rates):
        """Plot accumulated points for the active phase in real time."""
        if stage.startswith('Fine'):
            self.fine_curve.setData(positions, rates)
        else:
            self.coarse_curve.setData(positions, rates)
        self._refresh_peak_marker()

    def _on_plot(self, coarse_pos, coarse_counts, fine_pos, fine_counts):
        self.coarse_curve.setData(coarse_pos, coarse_counts)
        self.fine_curve.setData(fine_pos, fine_counts)
        self._refresh_peak_marker()

    def _refresh_peak_marker(self):
        """Mark the peak of the fine curve, falling back to the coarse curve."""
        peak_x, peak_y = self._peak(*self.fine_curve.getData())
        if peak_x is None:
            peak_x, peak_y = self._peak(*self.coarse_curve.getData())
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
