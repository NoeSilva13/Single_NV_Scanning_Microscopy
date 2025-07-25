#!/usr/bin/env python3
"""
Test Script for PyQtGraph Version of Confocal Control
====================================================
This script allows testing the PyQtGraph interface without requiring
full hardware setup (DAQ, TimeTagger, etc.)
"""

import sys
import numpy as np
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QLabel
from PyQt5.QtCore import QTimer
import pyqtgraph as pg

# Configure PyQtGraph
pg.setConfigOptions(antialias=True, useOpenGL=False)  # Disable OpenGL for compatibility
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')

class TestConfocalWindow(QMainWindow):
    """Simplified test window to demonstrate PyQtGraph capabilities"""
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.setup_test_data()
        
    def setup_ui(self):
        """Setup basic UI for testing"""
        self.setWindowTitle("PyQtGraph Confocal Test")
        self.setGeometry(100, 100, 1200, 800)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        layout = QHBoxLayout()
        central_widget.setLayout(layout)
        
        # Left panel for controls
        left_panel = self.create_control_panel()
        layout.addWidget(left_panel)
        
        # Right panel for image display
        self.image_widget = self.create_image_widget()
        layout.addWidget(self.image_widget)
        
        # Status bar
        self.statusBar().showMessage("PyQtGraph test ready")
        
    def create_control_panel(self):
        """Create control panel with test buttons"""
        widget = QWidget()
        widget.setFixedWidth(300)
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Test Controls")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        
        # Test buttons
        self.simulate_scan_btn = QPushButton("Simulate Scan")
        self.simulate_scan_btn.clicked.connect(self.simulate_scan)
        layout.addWidget(self.simulate_scan_btn)
        
        self.add_noise_btn = QPushButton("Add Noise")
        self.add_noise_btn.clicked.connect(self.add_noise)
        layout.addWidget(self.add_noise_btn)
        
        self.clear_image_btn = QPushButton("Clear Image")
        self.clear_image_btn.clicked.connect(self.clear_image)
        layout.addWidget(self.clear_image_btn)
        
        self.test_roi_btn = QPushButton("Add Test ROI")
        self.test_roi_btn.clicked.connect(self.add_test_roi)
        layout.addWidget(self.test_roi_btn)
        
        # Performance info
        self.perf_label = QLabel("Performance: Ready")
        layout.addWidget(self.perf_label)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
        
    def create_image_widget(self):
        """Create image display widget"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create graphics layout widget
        self.graphics_widget = pg.GraphicsLayoutWidget()
        
        # Create plot item for image display
        self.plot_item = self.graphics_widget.addPlot(title="Simulated Confocal Scan")
        self.plot_item.setAspectLocked(True)
        self.plot_item.setLabel('left', 'Y Position (µm)')
        self.plot_item.setLabel('bottom', 'X Position (µm)')
        
        # Create image item
        self.image_item = pg.ImageItem()
        self.plot_item.addItem(self.image_item)
        
        # Create colorbar
        self.colorbar = pg.ColorBarItem(
            values=(0, 1000),
            colorMap=pg.colormap.get('viridis'),
            width=20,
            interactive=True
        )
        self.colorbar.setImageItem(self.image_item, insert_in=self.plot_item)
        
        # Add mouse click handling
        self.image_item.mousePressEvent = self.on_image_click
        
        layout.addWidget(self.graphics_widget)
        widget.setLayout(layout)
        return widget
        
    def setup_test_data(self):
        """Setup test data and timers"""
        self.image_size = (100, 100)
        self.current_image = np.zeros(self.image_size, dtype=np.float32)
        self.roi = None
        
        # Timer for performance testing
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_performance_test)
        
        # Performance counter
        self.frame_count = 0
        self.last_fps_time = 0
        
    def simulate_scan(self):
        """Simulate a confocal scan with realistic data"""
        self.statusBar().showMessage("Simulating scan...")
        
        # Create realistic microscopy data
        x = np.linspace(-5, 5, self.image_size[1])
        y = np.linspace(-5, 5, self.image_size[0])
        X, Y = np.meshgrid(x, y)
        
        # Simulate multiple fluorescent spots
        image = np.zeros_like(X)
        
        # Add several Gaussian spots with different intensities
        spots = [
            (-2, -1, 800, 0.5),   # (x, y, intensity, width)
            (1, 2, 1200, 0.3),
            (-1, 1, 600, 0.7),
            (3, -2, 900, 0.4),
        ]
        
        for spot_x, spot_y, intensity, width in spots:
            spot = intensity * np.exp(-((X - spot_x)**2 + (Y - spot_y)**2) / (2 * width**2))
            image += spot
        
        # Add background and noise
        image += 50 + 20 * np.random.randn(*image.shape)
        
        # Ensure positive values
        image = np.maximum(image, 0)
        
        self.current_image = image.astype(np.float32)
        self.update_image_display()
        
        self.statusBar().showMessage("Scan simulation complete")
        
    def add_noise(self):
        """Add noise to current image"""
        if self.current_image is not None:
            noise = 50 * np.random.randn(*self.current_image.shape)
            self.current_image += noise
            self.current_image = np.maximum(self.current_image, 0)  # Keep positive
            self.update_image_display()
            self.statusBar().showMessage("Noise added")
            
    def clear_image(self):
        """Clear the current image"""
        self.current_image = np.zeros(self.image_size, dtype=np.float32)
        self.update_image_display()
        self.statusBar().showMessage("Image cleared")
        
    def add_test_roi(self):
        """Add a test ROI"""
        if self.roi is not None:
            self.plot_item.removeItem(self.roi)
        
        # Create rectangular ROI
        self.roi = pg.RectROI([1, 1], [2, 2], pen='r')
        self.plot_item.addItem(self.roi)
        
        # Connect ROI change signal
        self.roi.sigRegionChanged.connect(self.on_roi_changed)
        
        self.statusBar().showMessage("Test ROI added - drag to resize")
        
    def update_image_display(self):
        """Update the image display"""
        if self.current_image is not None:
            # Set image data
            self.image_item.setImage(self.current_image, autoLevels=True)
            
            # Update colorbar levels
            min_val = np.min(self.current_image)
            max_val = np.max(self.current_image)
            self.colorbar.setLevels((min_val, max_val))
            
    def on_image_click(self, event):
        """Handle image click events"""
        if event.button() == 1:  # Left click
            pos = event.pos()
            self.statusBar().showMessage(f"Clicked at: ({pos.x():.1f}, {pos.y():.1f})")
            
    def on_roi_changed(self):
        """Handle ROI changes"""
        if self.roi is not None:
            pos = self.roi.pos()
            size = self.roi.size()
            self.statusBar().showMessage(
                f"ROI: pos=({pos[0]:.1f}, {pos[1]:.1f}), size=({size[0]:.1f}, {size[1]:.1f})"
            )
            
    def start_performance_test(self):
        """Start performance testing"""
        self.frame_count = 0
        self.last_fps_time = 0
        self.update_timer.start(16)  # ~60 FPS
        self.statusBar().showMessage("Performance test started")
        
    def stop_performance_test(self):
        """Stop performance testing"""
        self.update_timer.stop()
        self.statusBar().showMessage("Performance test stopped")
        
    def update_performance_test(self):
        """Update for performance testing"""
        # Add some dynamic noise to test update performance
        if self.current_image is not None:
            noise = 10 * np.random.randn(*self.current_image.shape)
            test_image = self.current_image + noise
            test_image = np.maximum(test_image, 0)
            
            self.image_item.setImage(test_image, autoLevels=False)
            
            self.frame_count += 1
            
            # Update FPS counter every second
            import time
            current_time = time.time()
            if current_time - self.last_fps_time >= 1.0:
                fps = self.frame_count / (current_time - self.last_fps_time) if self.last_fps_time > 0 else 0
                self.perf_label.setText(f"Performance: {fps:.1f} FPS")
                self.frame_count = 0
                self.last_fps_time = current_time

def run_test():
    """Run the test application"""
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("PyQtGraph Confocal Test")
    
    # Create main window
    window = TestConfocalWindow()
    window.show()
    
    print("PyQtGraph Confocal Test Started")
    print("=" * 50)
    print("Test Features:")
    print("• Simulate Scan - Generate realistic confocal data")
    print("• Add Noise - Test dynamic updates")
    print("• Clear Image - Reset display")
    print("• Add Test ROI - Test region selection")
    print("• Click on image to test coordinate mapping")
    print("=" * 50)
    
    # Auto-run simulation for demonstration
    window.simulate_scan()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    run_test() 