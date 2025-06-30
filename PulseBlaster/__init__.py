"""
PulseBlaster Package - Swabian Pulse Streamer 8/2 Controller
-----------------------------------------------------------
ODMR pulse generation control for NV center experiments.

This package provides comprehensive control over the Swabian Pulse Streamer 8/2
for generating precise pulse sequences required in ODMR experiments with 
Nitrogen-Vacancy (NV) centers.

Author: Javier Noé Ramos Silva
Contact: jramossi@uci.edu
Lab: Burke Lab, Department of Electrical Engineering and Computer Science, University of California, Irvine
Date: 2025
"""

try:
    from .swabian_pulse_streamer import SwabianPulseController
    from .rigol_dsg836 import RigolDSG836Controller
    from .odmr_experiments import ODMRExperiments
    
    __all__ = ['SwabianPulseController', 'RigolDSG836Controller', 'ODMRExperiments']
    
except ImportError as e:
    print(f"Warning: Could not import all PulseBlaster modules: {e}")
    print("Make sure the pulsestreamer library is installed: pip install pulsestreamer")
    
    __all__ = []

__version__ = "1.0.0"
__author__ = "Javier Noé Ramos Silva"
__email__ = "jramossi@uci.edu" 