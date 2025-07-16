# CCD Camera Spectrometer Application

A Qt-based spectrometer application that uses a POA (Player One Astronomy) camera to capture and analyze spectral data from horizontal line images.

## Features

- **Real-time spectral analysis** - Processes horizontal line spectra from camera images
- **1920x1080 resolution** - Uses full HD resolution for maximum spectral detail
- **Wavelength calibration** - Linear calibration from pixel to wavelength mapping
- **Dark frame correction** - Subtracts dark current noise
- **Reference normalization** - Normalizes spectra against reference measurements
- **Real-time plotting** - Live spectrum display with adjustable parameters
- **Data recording** - Record time series of spectra
- **Export functionality** - Save spectra to CSV files
- **ROI selection** - Adjustable region of interest for spectrum extraction

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure POA camera drivers are installed and the camera is connected

3. Run the application:
```bash
python spectrometer_app.py
```

## Hardware Requirements

- POA camera (Player One Astronomy) with USB3 connection
- Computer with sufficient processing power for real-time image processing
- Spectrometer setup with horizontal line output (e.g., transmission grating)

## Usage

### Basic Operation

1. **Camera Connection**
   - The application will automatically try to connect to the first available POA camera
   - Status messages will appear in the status bar

2. **Start Imaging**
   - Click "Start Camera" to begin live image acquisition
   - The camera view will show the live image from the spectrometer

3. **ROI Setup**
   - Adjust "Start Y" to set the vertical position of the spectral line
   - Adjust "Height" to set the number of pixels to average for the spectrum
   - The ROI should encompass the horizontal spectral line

4. **Camera Settings**
   - **Exposure**: Adjust exposure time (0.1-10000 ms)
   - **Gain**: Adjust camera gain (0-1000)
   - Optimize settings for your light source and spectrometer

### Wavelength Calibration

1. **Default Calibration**
   - Set "Start λ" and "End λ" to define the wavelength range
   - Click "Apply Calibration" to create linear mapping
   - Default range: 400-800 nm

2. **Custom Calibration**
   - Use known spectral lines (e.g., mercury lamp) for precise calibration
   - Modify the calibration in the code for non-linear mappings

### Reference and Dark Corrections

1. **Dark Frame**
   - Block all light from entering the spectrometer
   - Click "Capture Dark" to record dark frame
   - This removes electronic noise and dark current

2. **Reference Frame**
   - Use a known white light source (e.g., tungsten lamp)
   - Click "Capture Reference" to record reference spectrum
   - This normalizes for lamp spectral response and optical throughput

3. **Clear Corrections**
   - Click "Clear Corrections" to remove dark/reference corrections

### Recording and Saving

1. **Live Recording**
   - Click "Start Recording" to begin time-series recording
   - Each spectrum is saved with timestamp
   - Click "Stop Recording" to end recording

2. **Save Data**
   - Click "Save Spectrum" to save current or recorded spectra
   - Data is saved in CSV format with wavelength and intensity columns
   - Multiple spectra are saved with separate intensity columns

## Technical Details

### Spectrum Processing

The application processes camera frames as follows:

1. **Frame Acquisition**: Captures frames at ~30 FPS from POA camera
2. **ROI Extraction**: Selects horizontal region containing spectral line
3. **Vertical Averaging**: Averages pixels vertically to create 1D spectrum
4. **Dark Subtraction**: Removes dark frame if available
5. **Reference Normalization**: Normalizes against reference if available
6. **Wavelength Mapping**: Converts pixel positions to wavelengths

### Camera Interface

- Uses POA camera API through `pyPOACamera` wrapper
- Supports RAW8 and RAW16 formats for maximum dynamic range
- Thread-safe camera operations for real-time performance
- Automatic exposure and gain control

### Data Format

CSV files contain:
- **Single spectrum**: Wavelength, Intensity
- **Multiple spectra**: Wavelength, Spectrum_1, Spectrum_2, ...

## Troubleshooting

### Camera Connection Issues
- Ensure camera is connected and powered
- Check USB3 connection for full bandwidth
- Verify camera drivers are installed

### Poor Signal Quality
- Adjust exposure time for proper signal level
- Optimize gain to avoid saturation
- Check spectrometer alignment and focus
- Ensure adequate light source intensity

### Calibration Problems
- Use known spectral lines for calibration verification
- Check that ROI encompasses the entire spectral line
- Verify spectrometer wavelength range matches settings

## Application Structure

```
spectrometer_app.py
├── CameraWorker (QThread)          # Camera acquisition thread
├── SpectrumProcessor              # Spectrum processing class
└── SpectrometerMainWindow        # Main GUI window
```

## Future Enhancements

- Non-linear wavelength calibration
- Advanced spectral analysis (peak finding, fitting)
- Real-time spectral math operations
- Multiple camera support
- Automated calibration routines
- Integration with external equipment

## License

This application is designed for research and educational use with POA cameras and spectrometer systems. 