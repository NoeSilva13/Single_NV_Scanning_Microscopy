# Auto-Focus Progress Bar

## Overview

The auto-focus functionality now includes a real-time progress bar that is **integrated directly into the focus plot widget**. This provides better user feedback during the potentially lengthy auto-focus operation without cluttering the interface with additional dock widgets.

## Features

### Integrated Progress Bar
- **Embedded design**: Progress bar appears within the focus plot widget itself
- **Real-time updates**: Shows current progress percentage and status
- **Stage information**: Displays whether the system is performing coarse scan, fine scan, or completion
- **Position and counts**: Shows current Z position and photon counts during scanning
- **Automatic show/hide**: Progress bar appears when auto-focus starts and disappears when complete
- **Compact layout**: Status label and progress bar are stacked below the plot

### Progress Tracking
- **Coarse scan**: First 50% of progress bar shows coarse Z-axis scanning
- **Fine scan**: 50-95% shows fine-tuning around the optimal position
- **Completion**: Final 100% shows movement to optimal position

## Implementation Details

### Signal Bridge Extensions
The `SignalBridge` class in `widgets/auto_focus.py` has been extended with new signals that communicate with the integrated progress bar:

```python
update_progress_signal = pyqtSignal(int, str)  # (progress_percent, status_text)
show_progress_signal = pyqtSignal()            # Show progress elements
hide_progress_signal = pyqtSignal()            # Hide progress elements
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
2. The progress bar and status label will appear directly below the focus plot
3. Watch real-time updates showing:
   - Current scan stage (Coarse/Fine)
   - Z position being measured
   - Photon counts at each position
   - Overall progress percentage
4. Progress elements automatically disappear when auto-focus completes

### Widget Layout
```
┌─────────────────────┐
│   Focus Plot        │  ← Matplotlib plot (always visible)
├─────────────────────┤
│ Status: Coarse Scan │  ← Status label (hidden when idle)
│ [████████░░░░] 80%  │  ← Progress bar (hidden when idle)
└─────────────────────┘
```

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

The progress bar appearance can be customized by modifying the `_create_progress_bar()` method in the `SingleAxisPlot` class:

- **Progress bar style**: Modify the `QProgressBar` properties
- **Status label style**: Adjust the `QLabel` styling and CSS
- **Layout**: Change the `QVBoxLayout` arrangement and spacing
- **Widget height**: Adjust the overall widget height in the constructor

## Error Handling

The progress bar automatically hides if:
- Auto-focus process encounters an error
- Piezo stage connection fails
- Any exception occurs during the process

This ensures the interface remains clean even when errors occur.

## Advantages of Integrated Design

1. **Cleaner Interface**: No additional dock widgets cluttering the Napari window
2. **Better UX**: Progress information appears exactly where the user expects it
3. **Compact Layout**: All auto-focus related elements are grouped together
4. **Responsive Design**: Progress elements appear/disappear smoothly within the widget
5. **Consistent Styling**: Progress bar matches the overall plot widget design

## Migration from Previous Version

The new implementation is backward compatible with the existing API:
- The `auto_focus()` factory function still returns a widget
- The `SignalBridge` class maintains the same interface
- The `PiezoController` changes are optional (progress callback is not required)

The main difference is that the progress bar is now integrated into the `SingleAxisPlot` widget instead of being a separate dock widget. 