"""
Z Scan Data Manager Module
--------------------------
This module handles data management for Z-axis scanning including:
- Saving 3D volumetric data
- Managing Z scan metadata
- Exporting data in various formats
- Loading and visualizing Z scan data
"""

import os
import time
import numpy as np
from typing import Dict, Any, Optional, Tuple
from napari.utils.notifications import show_info
from utils import save_tiff_with_imagej_metadata


class ZScanDataManager:
    """Data manager for Z-axis scanning operations"""
    
    def __init__(self, base_directory: str = "z_scan_data"):
        """
        Initialize Z scan data manager
        
        Args:
            base_directory: Base directory for storing Z scan data
        """
        self.base_directory = base_directory
        self._ensure_directory_exists()
        
    def _ensure_directory_exists(self):
        """Ensure the base directory exists"""
        if not os.path.exists(self.base_directory):
            os.makedirs(self.base_directory)
            show_info(f"📁 Created Z scan data directory: {self.base_directory}")
            
    def save_xz_scan(self, image_data: np.ndarray, metadata: Dict[str, Any]) -> str:
        """
        Save X-Z scan data
        
        Args:
            image_data: 2D image array (Z vs X)
            metadata: Scan metadata dictionary
            
        Returns:
            Path to saved data file
        """
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = f"xz_scan_{timestamp}"
        filepath = os.path.join(self.base_directory, filename)
        
        # Save as NPZ with all metadata
        np.savez(f"{filepath}.npz",
                 image=image_data,
                 x_points=metadata['x_points'],
                 z_points=metadata['z_points'],
                 y_fixed=metadata['y_fixed'],
                 dwell_time=metadata['dwell_time'],
                 scan_time=metadata['scan_time'],
                 scale_x=metadata['scale_x'],
                 scale_z=metadata['scale_z'],
                 scan_type=metadata['scan_type'],
                 timestamp=timestamp)
        
        # Save as TIFF with ImageJ metadata
        save_tiff_with_imagej_metadata(
            image_data=image_data,
            filepath=f"{filepath}.tiff",
            x_points=metadata['x_points'],
            y_points=metadata['z_points'],  # Z points as Y for 2D image
            scan_config={
                'scan_type': 'X-Z',
                'y_fixed': metadata['y_fixed'],
                'dwell_time': metadata['dwell_time']
            },
            timestamp=timestamp
        )
        
        show_info(f"💾 X-Z scan data saved: {filepath}")
        return filepath
        
    def save_yz_scan(self, image_data: np.ndarray, metadata: Dict[str, Any]) -> str:
        """
        Save Y-Z scan data
        
        Args:
            image_data: 2D image array (Z vs Y)
            metadata: Scan metadata dictionary
            
        Returns:
            Path to saved data file
        """
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = f"yz_scan_{timestamp}"
        filepath = os.path.join(self.base_directory, filename)
        
        # Save as NPZ with all metadata
        np.savez(f"{filepath}.npz",
                 image=image_data,
                 y_points=metadata['y_points'],
                 z_points=metadata['z_points'],
                 x_fixed=metadata['x_fixed'],
                 dwell_time=metadata['dwell_time'],
                 scan_time=metadata['scan_time'],
                 scale_y=metadata['scale_y'],
                 scale_z=metadata['scale_z'],
                 scan_type=metadata['scan_type'],
                 timestamp=timestamp)
        
        # Save as TIFF with ImageJ metadata
        save_tiff_with_imagej_metadata(
            image_data=image_data,
            filepath=f"{filepath}.tiff",
            x_points=metadata['y_points'],  # Y points as X for 2D image
            y_points=metadata['z_points'],  # Z points as Y for 2D image
            scan_config={
                'scan_type': 'Y-Z',
                'x_fixed': metadata['x_fixed'],
                'dwell_time': metadata['dwell_time']
            },
            timestamp=timestamp
        )
        
        show_info(f"💾 Y-Z scan data saved: {filepath}")
        return filepath
        
    def save_3d_scan(self, volume_data: np.ndarray, metadata: Dict[str, Any]) -> str:
        """
        Save 3D volumetric scan data
        
        Args:
            volume_data: 3D volume array (Z, Y, X)
            metadata: Scan metadata dictionary
            
        Returns:
            Path to saved data file
        """
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = f"3d_scan_{timestamp}"
        filepath = os.path.join(self.base_directory, filename)
        
        # Save as NPZ with all metadata
        np.savez(f"{filepath}.npz",
                 volume=volume_data,
                 x_points=metadata['x_points'],
                 y_points=metadata['y_points'],
                 z_points=metadata['z_points'],
                 dwell_time=metadata['dwell_time'],
                 scan_time=metadata['scan_time'],
                 scale_x=metadata['scale_x'],
                 scale_y=metadata['scale_y'],
                 scale_z=metadata['scale_z'],
                 scan_type=metadata['scan_type'],
                 timestamp=timestamp)
        
        # Save each Z-slice as a separate TIFF
        for z_idx, z_pos in enumerate(metadata['z_points']):
            slice_filename = f"{filepath}_z{z_pos:.2f}.tiff"
            save_tiff_with_imagej_metadata(
                image_data=volume_data[z_idx],
                filepath=slice_filename,
                x_points=metadata['x_points'],
                y_points=metadata['y_points'],
                scan_config={
                    'scan_type': '3D',
                    'z_position': z_pos,
                    'z_index': z_idx,
                    'dwell_time': metadata['dwell_time']
                },
                timestamp=timestamp
            )
        
        # Save maximum intensity projection
        mip = np.max(volume_data, axis=0)
        mip_filename = f"{filepath}_mip.tiff"
        save_tiff_with_imagej_metadata(
            image_data=mip,
            filepath=mip_filename,
            x_points=metadata['x_points'],
            y_points=metadata['y_points'],
            scan_config={
                'scan_type': '3D_MIP',
                'dwell_time': metadata['dwell_time']
            },
            timestamp=timestamp
        )
        
        show_info(f"💾 3D scan data saved: {filepath}")
        return filepath
        
    def load_scan_data(self, filepath: str) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Load scan data from file
        
        Args:
            filepath: Path to the .npz file
            
        Returns:
            Tuple of (data_array, metadata)
        """
        if not filepath.endswith('.npz'):
            filepath += '.npz'
            
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Scan data file not found: {filepath}")
            
        data = np.load(filepath, allow_pickle=True)
        
        # Determine data type and extract accordingly
        if 'volume' in data.files:
            # 3D scan
            scan_data = data['volume']
            metadata = {
                'scan_type': str(data['scan_type']),
                'x_points': data['x_points'],
                'y_points': data['y_points'],
                'z_points': data['z_points'],
                'dwell_time': float(data['dwell_time']),
                'scan_time': float(data['scan_time']),
                'scale_x': float(data['scale_x']),
                'scale_y': float(data['scale_y']),
                'scale_z': float(data['scale_z']),
                'timestamp': str(data['timestamp'])
            }
        else:
            # 2D scan (X-Z or Y-Z)
            scan_data = data['image']
            metadata = {
                'scan_type': str(data['scan_type']),
                'dwell_time': float(data['dwell_time']),
                'scan_time': float(data['scan_time']),
                'timestamp': str(data['timestamp'])
            }
            
            # Add appropriate points based on scan type
            if data['scan_type'] == 'X-Z':
                metadata.update({
                    'x_points': data['x_points'],
                    'z_points': data['z_points'],
                    'y_fixed': float(data['y_fixed']),
                    'scale_x': float(data['scale_x']),
                    'scale_z': float(data['scale_z'])
                })
            elif data['scan_type'] == 'Y-Z':
                metadata.update({
                    'y_points': data['y_points'],
                    'z_points': data['z_points'],
                    'x_fixed': float(data['x_fixed']),
                    'scale_y': float(data['scale_y']),
                    'scale_z': float(data['scale_z'])
                })
                
        show_info(f"📂 Loaded scan data: {filepath}")
        return scan_data, metadata
        
    def get_scan_summary(self, filepath: str) -> Dict[str, Any]:
        """
        Get summary information about a scan file
        
        Args:
            filepath: Path to the scan file
            
        Returns:
            Dictionary with scan summary information
        """
        try:
            data, metadata = self.load_scan_data(filepath)
            
            summary = {
                'filepath': filepath,
                'scan_type': metadata['scan_type'],
                'timestamp': metadata['timestamp'],
                'scan_time': metadata['scan_time'],
                'dwell_time': metadata['dwell_time']
            }
            
            if metadata['scan_type'] == '3D':
                summary.update({
                    'data_shape': data.shape,
                    'total_voxels': data.size,
                    'data_size_mb': data.nbytes / (1024 * 1024),
                    'z_range': [metadata['z_points'][0], metadata['z_points'][-1]],
                    'x_range': [metadata['x_points'][0], metadata['x_points'][-1]],
                    'y_range': [metadata['y_points'][0], metadata['y_points'][-1]]
                })
            else:
                summary.update({
                    'data_shape': data.shape,
                    'total_pixels': data.size,
                    'data_size_mb': data.nbytes / (1024 * 1024)
                })
                
            return summary
            
        except Exception as e:
            return {
                'filepath': filepath,
                'error': str(e)
            }
            
    def list_scan_files(self) -> list:
        """
        List all scan files in the data directory
        
        Returns:
            List of scan file paths
        """
        scan_files = []
        for filename in os.listdir(self.base_directory):
            if filename.endswith('.npz'):
                filepath = os.path.join(self.base_directory, filename)
                scan_files.append(filepath)
        return sorted(scan_files, reverse=True)  # Most recent first
