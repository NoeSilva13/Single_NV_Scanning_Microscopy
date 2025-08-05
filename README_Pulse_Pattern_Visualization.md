# Pulse Pattern Visualization Feature

## Overview

A new pulse pattern visualization feature has been added to the ODMR Control GUI that allows users to visualize pulse sequences based on their defined parameters. This feature provides real-time visual feedback of how the laser, microwave, and detection pulses will be timed in their experiments.

## Features

### 🎯 Real-time Visualization
- **Live Updates**: The pulse pattern updates automatically when parameters are changed
- **Visual Clarity**: Clear color-coded representation of different pulse channels
- **Timeline Markers**: Precise timing indicators showing pulse durations and delays
- **Multi-Sequence Display**: When repetitions > 1, shows two complete sequences. The second sequence starts at sequence_length + sequence_interval, with total display length of sequence_length + sequence_interval + sequence_length.

### 📊 Multi-Experiment Support
- **ODMR Experiments**: Full pulse sequence visualization for ODMR measurements
- **Rabi Oscillations**: Specialized visualization for Rabi oscillation experiments
- **T1 Decay**: Specialized visualization for T1 decay experiments with init and readout laser pulses
- **Extensible Design**: Easy to add support for other experiment types

### 🎨 Professional UI Design
- **Dark Theme**: Consistent with the existing GUI design
- **Color Coding**: 
  - 🟢 Laser pulses (AOM) - Green (#4caf50)
  - 🟢 Readout Laser (T1) - Light Green (#8bc34a)
  - 🔵 Microwave pulses (MW) - Blue (#2196f3)
  - 🔴 Detection windows (SPD) - Red (#f44336)
- **Responsive Layout**: Adapts to different parameter values

## Implementation Details

### Files Added/Modified

#### New Files
- `plot_widgets/pulse_pattern_visualizer.py` - Core visualization widget
- `test_pulse_pattern.py` - Test script for verification

#### Modified Files
- `plot_widgets/__init__.py` - Added import for new widget
- `odmr_gui_qt.py` - Integrated visualization into ODMR, Rabi, and T1 tabs

### Widget Architecture

```python
class PulsePatternVisualizer(QWidget):
    """
    A widget for visualizing pulse patterns based on user-defined parameters.
    Shows the timing of laser, microwave, and detection pulses for ODMR experiments.
    """
```

### Key Methods

#### `update_pulse_pattern(parameters)`
Updates the visualization based on provided parameters:
- `laser_duration`: Duration of laser pulse (ns)
- `mw_duration`: Duration of microwave pulse (ns)
- `detection_duration`: Duration of detection window (ns)
- `laser_delay`: Delay before laser pulse (ns)
- `mw_delay`: Delay before microwave pulse (ns)
- `detection_delay`: Delay before detection window (ns)
- `sequence_interval`: Time between two complete sequences (ns)
- `repetitions`: Number of sequence repetitions (if > 1, shows two sequences)

#### `update_t1_pulse_pattern(parameters)`
Updates the T1 visualization based on provided parameters:
- `init_laser_duration`: Duration of initialization laser pulse (ns)
- `readout_laser_duration`: Duration of readout laser pulse (ns)
- `detection_duration`: Duration of detection window (ns)
- `init_laser_delay`: Delay before initialization laser pulse (ns)
- `readout_laser_delay`: Delay before readout laser pulse (ns)
- `detection_delay`: Delay before detection window (ns)
- `sequence_interval`: Time between two complete sequences (ns)
- `repetitions`: Number of sequence repetitions (if > 1, shows two sequences)

**Note**: T1 visualization shows only two channels: Laser (combining init and readout) and Detection. The laser sequence follows: init laser delay + init laser duration + readout laser delay + readout laser duration + sequence interval. The readout laser starts at init_laser_delay + init_laser_duration + readout_laser_delay. The detection window starts exactly when the readout laser starts (aligned).

#### `connect_parameter_signals()`
Automatically connects parameter input fields to trigger visualization updates when values change.

## Usage

### ODMR Control Tab
1. Navigate to the "🔬 ODMR Control" tab
2. Locate the "🎯 Pulse Pattern Visualization" section
3. Adjust timing parameters in the "Timing Parameters" and "Delay Parameters" sections
4. The pulse pattern will update automatically in real-time

### Rabi Control Tab
1. Navigate to the "📈 Rabi Control" tab
2. Locate the "🎯 Rabi Pulse Pattern" section
3. Adjust timing parameters for Rabi experiments
4. The visualization updates automatically in real-time

### T1 Decay Control Tab
1. Navigate to the "⏱️ T1 Decay" tab
2. Locate the "🎯 T1 Pulse Pattern" section
3. Adjust timing parameters for T1 decay experiments
4. The visualization shows two channels: Laser (Init + Readout) and Detection
5. Laser sequence: init laser delay + init laser duration + readout laser delay + readout laser duration + sequence interval
6. The visualization updates automatically in real-time

### Parameter Guidelines

#### Timing Parameters
- **Laser Duration**: Typically 1000-3000 ns for initialization
- **MW Duration**: Variable for different experiments (ODMR: 2000 ns, Rabi: variable)
- **Detection Duration**: Usually 500-2000 ns for photon counting

#### Delay Parameters
- **Laser Delay**: Usually 0 ns (starts immediately)
- **MW Delay**: Often set to laser duration for sequential operation
- **Detection Delay**: Positioned after MW pulse for readout

#### Sequence Parameters
- **Sequence Length**: Calculated as max(laser_delay + laser_duration, mw_delay + mw_duration, detection_delay + detection_duration)
- **Sequence Interval**: Time between two complete sequences (typically 5000-20000 ns, may be longer than sequence length)
- **Repetitions**: Number of times to repeat the sequence. When > 1, the second sequence starts at sequence_length + sequence_interval, with total display length of sequence_length + sequence_interval + sequence_length

## Technical Specifications

### Dependencies
- PyQt5 for GUI framework
- Matplotlib for plotting
- NumPy for numerical operations

### Performance
- **Real-time Updates**: Sub-second response to parameter changes
- **Memory Efficient**: Minimal memory footprint for visualization
- **Smooth Rendering**: Optimized matplotlib backend for Qt

### Compatibility
- **Python 3.7+**: Full compatibility with modern Python versions
- **Cross-platform**: Works on Windows, macOS, and Linux
- **Hardware Independent**: No specific hardware requirements

## Customization

### Adding New Experiment Types
To add pulse pattern visualization for new experiment types:

1. Create a new pulse pattern widget instance
2. Add parameter input fields
3. Implement parameter extraction method
4. Connect signals for automatic updates
5. Add visualization section to the experiment tab

### Styling Customization
The visualization uses a consistent dark theme that can be customized by modifying:
- Background colors in `bg_color` parameter
- Pulse colors in the `update_pulse_pattern` method
- Font sizes and styles in matplotlib configuration

## Testing

### Test Script
Run the test script to verify functionality:
```bash
python test_pulse_pattern.py
```

### Manual Testing
1. Launch the ODMR GUI: `python odmr_gui_qt.py`
2. Navigate to ODMR or Rabi control tabs
3. Modify timing parameters
4. Verify pulse pattern updates correctly
5. Test edge cases (very short/long durations, overlapping pulses)

## Troubleshooting

### Common Issues

#### Visualization Not Updating
- Check that parameter values are valid numbers
- Verify signal connections are properly established
- Ensure matplotlib backend is correctly configured

#### Performance Issues
- Reduce update frequency for very frequent parameter changes
- Consider debouncing parameter updates for better performance

#### Display Issues
- Verify Qt and matplotlib versions are compatible
- Check display scaling settings on high-DPI displays

### Error Handling
The visualization includes comprehensive error handling for:
- Invalid parameter values
- Missing or corrupted data
- Display rendering errors
- Memory allocation issues

## Future Enhancements

### Planned Features
- **T1 Experiment Support**: Add visualization for T1 decay experiments
- **Custom Pulse Shapes**: Support for non-rectangular pulse shapes
- **Export Functionality**: Save pulse patterns as images or data files
- **Animation Support**: Animated visualization of pulse sequences
- **Multi-channel Support**: Visualization for additional experimental channels

### Performance Improvements
- **GPU Acceleration**: Optional GPU-accelerated rendering
- **Caching**: Intelligent caching of rendered patterns
- **Optimization**: Further optimization for real-time updates

## Contributing

When contributing to the pulse pattern visualization feature:

1. Follow the existing code style and documentation standards
2. Add comprehensive tests for new functionality
3. Update this README for any new features
4. Ensure backward compatibility with existing experiments
5. Test on multiple platforms and Python versions

## Support

For issues or questions regarding the pulse pattern visualization feature:
- Check the troubleshooting section above
- Review the test script for usage examples
- Examine the source code for implementation details
- Contact the development team for technical support 