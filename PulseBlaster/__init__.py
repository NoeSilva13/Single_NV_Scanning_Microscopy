"""
PulseBlaster Package - Swabian Pulse Streamer 8/2 Controller
-----------------------------------------------------------
ODMR pulse generation control for NV center experiments.

This package provides comprehensive control over the Swabian Pulse Streamer 8/2
for generating precise pulse sequences required in ODMR experiments with 
Nitrogen-Vacancy (NV) centers.

Author: NV Lab
Date: 2025
"""

try:
    from .swabian_pulse_streamer import SwabianPulseController
    from .odmr_experiments import ODMRExperiments
    
    __all__ = ['SwabianPulseController', 'ODMRExperiments']
    
except ImportError as e:
    print(f"Warning: Could not import all PulseBlaster modules: {e}")
    print("Make sure the pulsestreamer library is installed: pip install pulsestreamer")
    
    __all__ = []

__version__ = "1.0.0"
__author__ = "NV Lab"
__email__ = "your.email@institution.edu" 