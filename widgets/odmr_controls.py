"""
ODMR control widgets for the Napari Scanning SPD application.

Contains magicgui widgets for:
- Launching ODMR GUI in separate window
"""

import sys
import subprocess
import os
from PyQt5.QtWidgets import QApplication
from magicgui import magicgui
from napari.utils.notifications import show_info


def launch_odmr_gui():
    """Factory function to create launch_odmr_gui widget"""
    
    @magicgui(call_button="📡 Launch ODMR")
    def _launch_odmr_gui():
        """Launches the ODMR GUI Qt application in a separate window.
        Uses the ODMRControlCenter from odmr_gui_qt.py.
        """
        try:
            # Get the current directory where the main script is located
            current_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(current_dir)  # Go up one level to get to project root
            odmr_script_path = os.path.join(parent_dir, "odmr_gui_qt.py")
            
            if not os.path.exists(odmr_script_path):
                show_info("❌ ODMR GUI script not found!")
                return
            
            # Launch the ODMR GUI as a separate process
            # This prevents it from blocking the main Napari application
            subprocess.Popen([sys.executable, odmr_script_path])
            show_info("📡 ODMR GUI launched successfully!")
            
        except Exception as e:
            show_info(f"❌ Error launching ODMR GUI: {str(e)}")
    
    return _launch_odmr_gui 