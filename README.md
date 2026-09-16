# Single-NV microscopy — RFSoC4x2 branch

This branch controls a single-NV confocal microscope with an
[RFSoC4x2 and QICK-DAWG](https://github.com/sandialabs/qick-dawg). It keeps the
NI USB-6453 for galvo X/Y and piezo Z analog output while replacing the
TimeTagger, Pulse Streamer 8/2, and Rigol microwave generator.

The `main` branch is the maintained implementation for the previous hardware.
The branches are separate hardware products; there is no runtime backend flag.

## Entry points

- `confocal_main_control.py`: napari confocal application.
- `run_odmr_experiments.py`: script-driven CW ODMR, pulsed ODMR, Rabi, and T1.
- `spectrometer_app.py`: spectrometer application, unchanged by this migration.

## Architecture

### Confocal

RFSoC is the timing master. For each block of raster lines the PC:

1. buffers the existing µm-derived voltage waveform in the NI DAQ;
2. arms NI AO from external sample clock `/Dev1/PFI8`;
3. runs one `ConfocalFrame.acquire()`;
4. receives one photon count per imaging pixel;
5. updates napari and repeats for the next block.

The program emits additional pixel-clock pulses during lead-in and flyback
without triggering the ADC. Each pixel integrates its whole dwell in a single
edge-count window; only a dwell beyond `RFSOC_MAX_COUNTING_WINDOW_S` is split
into windows and summed. X/Y/Z DC writes, click-to-move, sliders, park,
XY/XZ/YZ/XYZ geometry and canonical µm units remain on the NI path.

### Experiments

The RFSoC package executes sweeps and repetitions in the tProc/FPGA:

- CW ODMR: `LockinODMR`
- Pulsed ODMR: `PODMRFineRes`
- Rabi: `RabiFineRes`
- T1: `T1FineRes`

Each experiment performs one `acquire()` for its complete sweep. Results use a
native versioned NPZ/CSV format and PDF plots under
`data/mmddyy/RFSoC_<Experiment>/`.

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Install NI-DAQmx separately. Configure and run the QICK-DAWG name server and
daemon on the RFSoC4x2 using the photon-counting firmware.

```powershell
$env:NV_RFSOC_IP = "192.168.3.1"
$env:NV_RFSOC_SERVER_NAME = "myqick"
$env:NV_RFSOC_FIRMWARE = "photon_counting"
python -m rfsoc.diagnostics
```

Then run:

```powershell
python confocal_main_control.py
# or
python run_odmr_experiments.py
```

## Configuration and safety

Instrument addresses, QICK channels, PMOD pins, thresholds, NQZ, settle time,
and NI channels are in `common/utils.py`.

Do not connect an SPCM TTL output directly to an RF ADC without verifying and
conditioning its voltage. Buffer the AOM and pixel-clock PMOD outputs, connect
a common ground, and verify all waveforms on an oscilloscope. Check microwave
power and Nyquist images with a spectrum analyzer.

At 2.87 GHz, the 4.9152 GS/s `photon_counting` firmware uses NQZ2; the 9.8304
GS/s firmware uses NQZ1.

See [docs/rfsoc4x2.md](docs/rfsoc4x2.md) for wiring, bring-up, validation, and
known cancellation limitations.

## Phase-1 exclusions

Readout transient, g(2), Ramsey, Hahn echo, frame-level acquisition, removal of
the NI DAQ, and point-by-point live experiment plotting are not implemented.
