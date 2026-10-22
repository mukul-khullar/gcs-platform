#!/usr/bin/env python3
import argparse
from collections import Counter
from math import cos, hypot, radians
from pathlib import Path
import subprocess
import time
from typing import Any, Callable, Iterable, Mapping, Sequence


CONNECTION = "udp:127.0.0.1:14551"
RECORD_DURATION_S = 60.0
MAX_FIXTURE_BYTES = 5 * 1024 * 1024
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "nominal_60s.tlog"
CONTAINER_FIXTURE_PATH = Path("/tmp/nominal_60s.tlog")
MESSAGE_INTERVALS_HZ = {
    "HEARTBEAT": 1,
    "SYS_STATUS": 1,
    "GPS_RAW_INT": 5,
    "ATTITUDE": 10,
    "GLOBAL_POSITION_INT": 5,
    "VFR_HUD": 5,
    "EKF_STATUS_REPORT": 1,
    "VIBRATION": 2,
}
REQUIRED_MESSAGE_TYPES = tuple(MESSAGE_INTERVALS_HZ)
MESSAGE_IDS = {
    "HEARTBEAT": 0,
    "SYS_STATUS": 1,
    "GPS_RAW_INT": 24,
    "ATTITUDE": 30,
    "GLOBAL_POSITION_INT": 33,
    "VFR_HUD": 74,
    "EKF_STATUS_REPORT": 193,
    "VIBRATION": 241,
}
SQUARE_SIDE_M = 10.0
TAKEOFF_ALT_M = 20.0
POSITION_TARGET_TYPEMASK = sum(1 << bit for bit in (3, 4, 5, 6, 7, 8, 10, 11))


def load_mavutil() -> Any:
    from pymavlink import mavutil

    return mavutil


def square_waypoints(side_m: float, altitude_m: float) -> list[tuple[float, float, float]]:
    down_m = -altitude_m
    return [
        (side_m, 0.0, down_m),
        (side_m, side_m, down_m),
        (0.0, side_m, down_m),
        (0.0, 0.0, down_m),
    ]


def validate_fixture_data(
    counts: Mapping[str, int],
    positions_ned_m: Sequence[tuple[float, float, float]],
    attitudes_rad: Sequence[tuple[float, float, float]],
    size_bytes: int,
) -> None:
    missing = [message_type for message_type in REQUIRED_MESSAGE_TYPES if counts.get(message_type, 0) == 0]
    if missing:
        raise ValueError(f"missing message types: {', '.join(missing)}")
    if size_bytes >= MAX_FIXTURE_BYTES:
        raise ValueError("fixture must be under 5 MiB")
    if len(positions_ned_m) < 2:
        raise ValueError("motion data is missing from GLOBAL_POSITION_INT")
    horizontal_range_m = max(hypot(north, east) for north, east, _ in positions_ned_m)
    altitude_range_m = max(-down for _, _, down in positions_ned_m) - min(
        -down for _, _, down in positions_ned_m
    )
    if horizontal_range_m < 3.0 or altitude_range_m < 10.0:
        raise ValueError("motion data does not show takeoff and horizontal travel")
    if len(attitudes_rad) < 2 or max(
        max(sample[axis] for sample in attitudes_rad) - min(sample[axis] for sample in attitudes_rad)
        for axis in range(3)
    ) < 0.01:
        raise ValueError("motion data is missing from ATTITUDE")


def wait_for_ack(connection: Any, mavlink: Any, command: int, timeout_s: float = 5.0) -> Any:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        ack = connection.recv_match(
            type="COMMAND_ACK",
            blocking=True,
            timeout=min(1.0, deadline - time.monotonic()),
        )
        if ack is not None and ack.command == command:
            if ack.result == mavlink.MAV_RESULT_IN_PROGRESS:
                continue
            if ack.result != mavlink.MAV_RESULT_ACCEPTED:
                raise RuntimeError(f"MAVLink command {command} rejected with result {ack.result}")
            return ack
    raise TimeoutError(f"no acknowledgement for MAVLink command {command}")


def send_command(connection: Any, mavlink: Any, command: int, params: Iterable[float]) -> None:
    values = list(params)
    values.extend([0.0] * (7 - len(values)))
    connection.mav.command_long_send(
        connection.target_system,
        connection.target_component,
        command,
        0,
        *values[:7],
    )
    wait_for_ack(connection, mavlink, command)


def request_message_rates(connection: Any, mavlink: Any) -> None:
    for message_type, rate_hz in MESSAGE_INTERVALS_HZ.items():
        send_command(
            connection,
            mavlink,
            mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
            (MESSAGE_IDS[message_type], 1_000_000 / rate_hz),
        )


def wait_until(
    connection: Any,
    message_type: str,
    predicate: Callable[[Any], bool],
    timeout_s: float,
    description: str,
) -> Any:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        message = connection.recv_match(
            type=message_type,
            blocking=True,
            timeout=min(1.0, deadline - time.monotonic()),
        )
        if message is not None and predicate(message):
            return message
    raise TimeoutError(f"timed out waiting for {description}")


def set_guided_mode(connection: Any, mavutil: Any) -> None:
    mode_id = connection.mode_mapping().get("GUIDED")
    if mode_id is None:
        raise RuntimeError("vehicle does not advertise GUIDED mode")
    connection.mav.set_mode_send(
        connection.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        mode_id,
    )
    wait_until(
        connection,
        "HEARTBEAT",
        lambda heartbeat: heartbeat.custom_mode == mode_id,
        10.0,
        "GUIDED mode",
    )


def arm_and_takeoff(connection: Any, mavutil: Any) -> Any:
    send_command(
        connection,
        mavutil.mavlink,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        (1.0, 0.0),
    )
    wait_until(
        connection,
        "HEARTBEAT",
        lambda heartbeat: heartbeat.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED,
        15.0,
        "armed heartbeat",
    )
    send_command(
        connection,
        mavutil.mavlink,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, TAKEOFF_ALT_M),
    )
    return wait_until(
        connection,
        "GLOBAL_POSITION_INT",
        lambda position: position.relative_alt >= (TAKEOFF_ALT_M - 1.0) * 1000,
        45.0,
        f"takeoff to {TAKEOFF_ALT_M:g} m",
    )


def land_and_disarm(connection: Any, mavutil: Any) -> None:
    mode_id = connection.mode_mapping().get("LAND")
    if mode_id is None:
        raise RuntimeError("vehicle does not advertise LAND mode")
    connection.mav.set_mode_send(
        connection.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        mode_id,
    )
    wait_until(
        connection,
        "HEARTBEAT",
        lambda heartbeat: heartbeat.custom_mode == mode_id,
        10.0,
        "LAND mode",
    )
    wait_until(
        connection,
        "HEARTBEAT",
        lambda heartbeat: not heartbeat.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED,
        45.0,
        "landing and disarm",
    )


def fly_square(
    connection: Any,
    mavutil: Any,
    waypoints: Sequence[tuple[float, float, float]],
    origin_lat_deg: float,
    origin_lon_deg: float,
) -> None:
    for north_m, east_m, down_m in waypoints:
        deadline = time.monotonic() + 30.0
        next_setpoint_at = 0.0
        while time.monotonic() < deadline:
            if time.monotonic() >= next_setpoint_at:
                connection.mav.set_position_target_local_ned_send(
                    int(time.monotonic() * 1000) & 0xFFFFFFFF,
                    connection.target_system,
                    connection.target_component,
                    mavutil.mavlink.MAV_FRAME_LOCAL_NED,
                    POSITION_TARGET_TYPEMASK,
                    north_m,
                    east_m,
                    down_m,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                )
                next_setpoint_at = time.monotonic() + 1.0
            position = connection.recv_match(
                type="GLOBAL_POSITION_INT",
                blocking=True,
                timeout=0.5,
            )
            if position is None:
                continue
            latitude = position.lat * 1e-7
            longitude = position.lon * 1e-7
            north_error_m = (latitude - origin_lat_deg) * 111_320.0
            east_error_m = (
                (longitude - origin_lon_deg)
                * 111_320.0
                * cos(radians(origin_lat_deg))
            )
            if (
                hypot(north_error_m - north_m, east_error_m - east_m) < 1.5
                and abs(position.relative_alt / 1000 + down_m) < 2.0
            ):
                break
        else:
            raise TimeoutError(f"timed out reaching square waypoint N={north_m:g} E={east_m:g}")


def read_tlog(
    mavutil: Any,
    path: Path,
) -> tuple[Counter[str], list[tuple[float, float, float]], list[tuple[float, float, float]]]:
    reader = mavutil.mavlink_connection(str(path), planner_format=False)
    counts: Counter[str] = Counter()
    positions: list[tuple[float, float, float]] = []
    attitudes: list[tuple[float, float, float]] = []
    origin_lat_deg = None
    origin_lon_deg = None
    try:
        while True:
            message = reader.recv_match(blocking=False)
            if message is None:
                break
            message_type = message.get_type()
            counts[message_type] += 1
            if message_type == "GLOBAL_POSITION_INT":
                latitude = message.lat * 1e-7
                longitude = message.lon * 1e-7
                if origin_lat_deg is None:
                    origin_lat_deg = latitude
                    origin_lon_deg = longitude
                north_m = (latitude - origin_lat_deg) * 111_320.0
                east_m = (
                    (longitude - origin_lon_deg)
                    * 111_320.0
                    * cos(radians(origin_lat_deg))
                )
                positions.append((north_m, east_m, message.relative_alt / 1000))
            elif message_type == "ATTITUDE":
                attitudes.append((message.roll, message.pitch, message.yaw))
    finally:
        reader.close()
    ned_positions = [(north, east, -altitude) for north, east, altitude in positions]
    return counts, ned_positions, attitudes


def capture(mavutil: Any, duration_s: float, fixture_path: Path) -> Counter[str]:
    connection = mavutil.mavlink_connection(CONNECTION)
    temp_path = fixture_path.with_name(f".{fixture_path.stem}.{time.time_ns()}.tmp.tlog")
    flight_started = False
    try:
        heartbeat = connection.wait_heartbeat(timeout=30)
        if heartbeat is None:
            raise TimeoutError(f"no heartbeat received from {CONNECTION}")
        fixture_path.parent.mkdir(parents=True, exist_ok=True)
        recording_deadline = time.monotonic() + duration_s
        with temp_path.open("wb") as tlog_file:
            connection.logfile = tlog_file
            request_message_rates(connection, mavutil.mavlink)
            set_guided_mode(connection, mavutil)
            flight_started = True
            position = arm_and_takeoff(connection, mavutil)
            fly_square(
                connection,
                mavutil,
                square_waypoints(SQUARE_SIDE_M, TAKEOFF_ALT_M),
                position.lat * 1e-7,
                position.lon * 1e-7,
            )
            while time.monotonic() < recording_deadline:
                connection.recv_match(
                    blocking=True,
                    timeout=min(1.0, recording_deadline - time.monotonic()),
                )
        size_bytes = temp_path.stat().st_size
        counts, positions_ned_m, attitudes_rad = read_tlog(mavutil, temp_path)
        validate_fixture_data(counts, positions_ned_m, attitudes_rad, size_bytes)
        temp_path.replace(fixture_path)
    finally:
        try:
            if flight_started:
                connection.logfile = None
                land_and_disarm(connection, mavutil)
        finally:
            connection.close()
            temp_path.unlink(missing_ok=True)
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Arm SITL, fly a 10 m square, and record a 60-second MAVLink tlog."
    )
    parser.add_argument(
        "--confirm-sitl",
        action="store_true",
        help="confirm this command is connected only to the local ArduPilot SITL instance",
    )
    parser.add_argument("--duration-s", type=float, default=RECORD_DURATION_S)
    parser.add_argument("--in-container", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.confirm_sitl:
        parser.error("refusing to arm without --confirm-sitl")
    if args.duration_s <= 0:
        parser.error("--duration-s must be positive")

    if not args.in_container:
        run_result = subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "sitl",
                "python3",
                "/sim/tools/record_fixture.py",
                "--in-container",
                "--confirm-sitl",
                "--duration-s",
                str(args.duration_s),
            ],
            check=False,
        )
        if run_result.returncode != 0:
            return run_result.returncode
        copy_result = subprocess.run(
            [
                "docker",
                "compose",
                "cp",
                f"sitl:{CONTAINER_FIXTURE_PATH.as_posix()}",
                FIXTURE_PATH.relative_to(Path.cwd()).as_posix(),
            ],
            check=False,
        )
        if copy_result.returncode != 0:
            return copy_result.returncode
        print(f"Copied fixture to {FIXTURE_PATH}")
        return 0

    try:
        counts = capture(load_mavutil(), args.duration_s, CONTAINER_FIXTURE_PATH)
    except (OSError, RuntimeError, TimeoutError, ValueError) as error:
        parser.exit(1, f"fixture recording failed: {error}\n")

    print(f"Recorded {CONTAINER_FIXTURE_PATH} ({CONTAINER_FIXTURE_PATH.stat().st_size} bytes)")
    for message_type, count in sorted(counts.items()):
        print(f"{message_type}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
