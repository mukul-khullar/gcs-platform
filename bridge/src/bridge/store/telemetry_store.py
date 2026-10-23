"""Latest contract frames and MAVLink numeric telemetry histories."""

from __future__ import annotations

import time
from typing import Any

import numpy as np
from numpy.typing import NDArray

from bridge.models import FrameModel

from .ring_buffer import TimeRingBuffer

_BUFFER_RATE_HZ = {
    "attitude": 20.0,
    "vibration": 2.0,
    "ekf_variances": 2.0,
}


class TelemetryStore:
    """Store latest frames and bounded numeric histories per vehicle."""

    def __init__(self, *, duration_s: float = 60.0) -> None:
        self.duration_s = duration_s
        self._latest: dict[tuple[int, str], FrameModel] = {}
        self._buffers: dict[tuple[int, str], TimeRingBuffer] = {}

    @property
    def latest_values(self) -> dict[tuple[int, str], FrameModel]:
        """Return a shallow snapshot of the latest frame by system and topic."""
        return dict(self._latest)

    def latest(self, sysid: int, topic: str) -> FrameModel | None:
        """Get the latest frame for a system and contract topic."""
        return self._latest.get((sysid, topic))

    def ingest_frame(self, frame: FrameModel) -> None:
        """Update latest values and ATTITUDE samples.

        ATTITUDE columns are roll, pitch, yaw (rad), then roll, pitch, yaw
        rates (rad/s).
        """
        topic = frame.type.value
        self._latest[(frame.sysid, topic)] = frame
        now_s = frame.t_wall_ms / 1000.0
        if topic == "telemetry.attitude":
            data = frame.data
            self._append(
                frame.sysid,
                "attitude",
                now_s,
                [
                    _as_float(data.get("roll_rad")),
                    _as_float(data.get("pitch_rad")),
                    _as_float(data.get("yaw_rad")),
                    *[_as_float(value) for value in data.get("rates_rps", [])],
                ],
            )

    def ingest_mavlink(
        self,
        msg: Any,
        *,
        sysid: int | None = None,
        t_wall_ms: int | None = None,
    ) -> None:
        """Store numeric telemetry histories using MAVLink SI values.

        VIBRATION columns are x/y/z acceleration (m/s^2), then clipping counts.
        EKF columns are velocity, horizontal/vertical position, compass, terrain
        altitude, and airspeed variances (unitless).
        """
        message_type = str(msg.get_type())
        vehicle_sysid = int(msg.get_srcSystem()) if sysid is None else sysid
        timestamp_s = time.monotonic() if t_wall_ms is None else t_wall_ms / 1000.0
        if message_type == "VIBRATION":
            values = [
                float(msg.vibration_x),
                float(msg.vibration_y),
                float(msg.vibration_z),
                float(msg.clipping_0),
                float(msg.clipping_1),
                float(msg.clipping_2),
            ]
            self._append(vehicle_sysid, "vibration", timestamp_s, values)
        elif message_type == "EKF_STATUS_REPORT":
            values = [
                float(msg.velocity_variance),
                float(msg.pos_horiz_variance),
                float(msg.pos_vert_variance),
                float(msg.compass_variance),
                float(msg.terrain_alt_variance),
                float(getattr(msg, "airspeed_variance", 0.0)),
            ]
            self._append(vehicle_sysid, "ekf_variances", timestamp_s, values)

    def samples(
        self,
        sysid: int,
        buffer_name: str,
        *,
        now_s: float | None = None,
    ) -> tuple[NDArray[Any], NDArray[Any]]:
        """Return chronological numeric samples for an individual vehicle."""
        buffer = self._buffers.get((sysid, buffer_name))
        if buffer is None:
            return (
                np.empty(0, dtype=np.float64),
                np.empty((0, 0), dtype=np.float64),
            )
        return buffer.snapshot(now_s=now_s)

    def _append(
        self,
        sysid: int,
        buffer_name: str,
        timestamp_s: float,
        values: list[float],
    ) -> None:
        key = (sysid, buffer_name)
        buffer = self._buffers.get(key)
        if buffer is None:
            buffer = TimeRingBuffer(
                len(values),
                rate_hz=_BUFFER_RATE_HZ[buffer_name],
                duration_s=self.duration_s,
            )
            self._buffers[key] = buffer
        buffer.append(timestamp_s, values)


def _as_float(value: Any) -> float:
    if not isinstance(value, (int, float)):
        raise ValueError("numeric telemetry sample contains a non-numeric value")
    return float(value)
