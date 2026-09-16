# Confocal widgets on the RFSoC4x2 branch

The widgets retain the napari UI and canonical µm contracts from `main`.
Hardware-timed scans now receive an `RFSoCSession` and an
`AcquisitionHandle`:

- `AutoFocusWidget(session, ..., scan_task_ref, acquisition_ref)`
- `SingleAxisScanWidget(..., session, ..., scan_task_ref, acquisition_ref)`
- `stop_scan(..., scan_task_ref, acquisition_ref, scan_lock)`

Manual X/Y/Z controls remain NI on-demand AO writes. Raster, single-axis, and
Z sweeps arm one finite NI AO task with an external RFSoC PMOD clock, and the
counts stream back while it runs. Stop marks the acquisition and takes effect
between two readout strides: within a line at ordinary dwells, within a pixel at
long ones.
