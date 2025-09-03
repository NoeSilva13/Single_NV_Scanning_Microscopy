"""
Z Scan Controller Module for Confocal Microscopy
-----------------------------------------------
This module handles Z-axis scanning functionality including:
- X-Z scanning (X vs Z at fixed Y)
- Y-Z scanning (Y vs Z at fixed X) 
- 3D volumetric scanning (X-Y scans over Z steps)

The module integrates with the existing galvo scanner and piezo controller
to provide comprehensive 3D imaging capabilities.
"""

import threading
import time
import numpy as np
from typing import Tuple, List, Optional, Dict, Any
from napari.utils.notifications import show_info
from piezo_controller import PiezoController
from utils import calculate_scale, save_tiff_with_imagej_metadata


class ZScanController:
    """Controller for Z-axis scanning operations"""
    
    def __init__(self, piezo_controller: PiezoController, output_task, counter, binwidth):
        """
        Initialize Z scan controller
        
        Args:
            piezo_controller: PiezoController instance for Z-axis control
            output_task: NI DAQ output task for galvo control
            counter: TimeTagger counter for photon detection
            binwidth: TimeTagger bin width in picoseconds
        """
        self.piezo_controller = piezo_controller
        self.output_task = output_task
        self.counter = counter
        self.binwidth = binwidth
        self.scan_in_progress = False
        self.stop_scan_requested = False
        
    def scan_xz(self, x_points: np.ndarray, z_points: np.ndarray, 
                y_fixed: float, dwell_time: float = 0.002) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Perform X-Z scan at fixed Y position
        
        Args:
            x_points: Array of X positions (voltage values)
            z_points: Array of Z positions (micrometers)
            y_fixed: Fixed Y position (voltage value)
            dwell_time: Dwell time per pixel in seconds
            
        Returns:
            Tuple of (image_data, scan_metadata)
        """
        if not self.piezo_controller._is_connected:
            raise RuntimeError("Piezo controller not connected")
            
        self.scan_in_progress = True
        self.stop_scan_requested = False
        
        try:
            height, width = len(z_points), len(x_points)
            image = np.zeros((height, width), dtype=np.float32)
            
            # Calculate scales for metadata
            scale_x = calculate_scale(x_points[0], x_points[-1], width)
            scale_z = calculate_scale(z_points[0], z_points[-1], height)
            
            start_time = time.time()
            
            for z_idx, z in enumerate(z_points):
                if self.stop_scan_requested:
                    show_info("🛑 X-Z scan stopped by user")
                    break
                    
                # Move piezo to Z position
                self.piezo_controller.set_position(z)
                time.sleep(0.1)  # Settling time for piezo
                
                for x_idx, x in enumerate(x_points):
                    if self.stop_scan_requested:
                        break
                        
                    # Move galvo to X position at fixed Y
                    self.output_task.write([x, y_fixed])
                    time.sleep(dwell_time)
                    
                    # Get photon counts
                    counts = self.counter.getData()[0][0]/(self.binwidth/1e12)
                    image[z_idx, x_idx] = counts
                    
                # Update progress
                if z_idx % max(1, height // 10) == 0:  # Update every 10% of progress
                    progress = (z_idx / height) * 100
                    show_info(f"X-Z Scan Progress: {progress:.1f}%")
                    
            end_time = time.time()
            scan_time = end_time - start_time
            
            # Prepare metadata
            metadata = {
                'scan_type': 'X-Z',
                'x_points': x_points,
                'z_points': z_points,
                'y_fixed': y_fixed,
                'dwell_time': dwell_time,
                'scan_time': scan_time,
                'scale_x': scale_x,
                'scale_z': scale_z,
                'image_shape': image.shape
            }
            
            show_info(f"✅ X-Z scan completed in {scan_time:.1f} seconds")
            return image, metadata
            
        finally:
            self.scan_in_progress = False
            
    def scan_yz(self, y_points: np.ndarray, z_points: np.ndarray,
                x_fixed: float, dwell_time: float = 0.002) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Perform Y-Z scan at fixed X position
        
        Args:
            y_points: Array of Y positions (voltage values)
            z_points: Array of Z positions (micrometers)
            x_fixed: Fixed X position (voltage value)
            dwell_time: Dwell time per pixel in seconds
            
        Returns:
            Tuple of (image_data, scan_metadata)
        """
        if not self.piezo_controller._is_connected:
            raise RuntimeError("Piezo controller not connected")
            
        self.scan_in_progress = True
        self.stop_scan_requested = False
        
        try:
            height, width = len(z_points), len(y_points)
            image = np.zeros((height, width), dtype=np.float32)
            
            # Calculate scales for metadata
            scale_y = calculate_scale(y_points[0], y_points[-1], width)
            scale_z = calculate_scale(z_points[0], z_points[-1], height)
            
            start_time = time.time()
            
            for z_idx, z in enumerate(z_points):
                if self.stop_scan_requested:
                    show_info("🛑 Y-Z scan stopped by user")
                    break
                    
                # Move piezo to Z position
                self.piezo_controller.set_position(z)
                time.sleep(0.1)  # Settling time for piezo
                
                for y_idx, y in enumerate(y_points):
                    if self.stop_scan_requested:
                        break
                        
                    # Move galvo to Y position at fixed X
                    self.output_task.write([x_fixed, y])
                    time.sleep(dwell_time)
                    
                    # Get photon counts
                    counts = self.counter.getData()[0][0]/(self.binwidth/1e12)
                    image[z_idx, y_idx] = counts
                    
                # Update progress
                if z_idx % max(1, height // 10) == 0:  # Update every 10% of progress
                    progress = (z_idx / height) * 100
                    show_info(f"Y-Z Scan Progress: {progress:.1f}%")
                    
            end_time = time.time()
            scan_time = end_time - start_time
            
            # Prepare metadata
            metadata = {
                'scan_type': 'Y-Z',
                'y_points': y_points,
                'z_points': z_points,
                'x_fixed': x_fixed,
                'dwell_time': dwell_time,
                'scan_time': scan_time,
                'scale_y': scale_y,
                'scale_z': scale_z,
                'image_shape': image.shape
            }
            
            show_info(f"✅ Y-Z scan completed in {scan_time:.1f} seconds")
            return image, metadata
            
        finally:
            self.scan_in_progress = False
            
    def scan_3d(self, x_points: np.ndarray, y_points: np.ndarray, z_points: np.ndarray,
                dwell_time: float = 0.002) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Perform 3D volumetric scan (X-Y scans over Z steps)
        
        Args:
            x_points: Array of X positions (voltage values)
            y_points: Array of Y positions (voltage values)
            z_points: Array of Z positions (micrometers)
            dwell_time: Dwell time per pixel in seconds
            
        Returns:
            Tuple of (volume_data, scan_metadata)
        """
        if not self.piezo_controller._is_connected:
            raise RuntimeError("Piezo controller not connected")
            
        self.scan_in_progress = True
        self.stop_scan_requested = False
        
        try:
            depth, height, width = len(z_points), len(y_points), len(x_points)
            volume = np.zeros((depth, height, width), dtype=np.float32)
            
            # Calculate scales for metadata
            scale_x = calculate_scale(x_points[0], x_points[-1], width)
            scale_y = calculate_scale(y_points[0], y_points[-1], height)
            scale_z = calculate_scale(z_points[0], z_points[-1], depth)
            
            start_time = time.time()
            total_z_steps = len(z_points)
            
            for z_idx, z in enumerate(z_points):
                if self.stop_scan_requested:
                    show_info("🛑 3D scan stopped by user")
                    break
                    
                # Move piezo to Z position
                self.piezo_controller.set_position(z)
                time.sleep(0.1)  # Settling time for piezo
                
                # Perform X-Y scan at this Z position
                for y_idx, y in enumerate(y_points):
                    if self.stop_scan_requested:
                        break
                        
                    for x_idx, x in enumerate(x_points):
                        if self.stop_scan_requested:
                            break
                            
                        # Move galvo to position
                        self.output_task.write([x, y])
                        time.sleep(dwell_time)
                        
                        # Get photon counts
                        counts = self.counter.getData()[0][0]/(self.binwidth/1e12)
                        volume[z_idx, y_idx, x_idx] = counts
                        
                # Update progress
                progress = (z_idx / total_z_steps) * 100
                show_info(f"3D Scan Progress: {progress:.1f}% (Z step {z_idx+1}/{total_z_steps})")
                
            end_time = time.time()
            scan_time = end_time - start_time
            
            # Prepare metadata
            metadata = {
                'scan_type': '3D',
                'x_points': x_points,
                'y_points': y_points,
                'z_points': z_points,
                'dwell_time': dwell_time,
                'scan_time': scan_time,
                'scale_x': scale_x,
                'scale_y': scale_y,
                'scale_z': scale_z,
                'volume_shape': volume.shape
            }
            
            show_info(f"✅ 3D scan completed in {scan_time:.1f} seconds")
            return volume, metadata
            
        finally:
            self.scan_in_progress = False
            
    def stop_scan(self):
        """Request stop of current scan"""
        self.stop_scan_requested = True
        show_info("🛑 Stopping Z scan...")
        
    def is_scanning(self) -> bool:
        """Check if a scan is currently in progress"""
        return self.scan_in_progress
