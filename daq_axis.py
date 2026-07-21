"""
DAQ analog-output axis abstraction.
-------------------------------------------------
A ``DAQAxis`` encapsulates the calibration (micrometers <-> volts), the analog
output channel, and the travel/voltage limits of a single scan axis driven by a
NI-DAQ analog output.

This is the single place where the µm <-> volt conversion lives, so the rest of
the application can work in micrometers (the canonical unit) and only convert to
volts at the DAQ boundary (waveform generation / analog writes).

Galvo X/Y and the piezo Z all share this interface, so combined scans (XY, XZ,
YZ, XYZ) can treat every axis uniformly.
"""

import numpy as np
import nidaqmx
from nidaqmx.errors import DaqError, DaqNotFoundError


class DAQAxis:
    """Calibration + metadata for one DAQ-driven analog-output scan axis."""

    def __init__(self, name, ao_channel, um_per_volt, voltage_range,
                 travel_um, validate=True):
        """
        Args:
            name: Short axis label, e.g. ``"x"``.
            ao_channel: Analog-output channel, e.g. ``"Dev1/ao0"``.
            um_per_volt: Calibration factor (micrometers per volt).
            voltage_range: (min_v, max_v) allowed output voltage.
            travel_um: (min_um, max_um) physical travel in micrometers.
            validate: If True, verify the AO channel exists on the DAQ.
        """
        self.name = name
        self.ao_channel = ao_channel
        self.um_per_volt = float(um_per_volt)
        self.voltage_range = (float(voltage_range[0]), float(voltage_range[1]))
        self.travel_um = (float(travel_um[0]), float(travel_um[1]))
        self.available = False
        self._position = 0.0

        if validate:
            self._validate_channel()
        else:
            self.available = True

    def _validate_channel(self):
        try:
            with nidaqmx.Task() as test_task:
                test_task.ao_channels.add_ao_voltage_chan(self.ao_channel)
            self.available = True
            print(f"Successfully initialized axis '{self.name}' on {self.ao_channel}")
        except DaqNotFoundError:
            print(f"NI-DAQmx not found. Axis '{self.name}' is unavailable.")
        except DaqError as e:
            print(f"Error initializing axis '{self.name}' on {self.ao_channel}: {e}")
        except Exception as e:
            print(f"Unexpected error initializing axis '{self.name}': {e}")

    # ------------------------------------------------------------------
    # Calibration
    # ------------------------------------------------------------------
    def clamp_um(self, position_um):
        """Clamp a position (µm) to the axis travel range."""
        return float(np.clip(position_um, self.travel_um[0], self.travel_um[1]))

    def position_to_voltage(self, position_um):
        """Convert a single position (µm) to a clamped output voltage."""
        position_um = self.clamp_um(position_um)
        voltage = position_um / self.um_per_volt
        return float(np.clip(voltage, *self.voltage_range))

    def voltage_to_position(self, voltage):
        """Convert a single voltage to a position in micrometers."""
        voltage = float(np.clip(voltage, *self.voltage_range))
        return voltage * self.um_per_volt

    def to_voltage(self, positions_um):
        """Vectorized µm -> volt conversion for a waveform array."""
        um = np.clip(np.asarray(positions_um, dtype=float),
                     self.travel_um[0], self.travel_um[1])
        volts = um / self.um_per_volt
        return np.clip(volts, self.voltage_range[0], self.voltage_range[1])

    # ------------------------------------------------------------------
    # Control (ephemeral single write; used by axes without a persistent task)
    # ------------------------------------------------------------------
    def set_position(self, position_um):
        """Move the axis to ``position_um`` (µm) via an ephemeral DAQ task.

        Returns the effective (clamped) position applied.
        """
        effective_um = self.clamp_um(position_um)
        voltage = self.position_to_voltage(effective_um)

        if not self.available:
            raise RuntimeError(f"Axis '{self.name}' via DAQ is not available")

        try:
            with nidaqmx.Task() as ao_task:
                ao_task.ao_channels.add_ao_voltage_chan(self.ao_channel)
                ao_task.write(voltage, auto_start=True)
            self._position = effective_um
            return effective_um
        except DaqError as e:
            raise RuntimeError(f"Error setting axis '{self.name}' position: {e}")

    @property
    def position(self):
        """Last commanded position in micrometers (no analog readback)."""
        return self._position

    @property
    def travel_min(self):
        return self.travel_um[0]

    @property
    def travel_max(self):
        return self.travel_um[1]

    @property
    def max_travel(self):
        """Backwards-compatible alias for the upper travel bound (µm)."""
        return self.travel_um[1]

    def close(self):
        """Release resources. Ephemeral tasks are already closed after writes."""
        pass
