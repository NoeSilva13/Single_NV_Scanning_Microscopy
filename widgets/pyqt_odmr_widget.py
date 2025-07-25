"""
Pure PyQt ODMR control widget for the microscopy control software.
"""

import subprocess
import sys
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton
from PyQt5.QtCore import QThread, pyqtSignal


class ODMRLaunchThread(QThread):
    """Background thread for launching ODMR GUI"""
    
    launch_complete = pyqtSignal(bool, str)  # success, message
    
    def __init__(self, tagger=None, counter=None, binwidth=None):
        super().__init__()
        self.tagger = tagger
        self.counter = counter
        self.binwidth = binwidth
    
    def run(self):
        """Launch ODMR GUI in background"""
        try:
            # Launch the ODMR GUI as a separate process
            subprocess.Popen([sys.executable, "odmr_gui_qt.py"])
            self.launch_complete.emit(True, "📡 ODMR GUI launched successfully")
        except Exception as e:
            self.launch_complete.emit(False, f"❌ Error launching ODMR GUI: {str(e)}")


class ODMRControlWidget(QWidget):
    """Pure PyQt ODMR control widget"""
    
    def __init__(self, tagger=None, counter=None, binwidth=None, parent=None):
        super().__init__(parent)
        self.tagger = tagger
        self.counter = counter
        self.binwidth = binwidth
        self.launch_thread = None
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout()
        
        self.launch_button = QPushButton("📡 Launch ODMR")
        self.launch_button.setFixedSize(150, 50)
        self.launch_button.clicked.connect(self.launch_odmr)
        
        layout.addWidget(self.launch_button)
        self.setLayout(layout)
    
    def launch_odmr(self):
        """Launch ODMR GUI"""
        if self.launch_thread and self.launch_thread.isRunning():
            return
        
        self.launch_button.setEnabled(False)
        self.launch_button.setText("Launching...")
        
        self.launch_thread = ODMRLaunchThread(self.tagger, self.counter, self.binwidth)
        self.launch_thread.launch_complete.connect(self.on_launch_complete)
        self.launch_thread.start()
    
    def on_launch_complete(self, success, message):
        """Handle launch completion"""
        print(message)
        self.launch_button.setEnabled(True)
        self.launch_button.setText("📡 Launch ODMR")


def create_odmr_control_widget(tagger=None, counter=None, binwidth=None):
    """Factory function to create ODMR control widget"""
    return ODMRControlWidget(tagger, counter, binwidth) 