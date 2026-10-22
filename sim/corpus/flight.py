from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from pymavlink import mavutil


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from simctl.faults import FaultController


MESSAGE_IDS = (0, 1, 24, 30, 33, 65, 74, 109, 147, 193, 241)
TYPEMASK = sum(1 << bit for bit in (3, 4, 5, 6, 7, 8, 10, 11))
ROUTES = {
    "square": ((8, 0, -12), (8, 8, -12), (0, 8, -12), (0, 0, -12)),
    "triangle": ((10, 0, -12), (5, 9, -12), (0, 0, -12)),
    "racetrack": ((12, 0, -12), (12, 6, -12), (-12, 6, -12), (-12, 0, -12)),
}


def _request_rates(connection: Any) -> None:
    for message_id in MESSAGE_IDS:
        connection.mav.command_long_send(
            connection.target_system, connection.target_component,
            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
            message_id, 200_000, 0, 0, 0, 0, 0,
        )


def _wait_heartbeat(connection: Any, predicate: Any, timeout_s: float, reason: str) -> Any:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        heartbeat = connection.recv_match(type="HEARTBEAT", blocking=True, timeout=0.5)
        if heartbeat is not None and predicate(heartbeat):
            return heartbeat
    raise TimeoutError(f"timed out waiting for {reason}")


def _set_mode(connection: Any, mode: str) -> None:
    mode_id = connection.mode_mapping().get(mode)
    if mode_id is None:
        raise RuntimeError(f"SITL does not advertise {mode} mode")
    connection.mav.set_mode_send(
        connection.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        mode_id,
    )
    _wait_heartbeat(connection, lambda hb: hb.custom_mode == mode_id, 10, f"{mode} mode")


def run_flight(job: dict[str, Any], output: Path, connection_uri: str) -> None:
    connection = mavutil.mavlink_connection(connection_uri)
    controller = FaultController(connection)
    originals: dict[str, float] = {}
    handle = None
    try:
        if connection.wait_heartbeat(timeout=15) is None:
            raise TimeoutError(f"no heartbeat at {connection_uri}")

        def set_param(name: str, value: float) -> None:
            actual, old_value = controller._read_param(name)
            originals.setdefault(actual, old_value)
            controller._write_param(actual, value)

        for name, value in job.get("scenario_params", {}).items():
            set_param(name, float(value))
        for name, value in (
            ("SIM_WIND_SPD", float(job["wind_speed_mps"])),
            ("SIM_WIND_DIR", float(job["wind_direction_deg"])),
        ):
            set_param(name, value)

        connection.logfile = output.open("wb")
        _request_rates(connection)
        _set_mode(connection, "GUIDED")
        connection.mav.command_long_send(
            connection.target_system, connection.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
            1, 0, 0, 0, 0, 0, 0,
        )
        _wait_heartbeat(
            connection,
            lambda hb: bool(hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED),
            15,
            "armed state",
        )
        connection.mav.command_long_send(
            connection.target_system, connection.target_component,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0,
            0, 0, 0, 0, 0, 0, 12,
        )

        takeoff_deadline = time.monotonic() + 40
        start_boot_ms = None
        while time.monotonic() < takeoff_deadline:
            message = connection.recv_match(blocking=True, timeout=0.5)
            if message is not None and message.get_type() == "GLOBAL_POSITION_INT":
                start_boot_ms = int(message.time_boot_ms)
                if message.relative_alt >= 10_000:
                    break
        else:
            raise TimeoutError("takeoff did not reach 10 m relative altitude")
        if start_boot_ms is None:
            raise RuntimeError("no GLOBAL_POSITION_INT received after takeoff")

        route = ROUTES[job["mission_shape"]]
        started_at = time.monotonic()
        last_setpoint_s = -1.0
        last_waypoint = -1
        fault_started = False
        fault_cleared = False
        latest_boot_ms = start_boot_ms
        stale_since = time.monotonic()
        while True:
            message = connection.recv_match(blocking=True, timeout=0.25)
            if message is not None:
                stale_since = time.monotonic()
                if hasattr(message, "time_boot_ms"):
                    latest_boot_ms = int(message.time_boot_ms)
            elif time.monotonic() - stale_since > 5:
                raise TimeoutError("SITL telemetry stalled during flight")
            elapsed_s = ((latest_boot_ms - start_boot_ms) & 0xFFFFFFFF) / 1000
            if job["fault"] is not None and not fault_started and elapsed_s >= job["onset_s"]:
                handle = controller._apply(job["fault"], job["assignments"])
                fault_started = True
            if (
                handle is not None
                and not fault_cleared
                and elapsed_s >= job["onset_s"] + job["fault_duration_s"]
            ):
                handle.clear()
                fault_cleared = True
            waypoint = min(int(elapsed_s // 10), len(route) - 1)
            if elapsed_s >= 5 and (waypoint != last_waypoint or elapsed_s - last_setpoint_s >= 1):
                north_m, east_m, down_m = route[waypoint]
                connection.mav.set_position_target_local_ned_send(
                    latest_boot_ms, connection.target_system, connection.target_component,
                    mavutil.mavlink.MAV_FRAME_LOCAL_NED, TYPEMASK,
                    north_m, east_m, down_m, 0, 0, 0, 0, 0, 0, 0, 0,
                )
                last_waypoint, last_setpoint_s = waypoint, elapsed_s
            if elapsed_s >= float(job["duration_s"]):
                break
            if time.monotonic() - started_at > float(job["duration_s"]) + 60:
                raise TimeoutError("flight exceeded its wall-clock safety deadline")

        if handle is not None and not fault_cleared:
            handle.clear()
        _set_mode(connection, "LAND")
        _wait_heartbeat(
            connection,
            lambda hb: not bool(hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED),
            90,
            "landing and disarm",
        )
    finally:
        try:
            if handle is not None and not fault_cleared:
                handle.clear()
        finally:
            try:
                for name, value in reversed(tuple(originals.items())):
                    controller._write_param(name, value)
            finally:
                connection.logfile = None
                connection.close()
