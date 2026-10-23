"""Deterministic synthetic ArduPilot MAVLink 2 telemetry logs."""

from __future__ import annotations

import math
import random
import struct
from pathlib import Path

from pymavlink.dialects.v20 import ardupilotmega

_EPOCH_USEC = 1_700_000_000_000_000
_LAT_ORIGIN_DEG = 37.4219999
_LON_ORIGIN_DEG = -122.0840575


def make_synthetic_tlog(
    path: str | Path, duration_s: float = 60, seed: int = 0
) -> None:
    """Write a MAVLink 2 ArduPilot .tlog with smooth, seeded vehicle telemetry.

    The log uses sysid/compid 1/1 and a big-endian Unix-microsecond timestamp
    before every MAVLink packet. Rates are heartbeat 1 Hz, attitude 20 Hz,
    global position 10 Hz, and GPS/EKF/vibration/system status 2 Hz.
    """
    if not math.isfinite(duration_s) or duration_s <= 0:
        raise ValueError("duration_s must be a finite positive number")

    rng = random.Random(seed)
    packet_buffer = bytearray()
    writer = _PacketWriter(packet_buffer)
    mav = ardupilotmega.MAVLink(writer, srcSystem=1, srcComponent=1)
    mav.robust_parsing = True
    log_path = Path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    events = (
        (1, 0.0, _heartbeat),
        (20, 0.0, _attitude),
        (10, 0.0, _global_position),
        (2, 0.0, _gps_raw),
        (2, 0.0, _ekf_status),
        (2, 0.0, _vibration),
        (2, 0.0, _sys_status),
    )
    scheduled: list[tuple[float, int, int, object]] = []
    order = 0
    for rate_hz, phase_s, factory in events:
        tick = 0
        timestamp_s = phase_s
        while timestamp_s < duration_s:
            scheduled.append((timestamp_s, order, tick, factory))
            tick += 1
            order += 1
            timestamp_s = phase_s + tick / rate_hz
    scheduled.sort(key=lambda event: (event[0], event[1]))

    with log_path.open("wb") as log_file:
        for timestamp_s, _, tick, factory in scheduled:
            packet_buffer.clear()
            boot_ms = round(timestamp_s * 1000)
            factory(mav, timestamp_s, boot_ms, tick, rng)
            packet = bytes(packet_buffer)
            if not packet or packet[0] != 0xFD:
                raise RuntimeError("pymavlink did not encode a MAVLink 2 packet")
            timestamp_usec = _EPOCH_USEC + round(timestamp_s * 1_000_000)
            log_file.write(struct.pack(">Q", timestamp_usec))
            log_file.write(packet)


class _PacketWriter:
    def __init__(self, buffer: bytearray) -> None:
        self._buffer = buffer

    def write(self, packet: bytes) -> int:
        self._buffer.extend(packet)
        return len(packet)


def _heartbeat(
    mav: ardupilotmega.MAVLink,
    timestamp_s: float,
    boot_ms: int,
    tick: int,
    rng: random.Random,
) -> None:
    del timestamp_s, boot_ms, tick, rng
    mav.heartbeat_send(
        ardupilotmega.MAV_TYPE_QUADROTOR,
        ardupilotmega.MAV_AUTOPILOT_ARDUPILOTMEGA,
        0,
        0,
        ardupilotmega.MAV_STATE_ACTIVE,
    )


def _attitude(
    mav: ardupilotmega.MAVLink,
    timestamp_s: float,
    boot_ms: int,
    tick: int,
    rng: random.Random,
) -> None:
    roll_rad = 0.08 * math.sin(timestamp_s * 0.4) + rng.uniform(-0.001, 0.001)
    pitch_rad = 0.05 * math.sin(timestamp_s * 0.25 + 0.6)
    yaw_rad = (0.15 * timestamp_s) % (2.0 * math.pi)
    mav.attitude_send(
        boot_ms,
        roll_rad,
        pitch_rad,
        yaw_rad,
        0.032 * math.cos(timestamp_s * 0.4),
        0.0125 * math.cos(timestamp_s * 0.25 + 0.6),
        0.15,
    )
    del tick


def _position(timestamp_s: float) -> tuple[int, int, int, int, int, int, int]:
    lat_deg = _LAT_ORIGIN_DEG + 0.00008 * math.sin(timestamp_s / 30.0)
    lon_deg = _LON_ORIGIN_DEG + 0.00012 * math.sin(timestamp_s / 40.0)
    alt_msl_m = 30.0 + 0.5 * math.sin(timestamp_s / 8.0)
    alt_rel_m = 12.0 + 0.25 * math.sin(timestamp_s / 10.0)
    north_mps = 1.5 * math.cos(timestamp_s / 30.0)
    east_mps = 1.0 * math.cos(timestamp_s / 40.0)
    down_mps = -0.05 * math.cos(timestamp_s / 10.0)
    return (
        round(lat_deg * 1e7),
        round(lon_deg * 1e7),
        round(alt_msl_m * 1000),
        round(alt_rel_m * 1000),
        round(north_mps * 100),
        round(east_mps * 100),
        round(down_mps * 100),
    )


def _global_position(
    mav: ardupilotmega.MAVLink,
    timestamp_s: float,
    boot_ms: int,
    tick: int,
    rng: random.Random,
) -> None:
    del tick, rng
    lat, lon, alt, alt_rel, vx, vy, vz = _position(timestamp_s)
    yaw_rad = (0.15 * timestamp_s) % (2.0 * math.pi)
    mav.global_position_int_send(
        boot_ms,
        lat,
        lon,
        alt,
        alt_rel,
        vx,
        vy,
        vz,
        round(math.degrees(yaw_rad) * 100) % 36000,
    )


def _gps_raw(
    mav: ardupilotmega.MAVLink,
    timestamp_s: float,
    boot_ms: int,
    tick: int,
    rng: random.Random,
) -> None:
    del tick, rng
    lat, lon, alt, _, vx, vy, _ = _position(timestamp_s)
    speed_cms = round(math.hypot(vx, vy))
    course_cdeg = round(math.degrees(math.atan2(vy, vx)) * 100) % 36000
    mav.gps_raw_int_send(
        boot_ms * 1000,
        3,
        lat,
        lon,
        alt,
        80,
        120,
        speed_cms,
        course_cdeg,
        12,
        alt_ellipsoid=alt + 8000,
        h_acc=800,
        v_acc=1200,
        vel_acc=100,
        hdg_acc=500,
    )


def _ekf_status(
    mav: ardupilotmega.MAVLink,
    timestamp_s: float,
    boot_ms: int,
    tick: int,
    rng: random.Random,
) -> None:
    del boot_ms, tick
    phase = timestamp_s / 20.0
    mav.ekf_status_report_send(
        0x1FFF,
        0.08 + 0.005 * math.sin(phase),
        0.12 + 0.01 * math.sin(phase + 0.5),
        0.15 + 0.01 * math.cos(phase),
        0.05 + rng.uniform(0.0, 0.005),
        0.1,
        airspeed_variance=0.0,
    )


def _vibration(
    mav: ardupilotmega.MAVLink,
    timestamp_s: float,
    boot_ms: int,
    tick: int,
    rng: random.Random,
) -> None:
    del boot_ms, tick
    mav.vibration_send(
        round(timestamp_s * 1_000_000),
        0.12 + 0.015 * math.sin(timestamp_s * 0.7) + rng.uniform(-0.002, 0.002),
        0.1 + 0.012 * math.sin(timestamp_s * 0.6 + 0.4),
        0.15 + 0.01 * math.cos(timestamp_s * 0.5),
        0,
        0,
        0,
    )


def _sys_status(
    mav: ardupilotmega.MAVLink,
    timestamp_s: float,
    boot_ms: int,
    tick: int,
    rng: random.Random,
) -> None:
    del boot_ms, tick
    remaining_pct = max(
        0, min(100, round(95 - timestamp_s / 600 + rng.uniform(-0.1, 0.1)))
    )
    mav.sys_status_send(
        0xFFFFFFFF,
        0xFFFFFFFF,
        0xFFFFFFFF,
        350,
        round(16_500 - timestamp_s * 0.1),
        -420,
        remaining_pct,
        0,
        0,
        0,
        0,
        0,
        0,
    )
