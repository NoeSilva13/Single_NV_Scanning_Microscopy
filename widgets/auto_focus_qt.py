"""
Auto-focus widgets for the Qt-based Scanning SPD application.

Contains:
- Auto-focus control widget
- Signal bridge for thread-safe GUI updates
- Focus plot widget creation function
"""

import threading
import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QPushButton, QWidget, QVBoxLayout
from piezo_controller import PiezoController
from plot_widgets.single_axis_plot import SingleAxisPlot


class SignalBridge(QObject):
    """Bridge to safely create and add widgets from background threads"""
    update_focus_plot_signal = pyqtSignal(list, list, str)
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.update_focus_plot_signal.connect(self._update_focus_plot)
        self.focus_plot_widget = None
        self.focus_dock_widget = None
    
    def _update_focus_plot(self, positions, counts, name):
        """Update the focus plot widget from the main thread"""
        # For Qt implementation, we'll just store the plot data
        # and could display it in a separate window if needed
        if self.focus_plot_widget is None:
            self.focus_plot_widget = create_focus_plot_widget(positions, counts)
            # In a full implementation, you might add this to a dock or show in a dialog
            print(f"Focus plot created with {len(positions)} data points")
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


class AutoFocusWidget(QPushButton):
    """Auto-focus button widget"""
    
    def __init__(self, counter, binwidth, signal_bridge, status_callback=None):
        super().__init__("🔍 Auto Focus")
        self.counter = counter
        self.binwidth = binwidth
        self.signal_bridge = signal_bridge
        self.status_callback = status_callback
        
        # Setup button styling
        self.setStyleSheet("""
            QPushButton {
                background-color: #00d4aa;
                color: #262930;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #00ffcc;
            }
            QPushButton:pressed {
                background-color: #009980;
            }
        """)
        
        self.clicked.connect(self._auto_focus)
    
    def _auto_focus(self):
        """Automatically find the optimal Z position by scanning for maximum signal"""
        def run_auto_focus():
            try:
                if self.status_callback:
                    self.status_callback('🔍 Starting Z scan...')
                
                piezo = PiezoController()
                
                if not piezo.connect():
                    if self.status_callback:
                        self.status_callback('❌ Failed to connect to piezo stage')
                    return
                
                try:
                    # Get count data using the counter
                    count_function = lambda: self.counter.getData()[0][0]/(self.binwidth/1e12)
                    positions, counts, optimal_pos = piezo.perform_auto_focus(count_function)
                    
                    if self.status_callback:
                        self.status_callback(f'✅ Focus optimized at Z = {optimal_pos} µm')
                    self.signal_bridge.update_focus_plot_signal.emit(positions, counts, 'Auto-Focus Plot')
                    
                finally:
                    piezo.disconnect()
                
            except Exception as e:
                if self.status_callback:
                    self.status_callback(f'❌ Auto-focus error: {str(e)}')
        
        threading.Thread(target=run_auto_focus, daemon=True).start()


def auto_focus(counter, binwidth, signal_bridge, status_callback=None):
    """Factory function to create auto_focus widget with dependencies"""
    return AutoFocusWidget(counter, binwidth, signal_bridge, status_callback)


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