"""
DAQ-based Z-axis (piezo objective) controller.
-------------------------------------------------
Controls the objective piezo Z position by writing an analog voltage on a DAQ
analog-output channel (default ``Dev1/ao2``) wired to the piezo controller's
EXT IN BNC.

The piezo controller itself is initialized and kept in closed loop by the
external Thorlabs software. In closed loop the EXT IN voltage commands the
position, with 0-10 V mapping to 0-450 um (see ``Z_UM_PER_VOLT``).

This is a thin specialization of :class:`daq_axis.DAQAxis`: it shares the
µm <-> volt calibration and the ephemeral-write control logic, and only pins the
Z-specific defaults (channel, travel 0-450 µm, closed-loop voltage range).
"""

from daq_axis import DAQAxis
from utils import Z_UM_PER_VOLT, Z_MAX_TRAVEL_UM, Z_VOLTAGE_RANGE


class DAQZController(DAQAxis):
    """Command the objective piezo Z position through a DAQ analog output."""

    def __init__(self,
                 ao_channel: str = "Dev1/ao2",
                 um_per_volt: float = Z_UM_PER_VOLT,
                 max_travel_um: float = Z_MAX_TRAVEL_UM,
                 voltage_range=Z_VOLTAGE_RANGE):
        super().__init__(
            name="z",
            ao_channel=ao_channel,
            um_per_volt=um_per_volt,
            voltage_range=voltage_range,
            travel_um=(0.0, max_travel_um),
            validate=True,
        )
        # Backwards-compatible attribute kept for existing callers.
        self.max_travel_um = max_travel_um
