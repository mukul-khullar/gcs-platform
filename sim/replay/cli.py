from __future__ import annotations

import argparse
import math
import socket
import time
from pathlib import Path

from pymavlink import mavutil


MIN_SPEED = 0.5
MAX_SPEED = 8.0


def _udp_destination(value: str) -> tuple[socket.socket, tuple[str, int]]:
    scheme, separator, endpoint = value.partition(":")
    host, port_separator, port_text = endpoint.rpartition(":")
    if scheme != "udp" or not separator or not port_separator or not host:
        raise ValueError("output must use udp:HOST:PORT")
    try:
        port = int(port_text)
    except ValueError as error:
        raise ValueError("UDP port must be an integer from 1 to 65535") from error
    if not 1 <= port <= 65535:
        raise ValueError("UDP port must be an integer from 1 to 65535")
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM)
    family, socktype, protocol, _, address = addresses[0]
    return socket.socket(family, socktype, protocol), address


def _validated_speed(speed: float) -> float:
    speed = float(speed)
    if not math.isfinite(speed) or not MIN_SPEED <= speed <= MAX_SPEED:
        raise ValueError(f"speed must be between {MIN_SPEED:g} and {MAX_SPEED:g}x")
    return speed


def replay_file(
    source: str | Path,
    output: str,
    *,
    speed: float = 1.0,
    loop: bool = False,
) -> int:
    speed = _validated_speed(speed)
    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    sock, destination = _udp_destination(output)
    message_count = 0
    next_origin: float | None = None
    first_interval_s = 0.0
    try:
        while True:
            reader = mavutil.mavlink_connection(
                str(source_path), dialect="ardupilotmega", robust_parsing=True
            )
            first_timestamp: float | None = None
            previous_timestamp: float | None = None
            last_target: float | None = None
            try:
                while True:
                    message = reader.recv_match(blocking=False)
                    if message is None:
                        break
                    if message.get_type() == "BAD_DATA":
                        raise ValueError(f"invalid MAVLink frame in {source_path}")
                    frame = message.get_msgbuf()
                    if not frame:
                        raise ValueError(f"empty MAVLink frame in {source_path}")
                    timestamp = float(message._timestamp)
                    if previous_timestamp is not None and timestamp < previous_timestamp:
                        raise ValueError("tlog timestamps must be non-decreasing")
                    if first_timestamp is None:
                        first_timestamp = timestamp
                        origin = next_origin if next_origin is not None else time.monotonic()
                    else:
                        interval_s = timestamp - previous_timestamp
                        if message_count == 1:
                            first_interval_s = interval_s
                    target = origin + (timestamp - first_timestamp) / speed
                    delay_s = target - time.monotonic()
                    if delay_s > 0:
                        time.sleep(delay_s)
                    sock.sendto(frame, destination)
                    message_count += 1
                    previous_timestamp = timestamp
                    last_target = target
            finally:
                reader.close()

            if not loop:
                if first_timestamp is None:
                    raise ValueError(f"no MAVLink frames found in {source_path}")
                return message_count
            if first_timestamp is None:
                raise ValueError(f"no MAVLink frames found in {source_path}")
            if last_target is None:
                raise ValueError(f"no MAVLink frames found in {source_path}")
            next_origin = max(last_target + first_interval_s / speed, time.monotonic())
    finally:
        sock.close()


def _speed_argument(value: str) -> float:
    try:
        return _validated_speed(float(value))
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="replay")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="replay a MAVLink .tlog over UDP")
    run.add_argument("flight", type=Path)
    run.add_argument("--speed", type=_speed_argument, default=1.0)
    run.add_argument("--out", required=True, help="UDP destination, e.g. udp:127.0.0.1:14551")
    run.add_argument("--loop", action="store_true")
    args = parser.parse_args(argv)
    try:
        count = replay_file(args.flight, args.out, speed=args.speed, loop=args.loop)
    except KeyboardInterrupt:
        return 130
    print(f"replayed {count} MAVLink messages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
