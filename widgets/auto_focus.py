"""
Auto-focus widgets for the Napari Scanning SPD application.

Contains:
- Auto-focus control widget
- Signal bridge for thread-safe GUI updates
- Focus plot widget creation function
- Progress bar for auto-focus process
"""

import threading
import numpy as np
from qtpy.QtCore import QObject, Signal as pyqtSignal
from magicgui import magicgui
from napari.utils.notifications import show_info
from plot_widgets.single_axis_plot import SingleAxisPlot
from scanning_core import run_hardware_timed_sweep, counts_to_rate
from utils import PIEZO_COARSE_STEP, PIEZO_FINE_STEP, PIEZO_FINE_RANGE


class SignalBridge(QObject):
    """Bridge to safely create and add widgets from background threads"""
    # Payload: coarse_pos, coarse_counts, fine_pos, fine_counts, dock_name
    update_focus_plot_signal = pyqtSignal(list, list, list, list, str)
    update_progress_signal = pyqtSignal(int, str)
    show_progress_signal = pyqtSignal()
    hide_progress_signal = pyqtSignal()
    update_z_control_signal = pyqtSignal()
    notify_signal = pyqtSignal(str)
    
    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self.update_focus_plot_signal.connect(self._update_focus_plot)
        self.update_progress_signal.connect(self._update_progress)
        self.show_progress_signal.connect(self._show_progress)
        self.hide_progress_signal.connect(self._hide_progress)
        self.update_z_control_signal.connect(self._update_z_control)
        self.notify_signal.connect(self._on_notify)
        self.focus_plot_widget = None
        self.focus_dock_widget = None
        self.z_control_widget = None
    
    def _update_focus_plot(self, coarse_pos, coarse_counts, fine_pos, fine_counts, name):
        """Update the focus plot widget from the main thread"""
        # Create plot widget if it doesn't exist
        if self.focus_plot_widget is None:
            self.focus_plot_widget = create_focus_plot_widget(
                coarse_pos, coarse_counts, fine_pos, fine_counts
            )
            self.focus_dock_widget = self.viewer.window.add_dock_widget(
                self.focus_plot_widget, 
                area='right', 
                name=name
            )
        else:
            _plot_focus_results(
                self.focus_plot_widget, coarse_pos, coarse_counts, fine_pos, fine_counts
            )
    
    def _update_progress(self, value, text):
        """Update the progress bar from the main thread"""
        if self.focus_plot_widget and hasattr(self.focus_plot_widget, 'update_progress'):
            self.focus_plot_widget.update_progress(value, text)
    
    def _show_progress(self):
        """Show the progress bar from the main thread"""
        if self.focus_plot_widget and hasattr(self.focus_plot_widget, 'show_progress'):
            self.focus_plot_widget.show_progress()
    
    def _hide_progress(self):
        """Hide the progress bar from the main thread"""
        if self.focus_plot_widget and hasattr(self.focus_plot_widget, 'hide_progress'):
            self.focus_plot_widget.hide_progress()
    
    def _update_z_control(self):
        """Update the Z control widget from the main thread"""
        if self.z_control_widget:
            self.z_control_widget._update_ui_with_current_position()

    def _on_notify(self, msg):
        """Show notification on the main thread"""
        show_info(msg)





def _sweep_phase(tagger, z_controller, positions, rate, stage,
                 base_step, total_steps, progress_callback,
                 stop_check, task_ref, cbm_ref, lock):
    """Run one hardware-timed Z sweep over ``positions`` and return count rates.

    The positions (micrometers) are converted to EXT IN voltages and clocked
    out on the piezo analog-output channel; CountBetweenMarkers counts photons
    between clock edges (one value per position).
    """
    voltages = np.array([[z_controller.position_to_voltage(p) for p in positions]])

    def _on_progress(counts, bin_widths):
        if progress_callback is None:
            return
        done = int(np.count_nonzero(np.asarray(bin_widths) > 0))
        done = min(done, len(positions))
        if done > 0:
            rates = counts_to_rate(counts, bin_widths)
            idx = done - 1
            progress_callback(base_step + done, total_steps, stage,
                              positions[idx], rates[idx])

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
                    progress_callback=None,
                    coarse_step=PIEZO_COARSE_STEP,
                    fine_step=PIEZO_FINE_STEP,
                    fine_range=PIEZO_FINE_RANGE,
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
    progress_callback : Optional[Callable[[int, int, str, float, float], None]]
        Signature: (current_step, total_steps, stage, position, counts).
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

    total_coarse_steps = len(coarse_positions)
    # Rough estimate of fine steps for the initial progress total.
    total_fine_steps = int(fine_range / fine_step) + 1
    total_steps = total_coarse_steps + total_fine_steps

    print("Starting coarse auto-focus scan...")
    coarse_counts = _sweep_phase(
        tagger, z_controller, coarse_positions, rate, "Coarse Scan",
        0, total_steps, progress_callback, stop_check, task_ref, cbm_ref, lock
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

    total_fine_steps = len(fine_positions)
    total_steps = total_coarse_steps + total_fine_steps

    fine_counts = _sweep_phase(
        tagger, z_controller, fine_positions, rate, "Fine Scan",
        total_coarse_steps, total_steps, progress_callback,
        stop_check, task_ref, cbm_ref, lock
    )

    optimal_pos = fine_positions[int(np.argmax(fine_counts))]
    print(f"Fine scan complete. Refined peak found at {optimal_pos:.2f} µm")

    # Move to the final optimal position (ephemeral single write on ao2).
    z_controller.set_position(optimal_pos)
    if progress_callback:
        progress_callback(
            total_steps, total_steps, "Complete", optimal_pos, float(np.max(fine_counts))
        )
    print(f"Auto-focus complete. Final position: {optimal_pos:.2f} µm")

    return (coarse_positions, list(coarse_counts),
            fine_positions, list(fine_counts), optimal_pos)


def auto_focus(tagger, scan_params_manager, signal_bridge, z_controller,
               scan_lock, scan_in_progress, stop_scan_requested,
               scan_task_ref, cbm_ref):
    """Factory function to create the auto_focus widget with dependencies.

    Parameters
    ----------
    tagger : TimeTagger.TimeTagger
        Time Tagger instance (used to build CountBetweenMarkers).
    scan_params_manager : ScanParametersManager
        Source of the shared ``dwell_time`` used as the per-point clock period.
    signal_bridge : SignalBridge
        Bridge for thread-safe GUI updates.
    z_controller : DAQZController
        DAQ-based Z (piezo) controller instance (required).
    scan_lock, scan_in_progress, stop_scan_requested, scan_task_ref, cbm_ref :
        Shared concurrency primitives, so the sweep is mutually exclusive with
        the 2D raster / single-axis scans and the Stop button can abort it.
    """

    @magicgui(call_button="🔍 Auto Focus")
    def _auto_focus():
        """Automatically find the optimal Z position by scanning for maximum signal"""
        def run_auto_focus():
            # Acquire exclusive access to the DAQ AO engine / Time Tagger clock.
            with scan_lock:
                if scan_in_progress[0]:
                    signal_bridge.notify_signal.emit('⚠️ A scan is already in progress')
                    return
                scan_in_progress[0] = True
                stop_scan_requested[0] = False

            try:
                signal_bridge.notify_signal.emit('🔍 Starting Z scan...')
                signal_bridge.show_progress_signal.emit()

                if not z_controller.available:
                    signal_bridge.notify_signal.emit('❌ Z control via DAQ not available')
                    return

                dwell_time = scan_params_manager.get_params()['dwell_time']

                def progress_callback(current_step, total_steps, stage, position=None, counts=None):
                    progress_percent = int((current_step / total_steps) * 100)
                    if position is not None and counts is not None:
                        status_text = f'{stage}: Position {position:.1f} µm, Counts: {counts:.0f}'
                    else:
                        status_text = f'{stage}: Step {current_step}/{total_steps}'
                    signal_bridge.update_progress_signal.emit(progress_percent, status_text)

                coarse_pos, coarse_counts, fine_pos, fine_counts, optimal_pos = run_focus_sweep(
                    tagger,
                    z_controller,
                    dwell_time,
                    progress_callback=progress_callback,
                    stop_check=lambda: stop_scan_requested[0],
                    task_ref=scan_task_ref,
                    cbm_ref=cbm_ref,
                    lock=scan_lock,
                )

                if stop_scan_requested[0]:
                    signal_bridge.notify_signal.emit('🛑 Auto-focus stopped by user')
                    return

                signal_bridge.notify_signal.emit(f'✅ Focus optimized at Z = {optimal_pos:.2f} µm')
                signal_bridge.update_focus_plot_signal.emit(
                    coarse_pos, coarse_counts, fine_pos, fine_counts, 'Auto-Focus Plot'
                )
                signal_bridge.update_z_control_signal.emit()  # Update Z control widget

            except Exception as e:
                signal_bridge.notify_signal.emit(f'❌ Auto-focus error: {str(e)}')
            finally:
                signal_bridge.hide_progress_signal.emit()
                with scan_lock:
                    scan_in_progress[0] = False

        threading.Thread(target=run_auto_focus, daemon=True).start()

    return _auto_focus


def _plot_focus_results(plot_widget, coarse_pos, coarse_counts, fine_pos, fine_counts):
    """Plot coarse and fine sweeps as separate series (no connecting line)."""
    plot_widget.plot_data(
        x_data=[],
        y_data=[],
        x_label='Z Position (µm)',
        y_label='Counts',
        title='Auto-Focus Results',
        mark_peak=len(fine_counts) > 0 or len(coarse_counts) > 0,
        series=[
            {"x": coarse_pos, "y": coarse_counts, "label": "Coarse", "color": "#90a4ae"},
            {"x": fine_pos, "y": fine_counts, "label": "Fine", "color": "#00ff00"},
        ],
    )


def create_focus_plot_widget(coarse_pos, coarse_counts, fine_pos=None, fine_counts=None):
    """
    Creates a plot widget to display auto-focus results using SingleAxisPlot
    
    Parameters
    ----------
    coarse_pos, coarse_counts : list
        Coarse Z sweep data
    fine_pos, fine_counts : list, optional
        Fine Z sweep data (empty/None until a scan completes)
    
    Returns
    -------
    SingleAxisPlot
        A widget containing the focus plot with integrated progress bar
    """
    if fine_pos is None:
        fine_pos = []
    if fine_counts is None:
        fine_counts = []
    plot_widget = SingleAxisPlot(show_progress_bar=True)
    _plot_focus_results(plot_widget, coarse_pos, coarse_counts, fine_pos, fine_counts)
    return plot_widget 