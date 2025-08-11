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
from PyQt5.QtCore import QObject, pyqtSignal
from magicgui import magicgui
from napari.utils.notifications import show_info
from piezo_controller import PiezoController
from plot_widgets.single_axis_plot import SingleAxisPlot


class SignalBridge(QObject):
    """Bridge to safely create and add widgets from background threads"""
    update_focus_plot_signal = pyqtSignal(list, list, str)
    update_progress_signal = pyqtSignal(int, str)
    show_progress_signal = pyqtSignal()
    hide_progress_signal = pyqtSignal()
    
    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self.update_focus_plot_signal.connect(self._update_focus_plot)
        self.update_progress_signal.connect(self._update_progress)
        self.show_progress_signal.connect(self._show_progress)
        self.hide_progress_signal.connect(self._hide_progress)
        self.focus_plot_widget = None
        self.focus_dock_widget = None
    
    def _update_focus_plot(self, positions, counts, name):
        """Update the focus plot widget from the main thread"""
        # Create plot widget if it doesn't exist
        if self.focus_plot_widget is None:
            self.focus_plot_widget = create_focus_plot_widget(positions, counts)
            self.focus_dock_widget = self.viewer.window.add_dock_widget(
                self.focus_plot_widget, 
                area='right', 
                name=name
            )
        else:
            # Update existing plot
            self.focus_plot_widget.plot_data(
                x_data=positions,
                y_data=counts,
                x_label='Z Position (µm)',
                y_label='Counts',
                title='Auto-Focus Results',
                peak_annotation=f'Optimal: {positions[np.argmax(counts)]:.2f} µm' if len(counts) > 0 else None
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





def auto_focus(counter, binwidth, signal_bridge):
    """Factory function to create auto_focus widget with dependencies"""
    
    @magicgui(call_button="🔍 Auto Focus")
    def _auto_focus():
        """Automatically find the optimal Z position by scanning for maximum signal"""
        def run_auto_focus():
            try:
                show_info('🔍 Starting Z scan...')
                signal_bridge.show_progress_signal.emit()
                
                piezo = PiezoController()
                
                if not piezo.connect():
                    show_info('❌ Failed to connect to piezo stage')
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
                    positions, counts, optimal_pos = piezo.perform_auto_focus(
                        count_function, 
                        progress_callback=progress_callback
                    )
                    
                    show_info(f'✅ Focus optimized at Z = {optimal_pos} µm')
                    signal_bridge.update_focus_plot_signal.emit(positions, counts, 'Auto-Focus Plot')
                    
                finally:
                    piezo.disconnect()
                    signal_bridge.hide_progress_signal.emit()
                
            except Exception as e:
                show_info(f'❌ Auto-focus error: {str(e)}')
                signal_bridge.hide_progress_signal.emit()
        
        threading.Thread(target=run_auto_focus, daemon=True).start()
    
    return _auto_focus


def create_focus_plot_widget(positions, counts):
    """
    Creates a plot widget to display auto-focus results using SingleAxisPlot
    
    Parameters
    ----------
    positions : list
        Z positions scanned during auto-focus
    counts : list
        Photon counts measured at each position
    
    Returns
    -------
    SingleAxisPlot
        A widget containing the focus plot with integrated progress bar
    """
    plot_widget = SingleAxisPlot(show_progress_bar=True)
    plot_widget.plot_data(
        x_data=positions,
        y_data=counts,
        x_label='Z Position (µm)',
        y_label='Counts',
        title='Auto-Focus Results',
        peak_annotation=f'Optimal: {positions[np.argmax(counts)]:.2f} µm' if len(counts) > 0 else None
    )
    return plot_widget 