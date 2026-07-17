"""
Auto-focus widgets for the Napari Scanning SPD application.

Contains:
- Auto-focus control widget
- Signal bridge for thread-safe GUI updates
- Focus plot widget creation function
- Progress bar for auto-focus process
"""

import threading
import time
import numpy as np
from qtpy.QtCore import QObject, Signal as pyqtSignal
from magicgui import magicgui
from napari.utils.notifications import show_info
from plot_widgets.single_axis_plot import SingleAxisPlot
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





def run_focus_sweep(z_controller,
                    count_function,
                    progress_callback=None,
                    coarse_step=PIEZO_COARSE_STEP,
                    fine_step=PIEZO_FINE_STEP,
                    fine_range=PIEZO_FINE_RANGE,
                    settling_time=0.1):
    """Find the optimal Z position by sweeping the piezo and measuring counts.

    Performs a coarse sweep over the full travel followed by an optional fine
    sweep around the coarse peak. Movement is delegated to ``z_controller``
    (which commands the piezo via DAQ analog output), keeping this routine
    hardware-agnostic.

    Parameters
    ----------
    z_controller : DAQZController
        Controller exposing ``set_position(um)`` and ``max_travel``.
    count_function : Callable[[], float]
        Returns the current photon count/count-rate.
    progress_callback : Optional[Callable[[int, int, str, float, float], None]]
        Signature: (current_step, total_steps, stage, position, counts).
    coarse_step, fine_step, fine_range : float
        Sweep parameters in micrometers.
    settling_time : float
        Seconds to wait after each move before measuring.

    Returns
    -------
    Tuple[list, list, list, list, float]
        (coarse_positions, coarse_counts, fine_positions, fine_counts, optimal_position)
    """
    max_pos = z_controller.max_travel

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
    current_step = 0

    coarse_counts = []
    print("Starting coarse auto-focus scan...")
    for coarse_pos in coarse_positions:
        z_controller.set_position(coarse_pos)
        time.sleep(settling_time)
        count = count_function()
        coarse_counts.append(count)
        current_step += 1
        if progress_callback:
            progress_callback(current_step, total_steps, "Coarse Scan", coarse_pos, count)

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

    fine_counts = []
    for i, position in enumerate(fine_positions):
        z_controller.set_position(position)
        time.sleep(settling_time)
        count = count_function()
        fine_counts.append(count)
        current_step = total_coarse_steps + i + 1
        if progress_callback:
            progress_callback(current_step, total_steps, "Fine Scan", position, count)

    optimal_pos = fine_positions[int(np.argmax(fine_counts))]
    print(f"Fine scan complete. Refined peak found at {optimal_pos:.2f} µm")

    # Move to the final optimal position.
    z_controller.set_position(optimal_pos)
    time.sleep(settling_time)
    if progress_callback:
        progress_callback(
            total_steps, total_steps, "Complete", optimal_pos, max(fine_counts)
        )
    print(f"Auto-focus complete. Final position: {optimal_pos:.2f} µm")

    return coarse_positions, coarse_counts, fine_positions, fine_counts, optimal_pos


def auto_focus(counter, binwidth, signal_bridge, z_controller):
    """Factory function to create auto_focus widget with dependencies
    
    Parameters
    ----------
    counter : TimeTagger.Counter
        Counter object for photon counting
    binwidth : int
        Bin width for photon counting
    signal_bridge : SignalBridge
        Bridge for thread-safe GUI updates
    z_controller : DAQZController
        DAQ-based Z (piezo) controller instance (required)
    """
    
    @magicgui(call_button="🔍 Auto Focus")
    def _auto_focus():
        """Automatically find the optimal Z position by scanning for maximum signal"""
        def run_auto_focus():
            try:
                signal_bridge.notify_signal.emit('🔍 Starting Z scan...')
                signal_bridge.show_progress_signal.emit()
                
                if not z_controller.available:
                    signal_bridge.notify_signal.emit('❌ Z control via DAQ not available')
                    signal_bridge.hide_progress_signal.emit()
                    return
                
                try:
                    # Create progress callback function
                    def progress_callback(current_step, total_steps, stage, position=None, counts=None):
                        progress_percent = int((current_step / total_steps) * 100)
                        if position is not None and counts is not None:
                            status_text = f'{stage}: Position {position:.1f} µm, Counts: {counts:.0f}'
                        else:
                            status_text = f'{stage}: Step {current_step}/{total_steps}'
                        signal_bridge.update_progress_signal.emit(progress_percent, status_text)
                    
                    # Get count data using the counter
                    count_function = lambda: counter.getData()[0][0]/(binwidth/1e12)
                    coarse_pos, coarse_counts, fine_pos, fine_counts, optimal_pos = run_focus_sweep(
                        z_controller,
                        count_function,
                        progress_callback=progress_callback
                    )
                    
                    signal_bridge.notify_signal.emit(f'✅ Focus optimized at Z = {optimal_pos} µm')
                    signal_bridge.update_focus_plot_signal.emit(
                        coarse_pos, coarse_counts, fine_pos, fine_counts, 'Auto-Focus Plot'
                    )
                    signal_bridge.update_z_control_signal.emit()  # Update Z control widget
                    
                finally:
                    signal_bridge.hide_progress_signal.emit()
                
            except Exception as e:
                signal_bridge.notify_signal.emit(f'❌ Auto-focus error: {str(e)}')
                signal_bridge.hide_progress_signal.emit()
        
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