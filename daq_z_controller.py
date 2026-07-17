"""
DAQ-based Z-axis (piezo objective) controller.
-------------------------------------------------
Controls the objective piezo Z position by writing an analog voltage on a DAQ
analog-output channel (default ``Dev1/ao2``) wired to the piezo controller's
EXT IN BNC.

The piezo controller itself is initialized and kept in closed loop by the
external Thorlabs software. In closed loop the EXT IN voltage commands the
position, with 0-10 V mapping to 0-450 um (see ``Z_UM_PER_VOLT``).

This class is intentionally minimal: it only maps micrometers <-> volts and
writes the voltage. There is no analog position readback, so the reported
position is simply the last commanded value.

Each move uses an ephemeral DAQ task (open, write, close), mirroring
``GalvoScannerController.set_voltages``. This avoids holding the shared AO
timing engine, which the hardware-timed raster scan reserves for ao0/ao1.
"""

import numpy as np
import nidaqmx
from nidaqmx.errors import DaqError, DaqNotFoundError

from utils import Z_UM_PER_VOLT, Z_MAX_TRAVEL_UM, Z_VOLTAGE_RANGE


class DAQZController:
    """Command the objective piezo Z position through a DAQ analog output."""

    def __init__(self,
                 ao_channel: str = "Dev1/ao2",
                 um_per_volt: float = Z_UM_PER_VOLT,
                 max_travel_um: float = Z_MAX_TRAVEL_UM,
                 voltage_range=Z_VOLTAGE_RANGE):
        self.ao_channel = ao_channel
        self.um_per_volt = um_per_volt
        self.max_travel_um = max_travel_um
        self.voltage_range = tuple(voltage_range)
        self.available = False
        self._position = 0.0

        # Validate that the analog-output channel exists on the DAQ.
        try:
            with nidaqmx.Task() as test_task:
                test_task.ao_channels.add_ao_voltage_chan(self.ao_channel)
            self.available = True
            print(f"Successfully initialized Z control on {self.ao_channel}")
        except DaqNotFoundError:
            print("NI-DAQmx not found. Z control via DAQ is unavailable.")
        except DaqError as e:
            print(f"Error initializing Z control on {self.ao_channel}: {e}")
        except Exception as e:
            print(f"Unexpected error initializing Z control: {e}")

    # --------------------------
    # Calibration helpers
    # --------------------------
    def position_to_voltage(self, position_um: float) -> float:
        """Convert a clamped position in micrometers to an EXT IN voltage."""
        position_um = float(np.clip(position_um, 0.0, self.max_travel_um))
        voltage = position_um / self.um_per_volt
        return float(np.clip(voltage, *self.voltage_range))

    def voltage_to_position(self, voltage: float) -> float:
        """Convert an EXT IN voltage to a position in micrometers."""
        voltage = float(np.clip(voltage, *self.voltage_range))
        return voltage * self.um_per_volt

    # --------------------------
    # Control
    # --------------------------
    def set_position(self, position_um: float) -> float:
        """Move the piezo to ``position_um`` (micrometers).

        Clamps to the valid travel range, converts to a voltage, and writes it
        on the analog-output channel using an ephemeral task.

        Returns:
            float: The effective position applied (after clamping).
        """
        effective_um = float(np.clip(position_um, 0.0, self.max_travel_um))
        voltage = self.position_to_voltage(effective_um)

        if not self.available:
            raise RuntimeError("Z control via DAQ is not available")

        try:
            with nidaqmx.Task() as ao_task:
                ao_task.ao_channels.add_ao_voltage_chan(self.ao_channel)
                ao_task.write(voltage, auto_start=True)
            self._position = effective_um
            return effective_um
        except DaqError as e:
            raise RuntimeError(f"Error setting Z position: {e}")

    @property
    def position(self) -> float:
        """Last commanded position in micrometers (no analog readback)."""
        return self._position

    @property
    def max_travel(self) -> float:
        """Full travel range of the piezo stage in micrometers."""
        return self.max_travel_um

    def close(self):
        """Release resources. Leaves the last commanded voltage in place."""
        # Ephemeral tasks are already closed after each write; nothing to hold.
        # The DAQ holds the last written voltage, keeping the piezo in position.
        pass
