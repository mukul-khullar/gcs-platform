"""Normalize ArduPilot MAVLink messages into versioned telemetry frames."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from pymavlink.dialects.v20 import ardupilotmega

from bridge.models import FrameModel, Topic

from .conversions import (
    cdeg_to_deg,
    centi_to_unitless,
    centiamps_to_amps,
    cmps_to_mps,
    deg_e7_to_deg,
    millivolts_to_volts,
    mm_to_m,
    nullable_int,
)
from .rate_limiter import TopicRateLimiter

__all__ = [
    "Normalizer",
    "centiamps_to_amps",
    "centi_to_unitless",
    "cdeg_to_deg",
    "cmps_to_mps",
    "deg_e7_to_deg",
    "millivolts_to_volts",
    "mm_to_m",
    "nullable_int",
    "normalize_message",
]


class Normalizer:
    """Map MAVLink messages to contract topics with per-system/topic sequences."""

    def __init__(self, rate_limiter: TopicRateLimiter | None = None) -> None:
        self._rate_limiter = rate_limiter or TopicRateLimiter.from_yaml()
        self._sequences: dict[tuple[int, str], int] = defaultdict(int)

    def normalize(
        self, msg: Any, *, t_wall_ms: int, now_s: float | None = None
    ) -> FrameModel | None:
        """Normalize one supported message, returning None if it is throttled."""
        topic, data = _topic_data(str(msg.get_type()), msg)
        if topic is None or data is None:
            return None
        if not self._rate_limiter.allow(topic, now_s=now_s):
            return None

        sysid = int(msg.get_srcSystem())
        sequence_key = (sysid, topic)
        seq = self._sequences[sequence_key]
        self._sequences[sequence_key] += 1
        return FrameModel(
            v=1,
            type=Topic(topic),
            seq=seq,
            sysid=sysid,
            t_wall_ms=t_wall_ms,
            t_boot_ms=_boot_time_ms(msg),
            data=data,
        )


def normalize_message(msg: Any, *, t_wall_ms: int) -> FrameModel | None:
    """Normalize one MAVLink message without applying topic rate limits."""
    unrestricted = TopicRateLimiter(
        {
            "telemetry.attitude": None,
            "telemetry.position": None,
            "vehicle.status": None,
            "health.summary": None,
            "anomaly.event": None,
            "mission.proposal": None,
            "mission.state": None,
        }
    )
    return Normalizer(unrestricted).normalize(msg, t_wall_ms=t_wall_ms, now_s=0.0)


def _boot_time_ms(msg: Any) -> int:
    raw_time = getattr(msg, "time_boot_ms", None)
    if raw_time is not None:
        return int(raw_time)
    time_usec = getattr(msg, "time_usec", 0)
    return int(time_usec // 1000)


def _topic_data(
    message_type: str, msg: Any
) -> tuple[str | None, dict[str, Any] | None]:
    if message_type == "ATTITUDE":
        return "telemetry.attitude", {
            "roll_rad": float(msg.roll),
            "pitch_rad": float(msg.pitch),
            "yaw_rad": float(msg.yaw),
            "rates_rps": [
                float(msg.rollspeed),
                float(msg.pitchspeed),
                float(msg.yawspeed),
            ],
        }
    if message_type == "GLOBAL_POSITION_INT":
        return "telemetry.position", {
            "lat_deg": deg_e7_to_deg(msg.lat),
            "lon_deg": deg_e7_to_deg(msg.lon),
            "alt_msl_m": mm_to_m(msg.alt),
            "alt_rel_m": mm_to_m(msg.relative_alt),
            "vel_ned_mps": [
                cmps_to_mps(msg.vx),
                cmps_to_mps(msg.vy),
                cmps_to_mps(msg.vz),
            ],
            "heading_deg": cdeg_to_deg(msg.hdg),
        }
    if message_type == "HEARTBEAT":
        if msg.type == ardupilotmega.MAV_TYPE_GCS:
            return None, None
        return "vehicle.status", {
            "armed": bool(msg.base_mode & ardupilotmega.MAV_MODE_FLAG_SAFETY_ARMED),
            "mode": str(msg.custom_mode),
            "system_status": int(msg.system_status),
            "mission_seq": None,
        }
    return None, None
