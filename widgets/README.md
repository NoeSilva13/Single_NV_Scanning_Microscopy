# Confocal widgets on the RFSoC4x2 branch

The widgets retain the napari UI and canonical µm contracts from `main`.
Hardware-timed scans now receive an `RFSoCSession` and an
`AcquisitionHandle`:

- `AutoFocusWidget(session, ..., scan_task_ref, acquisition_ref)`
- `SingleAxisScanWidget(..., session, ..., scan_task_ref, acquisition_ref)`
- `stop_scan(..., scan_task_ref, acquisition_ref, scan_lock)`

Manual X/Y/Z controls remain NI on-demand AO writes. Raster, single-axis, and
Z sweeps arm finite NI AO tasks with an external RFSoC PMOD clock. Stop marks
the acquisition and prevents the next line; the current RFSoC/NI line is
allowed to finish.
