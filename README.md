# Single NV Scanning Microscopy

This Python project provides software control for a Single Nitrogen-Vacancy (NV) Scanning Microscopy system. The setup is based on the **Thorlabs LSKGG4 Galvo-Galvo Scanner** and the **NI USB-6453 Data Acquisition (DAQ) device**.

## Overview

The system enables two-dimensional imaging of samples by scanning with high precision and detecting single photons emitted by NV centers in diamond. Two types of detectors are supported:

- **Avalanche Photodiode (APD)**
- **Excelitas SPCM-AQRH-10-FC Single Photon Counting Module**

These detectors are used to collect fluorescence data from the sample as it is scanned, enabling high-resolution image reconstruction.

## Features

- Real-time control of galvo scanners
- Synchronization with single-photon detectors
- Image acquisition and reconstruction
- Support for multiple detector types

## Requirements

- **Hardware**:
  - Thorlabs LSKGG4 Galvo-Galvo Scanner
  - NI USB-6453 DAQ
  - APD or Excelitas SPCM-AQRH-10-FC detector

- **Software**:
  - Python (version X.X or higher)
  - Required Python packages (see `requirements.txt`)

## Getting Started

##License

