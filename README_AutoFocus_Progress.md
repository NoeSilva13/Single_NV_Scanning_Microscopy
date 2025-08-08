# Auto-Focus Progress Bar

## Overview

The auto-focus functionality now includes a real-time progress bar that shows the current status of the auto-focus process. This provides better user feedback during the potentially lengthy auto-focus operation.

## Features

### Progress Bar Widget
- **Real-time updates**: Shows current progress percentage and status
- **Stage information**: Displays whether the system is performing coarse scan, fine scan, or completion
- **Position and counts**: Shows current Z position and photon counts during scanning
- **Automatic cleanup**: Progress bar automatically disappears when auto-focus completes

### Progress Tracking
- **Coarse scan**: First 50% of progress bar shows coarse Z-axis scanning
- **Fine scan**: 50-95% shows fine-tuning around the optimal position
- **Completion**: Final 100% shows movement to optimal position

## Implementation Details

### Signal Bridge Extensions
The `SignalBridge` class in `widgets/auto_focus.py` has been extended with new signals:

```python
update_progress_signal = pyqtSignal(int, str)  # (progress_percent, status_text)
show_progress_signal = pyqtSignal()            # Show progress bar
hide_progress_signal = pyqtSignal()            # Hide progress bar
```

### Progress Callback
The `PiezoController.perform_auto_focus()` method now accepts an optional progress callback:

```python
def perform_auto_focus(self, 
                     counter_function: Callable[[], int],
                     progress_callback: Optional[Callable[[int, int, str, float, int], None]] = None,
                     ...):
```

The callback signature is:
- `current_step`: Current step number
- `total_steps`: Total number of steps
- `stage`: Current stage ("Coarse Scan", "Fine Scan", "Complete")
- `position`: Current Z position in µm
- `counts`: Current photon counts

### Thread Safety
All progress updates are thread-safe using PyQt5 signals, ensuring the GUI updates happen on the main thread.

## Usage

### For Users
1. Click the "🔍 Auto Focus" button in the Napari interface
2. A progress bar will appear at the bottom of the window
3. Watch real-time updates showing:
   - Current scan stage (Coarse/Fine)
   - Z position being measured
   - Photon counts at each position
   - Overall progress percentage
4. Progress bar automatically disappears when auto-focus completes

### For Developers
To add progress tracking to other operations:

1. **Create a progress callback function**:
```python
def progress_callback(current_step, total_steps, stage, position=None, counts=None):
    progress_percent = int((current_step / total_steps) * 100)
    status_text = f'{stage}: Step {current_step}/{total_steps}'
    signal_bridge.update_progress_signal.emit(progress_percent, status_text)
```

2. **Show/hide progress bar**:
```python
signal_bridge.show_progress_signal.emit()   # Show at start
signal_bridge.hide_progress_signal.emit()   # Hide at end
```

3. **Update progress during operation**:
```python
signal_bridge.update_progress_signal.emit(progress_percent, status_text)
```

## Configuration

The progress bar appearance can be customized by modifying the `create_progress_widget()` function in `widgets/auto_focus.py`:

- **Progress bar style**: Modify the `QProgressBar` properties
- **Status label style**: Adjust the `QLabel` styling
- **Layout**: Change the `QVBoxLayout` arrangement

## Error Handling

The progress bar automatically hides if:
- Auto-focus process encounters an error
- Piezo stage connection fails
- Any exception occurs during the process

This ensures the interface remains clean even when errors occur.

## Testing

A test script `test_auto_focus_progress.py` is provided to verify the progress bar functionality without requiring the full microscope setup.

Run the test with:
```bash
python test_auto_focus_progress.py
```

This will open a simple window with a test button that simulates the auto-focus process and shows the progress bar in action. 