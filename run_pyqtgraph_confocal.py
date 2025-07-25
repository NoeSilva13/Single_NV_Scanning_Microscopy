#!/usr/bin/env python3
"""
Startup Script for PyQtGraph Confocal Control
============================================
This script handles dependencies and provides a safe way to start the application
"""

import sys
import os

def check_dependencies():
    """Check if all required dependencies are available"""
    missing_deps = []
    
    try:
        import pyqtgraph
        print(f"✅ PyQtGraph {pyqtgraph.__version__} found")
    except ImportError:
        missing_deps.append("pyqtgraph")
    
    try:
        import PyQt5
        print(f"✅ PyQt5 found")
    except ImportError:
        missing_deps.append("PyQt5")
    
    try:
        import numpy
        print(f"✅ NumPy {numpy.__version__} found")
    except ImportError:
        missing_deps.append("numpy")
    
    try:
        import nidaqmx
        print(f"✅ NI-DAQmx found")
    except ImportError:
        print("⚠️ NI-DAQmx not found - DAQ functionality will be disabled")
    
    try:
        from TimeTagger import createTimeTagger
        print(f"✅ TimeTagger found")
    except ImportError:
        print("⚠️ TimeTagger not found - will use virtual device if available")
    
    try:
        import qickdawg
        print(f"✅ qickdawg found")
    except ImportError:
        print("⚠️ qickdawg not found - some functionality may be limited")
    
    if missing_deps:
        print("\n❌ Missing required dependencies:")
        for dep in missing_deps:
            print(f"   - {dep}")
        print("\nInstall missing dependencies with:")
        print(f"   pip install {' '.join(missing_deps)}")
        return False
    
    return True

def main():
    """Main startup function"""
    print("PyQtGraph Confocal Control Startup")
    print("=" * 50)
    
    # Check dependencies
    if not check_dependencies():
        print("\n❌ Cannot start application - missing dependencies")
        sys.exit(1)
    
    print("\n🚀 Starting PyQtGraph Confocal Control...")
    
    try:
        # Import and run the main application
        from confocal_main_control_pyqtgraph import main as run_confocal
        run_confocal()
        
    except ImportError as e:
        print(f"\n❌ Import error: {e}")
        print("Make sure all widget modules are available")
        sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Startup error: {e}")
        print("Try running the test version first:")
        print("   python test_pyqtgraph_version.py")
        sys.exit(1)

if __name__ == "__main__":
    main() 