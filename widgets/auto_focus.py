"""
Auto-focus widgets for the Napari Scanning SPD application.

Contains:
- Auto-focus control widget
- Signal bridge for thread-safe GUI updates
- Focus plot widget creation function
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
    
    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self.update_focus_plot_signal.connect(self._update_focus_plot)
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


def auto_focus(counter, binwidth, signal_bridge):
    """Factory function to create auto_focus widget with dependencies"""
    
    @magicgui(call_button="🔍 Auto Focus")
    def _auto_focus():
        """Automatically find the optimal Z position by scanning for maximum signal"""
        def run_auto_focus():
            try:
                show_info('🔍 Starting Z scan...')
                piezo = PiezoController()
                
                if not piezo.connect():
                    show_info('❌ Failed to connect to piezo stage')
                    return
                
                try:
                    # Get count data using the counter
                    count_function = lambda: counter.getData()[0][0]/(binwidth/1e12)
                    positions, counts, optimal_pos = piezo.perform_auto_focus(count_function)
                    
                    show_info(f'✅ Focus optimized at Z = {optimal_pos} µm')
                    signal_bridge.update_focus_plot_signal.emit(positions, counts, 'Auto-Focus Plot')
                    
                finally:
                    piezo.disconnect()
                
            except Exception as e:
                show_info(f'❌ Auto-focus error: {str(e)}')
        
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
        A widget containing the focus plot
    """
    plot_widget = SingleAxisPlot()
    plot_widget.plot_data(
        x_data=positions,
        y_data=counts,
        x_label='Z Position (µm)',
        y_label='Counts',
        title='Auto-Focus Results',
        peak_annotation=f'Optimal: {positions[np.argmax(counts)]:.2f} µm' if len(counts) > 0 else None
    )
    return plot_widget 