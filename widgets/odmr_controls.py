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


def launch_odmr_gui(tagger=None, counter=None, binwidth=None):
    """Factory function to create launch_odmr_gui widget with TimeTagger sharing"""
    
    @magicgui(call_button="📡 Launch ODMR")
    def _launch_odmr_gui():
        """Launches the ODMR GUI Qt application in a separate window.
        Uses the ODMRControlCenter from odmr_gui_qt.py with shared TimeTagger instance.
        """
        try:
            # Import the ODMR GUI classes
            from odmr_gui_qt import ODMRControlCenter
            from PyQt5.QtWidgets import QApplication
            
            # Check if QApplication exists, if not create one
            app = QApplication.instance()
            if app is None:
                app = QApplication(sys.argv)
            
            # Create and show the ODMR GUI with shared TimeTagger
            odmr_window = ODMRControlCenter(shared_tagger=tagger)
            odmr_window.show()
            
            show_info("📡 ODMR GUI launched successfully with shared TimeTagger!")
            
        except ImportError as e:
            show_info(f"❌ Error importing ODMR GUI: {str(e)}")
            # Fallback to subprocess method
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
                show_info("📡 ODMR GUI launched as separate process!")
                
            except Exception as e2:
                show_info(f"❌ Error launching ODMR GUI: {str(e2)}")
            
        except Exception as e:
            show_info(f"❌ Error launching ODMR GUI: {str(e)}")
    
    return _launch_odmr_gui 