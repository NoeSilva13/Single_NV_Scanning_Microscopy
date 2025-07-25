# Pulse Sequence Diagrams

This folder contains visual parameter guides for the three main quantum sensing experiments in the ODMR Control Center. Each SVG diagram illustrates the pulse timing, parameter relationships, and physical processes for optimal parameter setting.

## 📁 Files

### 🔬 **Experiment Diagrams**

| File | Experiment | Description |
|------|------------|-------------|
| `t1_decay_sequence_diagram.svg` | T1 Decay | Relaxation time measurement using laser pulses only |
| `odmr_sequence_diagram.svg` | ODMR | Frequency sweep to find NV resonance using MW driving |
| `rabi_sequence_diagram.svg` | Rabi Oscillations | MW duration sweep to measure population oscillations |

## 🎯 **How to Use These Diagrams**

### **For New Users:**
1. **Study the sequence flow** - understand the physical process
2. **Identify key parameters** - see what controls experiment sensitivity
3. **Note default values** - good starting points for first measurements
4. **Understand timing relationships** - how delays auto-calculate

### **For Parameter Optimization:**
1. **Variable parameters** are highlighted in **yellow** - these are swept during measurements
2. **Fixed parameters** in **green** control pulse durations and timing
3. **Auto-calculated delays** are shown with mathematical relationships
4. **Expected results** help interpret measurement outcomes

## 📊 **Experiment Overview**

### **T1 Decay Measurement**
- **Purpose**: Measure excited state lifetime
- **Key Variable**: Delay time between init and readout lasers (0-10000 ns)
- **Result**: Exponential decay curve → T1 relaxation time
- **No Microwave Required**: Pure optical measurement

### **ODMR (Optically Detected Magnetic Resonance)**
- **Purpose**: Find NV center resonance frequency
- **Key Variable**: Microwave frequency (2.80-2.90 GHz sweep)
- **Result**: Lorentzian dip at resonance (~2.87 GHz)
- **Applications**: Magnetometry, sensing, calibration

### **Rabi Oscillations**
- **Purpose**: Measure coherent population transfer
- **Key Variable**: Microwave pulse duration (0-200 ns)
- **Result**: Sinusoidal oscillation → π/2 and π pulse durations
- **Applications**: Gate calibration, coherence assessment

## 🎨 **Visual Guide Features**

### **Color Coding:**
- **Red**: Laser pulses (initialization/readout)
- **Purple**: Microwave pulses (population control)
- **Blue**: Detection windows (photon counting)
- **Yellow**: Variable parameters (experiment sweep range)
- **Green**: Fixed timing parameters
- **Orange**: Auto-calculated delays

### **Timeline Elements:**
- **Solid rectangles**: Active pulses (ON state)
- **Dashed rectangles**: Inactive periods (OFF state)
- **Dimensional lines**: Parameter annotations with default values
- **NV State row**: Shows physical quantum state evolution

## 🔧 **Parameter Setting Guidelines**

### **Timing Constraints:**
- All parameters aligned to **8 ns boundaries** (Pulse Streamer requirement)
- Auto-calculated delays ensure proper sequence timing
- Default values provide good signal-to-noise starting points

### **Optimization Tips:**
1. **T1**: Increase delay range if decay not complete
2. **ODMR**: Adjust frequency range if no resonance found
3. **Rabi**: Increase MW duration range to see full oscillation

### **Common Issues:**
- **Weak signal**: Increase repetitions or laser power
- **No contrast**: Check MW frequency or power
- **Timing errors**: Ensure 8ns alignment of custom parameters

## 📖 **Integration with GUI**

These diagrams complement the ODMR Control Center interface:
- Reference them when setting up new experiments
- Use parameter boxes for quick lookup of defaults
- Compare your results with expected curve shapes
- Troubleshoot timing issues using sequence visualization

## 🎓 **Educational Use**

Perfect for:
- **Training new lab members** on NV center experiments
- **Understanding parameter relationships** before running measurements
- **Troubleshooting experimental issues** with visual timing reference
- **Planning experiment sequences** and parameter ranges

---

*Generated for ODMR Control Center - NV Lab*  
*Dark theme styling matches the napari-inspired GUI interface* 