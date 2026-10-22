#!/usr/bin/env python3
import argparse
import subprocess


def load_mavutil():
    from pymavlink import mavutil

    return mavutil


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wait for a MAVLink heartbeat and print its identity.")
    parser.add_argument("--connect", default="udpin:127.0.0.1:14550")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--in-container", action="store_true")
    args = parser.parse_args(argv)
    if not args.in_container:
        return subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "sitl",
                "python3",
                "/sim/tools/check_hb.py",
                "--in-container",
                "--connect",
                args.connect,
                "--timeout",
                str(args.timeout),
            ],
            check=False,
        ).returncode

    mavutil = load_mavutil()
    connection = mavutil.mavlink_connection(args.connect)
    heartbeat = connection.wait_heartbeat(timeout=args.timeout)
    if heartbeat is None:
        print(f"No heartbeat received on {args.connect} within {args.timeout:g}s")
        return 1
    print(f"sysid={heartbeat.get_srcSystem()} mode={mavutil.mode_string_v10(heartbeat)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
