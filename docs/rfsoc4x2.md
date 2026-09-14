# RFSoC4x2 setup and bring-up

This branch targets the RFSoC4x2 with QICK-DAWG. The `main` branch remains the
implementation for TimeTagger, Pulse Streamer 8/2, and Rigol DSG836.

## Software

Use the same QICK version on the PC and board:

```powershell
python -m pip install -r requirements.txt
```

The requirements pin QICK 0.2.302 and QICK-DAWG commit `4bc384f4`. On the board,
load either `firmware/photon_counting/qick_4x2.bit` or the 9 GHz variant, then
start the Pyro name server and `qick_daemon` with server name `myqick`.

Set the board address without editing code:

```powershell
$env:NV_RFSOC_IP = "192.168.3.1"
$env:NV_RFSOC_SERVER_NAME = "myqick"
$env:NV_RFSOC_FIRMWARE = "photon_counting"
```

Run `python -m rfsoc.diagnostics` before either application.

## Required wiring

- Condition and attenuate the SPCM TTL output before the selected RF ADC.
  Never assume a 3.3/5 V TTL signal is safe for an RFSoC ADC input.
- RFSoC PMOD AOM output -> suitable logic buffer/driver -> AOM gate.
- RFSoC PMOD pixel-clock output -> logic buffer -> `DAQ_RFSOC_CLOCK_INPUT`
  (`/Dev1/PFI8` by default).
- Connect a common signal ground. Verify levels and polarity at every receiving
  connector before connecting the instruments.
- RF DAC channel 0 -> filtered/amplified microwave chain. Measure unwanted
  Nyquist images before connecting the device under test.

The pin indices in `common/utils.py` are QICK output-pin indices, not connector
labels. Confirm them against the printed `QickConfig`.

## Nyquist-zone rule

At 2.87 GHz:

- `photon_counting` (4.9152 GS/s DAC): configure NQZ 2.
- `photon_counting_9ghz` (9.8304 GS/s DAC): configure NQZ 1.

The software rejects an inconsistent firmware/frequency/NQZ combination, but
that check does not replace a spectrum-analyzer measurement.

## Confocal timing

The NI device remains responsible for `ao0`, `ao1`, and `ao2`, including all DC
writes. During a scan:

1. The host buffers one line and arms a finite AO task using PFI8 as an external
   rising-edge sample clock.
2. One `ConfocalLine.acquire()` emits a PMOD edge for each imaging sample.
3. After every edge the program waits for galvo/piezo settle, then integrates
   one or more legal edge-counting windows.
4. The program emits flyback clocks after the line without ADC triggers.
5. The host inserts the completed line in napari and arms the next line.

The 16-bit readout-length register permits at most 65535 ADC samples per
window. Longer dwell values are divided into K windows and summed. Count rates
use the effective integrated duration, excluding settle and flyback.

Stop is deterministic between lines. QICK 0.2.302 does not provide a safe
cooperative cancellation of a blocked remote `acquire()`, so an RFSoC/NI line
already in progress is allowed to finish before the next line is suppressed.

## Bench acceptance sequence

1. Run `connection_report()` and compare firmware, channel map, PMOD pins and
   client/server versions.
2. Feed conditioned calibration pulses to the ADC. Sweep high/low thresholds
   and verify linear counts, minimum pulse width and no rollover.
3. Observe AOM and pixel clock together on an oscilloscope. Confirm that clock
   transitions do not glitch the AOM mask.
4. Arm a short NI AO buffer and prove that N PMOD edges produce exactly N AO
   updates.
5. Acquire one pixel, one short line, a line with flyback, then XY, XZ/YZ and
   XYZ.
6. Measure the RF DAC spectrum at the intended gain and NQZ.
7. Run CW ODMR, pulsed ODMR, Rabi and T1 in that order.

## Experiment runner

`run_odmr_experiments.py` is intentionally script-only. Edit and uncomment one
block. Each experiment compiles one FPGA sweep and calls `acquire()` once;
there is no SCPI or host loop per sweep point. Results are written under:

```text
data/mmddyy/RFSoC_<Experiment>/
```

Each measurement contains CSV, compressed NPZ metadata, and PDF output.
Readout transient, g(2), Ramsey, Hahn echo, frame-level acquisition, removal of
the NI DAQ, and incremental experiment plotting are outside phase 1.
