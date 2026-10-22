import unittest
from io import BytesIO
from math import cos, radians
from pathlib import Path
import struct
import tempfile
from unittest.mock import patch

from pymavlink import mavutil
from sim.tools.record_fixture import (
    MESSAGE_INTERVALS_HZ,
    MESSAGE_IDS,
    REQUIRED_MESSAGE_TYPES,
    CONNECTION,
    fly_square,
    main,
    read_tlog,
    request_message_rates,
    square_waypoints,
    validate_fixture_data,
)


class FixturePlanTests(unittest.TestCase):
    def test_uses_the_requested_loopback_udp_endpoint(self) -> None:
        self.assertEqual(CONNECTION, "udp:127.0.0.1:14551")

    def test_requests_a_rate_for_each_required_message(self) -> None:
        self.assertEqual(set(MESSAGE_INTERVALS_HZ), set(REQUIRED_MESSAGE_TYPES))
        self.assertTrue(all(rate > 0 for rate in MESSAGE_INTERVALS_HZ.values()))

    def test_square_is_closed_and_keeps_altitude(self) -> None:
        waypoints = square_waypoints(side_m=8, altitude_m=20)
        self.assertEqual(waypoints, [(8, 0, -20), (8, 8, -20), (0, 8, -20), (0, 0, -20)])

    def test_fixture_validation_requires_all_messages_size_and_motion(self) -> None:
        counts = dict.fromkeys(REQUIRED_MESSAGE_TYPES, 1)
        positions = [(0, 0, 0), (0, 0, 20000), (5, 5, 20000)]
        attitudes = [(0.0, 0.0, 0.0), (0.1, 0.0, 0.0)]
        validate_fixture_data(counts, positions, attitudes, 1024)

        with self.assertRaisesRegex(ValueError, "missing message types"):
            validate_fixture_data({}, positions, attitudes, 1024)
        with self.assertRaisesRegex(ValueError, "5 MiB"):
            validate_fixture_data(counts, positions, attitudes, 5 * 1024 * 1024)
        with self.assertRaisesRegex(ValueError, "motion"):
            validate_fixture_data(counts, [(0, 0, 0), (0, 0, 20000)], attitudes, 1024)

    def test_host_invocation_runs_recorder_inside_sitl_container(self) -> None:
        result = type("Result", (), {"returncode": 0})()
        with patch("sim.tools.record_fixture.subprocess.run", return_value=result) as run:
            self.assertEqual(main(["--confirm-sitl"]), 0)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0][:6], ["docker", "compose", "exec", "-T", "sitl", "python3"])
        self.assertEqual(run.call_args_list[1].args[0][:3], ["docker", "compose", "cp"])

    def test_requests_interval_for_each_required_message_id(self) -> None:
        command = mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL
        sent = []
        connection = type(
            "Connection",
            (),
            {
                "target_system": 1,
                "target_component": 1,
                "mavlink": mavutil.mavlink,
                "mav": type("Sender", (), {"command_long_send": lambda self, *args: sent.append(args)})(),
                "recv_match": lambda self, **kwargs: type(
                    "Ack",
                    (),
                    {"command": command, "result": mavutil.mavlink.MAV_RESULT_ACCEPTED},
                )(),
            },
        )()

        request_message_rates(connection, mavutil.mavlink)

        self.assertEqual(len(sent), len(REQUIRED_MESSAGE_TYPES))
        self.assertEqual({int(args[4]) for args in sent}, set(MESSAGE_IDS.values()))

    def test_reads_raw_tlog_messages(self) -> None:
        dialect = mavutil.mavlink
        encoder = dialect.MAVLink(None)
        encoder.srcSystem = 1
        messages = [
            dialect.MAVLink_heartbeat_message(2, 3, 0, 4, 3, 3),
            dialect.MAVLink_global_position_int_message(1, 374000000, -1220800000, 20000, 20000, 0, 0, 0, 0),
            dialect.MAVLink_attitude_message(1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        ]
        messages.extend(
            [
                dialect.MAVLink_global_position_int_message(2, 374000100, -1220799900, 20000, 20000, 0, 0, 0, 0),
                dialect.MAVLink_attitude_message(2, 0.02, 0.0, 0.0, 0.0, 0.0, 0.0),
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.tlog"
            with path.open("wb") as capture:
                for index, message in enumerate(messages):
                    capture.write(struct.pack(">Q", 1_000_000 + index * 1_000_000))
                    capture.write(message.pack(encoder))

            counts, positions, attitudes = read_tlog(mavutil, path)

        self.assertEqual(counts["HEARTBEAT"], 1)
        self.assertEqual(counts["GLOBAL_POSITION_INT"], 2)
        self.assertEqual(counts["ATTITUDE"], 2)
        self.assertGreater(positions[-1][0], positions[0][0])
        self.assertEqual(len(attitudes), 2)

    def test_square_setpoints_encode_with_pymavlink_and_reach_each_waypoint(self) -> None:
        origin_lat_deg, origin_lon_deg = 37.4, -122.08
        output = BytesIO()

        class Connection:
            target_system = 1
            target_component = 1

            class Sender:
                def __init__(self) -> None:
                    self.encoder = mavutil.mavlink.MAVLink(output)
                    self.last_setpoint = None

                def set_position_target_local_ned_send(self, *args: object) -> None:
                    self.encoder.set_position_target_local_ned_send(*args)
                    self.last_setpoint = args

            def __init__(self) -> None:
                self.mav = self.Sender()

            def recv_match(self, **kwargs: object) -> object:
                assert self.mav.last_setpoint is not None
                north_m, east_m, down_m = self.mav.last_setpoint[5:8]
                return type(
                    "Position",
                    (),
                    {
                        "lat": round((origin_lat_deg + north_m / 111_320) * 1e7),
                        "lon": round(
                            (
                                origin_lon_deg
                                + east_m / (111_320 * cos(radians(origin_lat_deg)))
                            )
                            * 1e7
                        ),
                        "relative_alt": round(-down_m * 1000),
                    },
                )()

        connection = Connection()
        fly_square(
            connection,
            mavutil,
            square_waypoints(10, 20),
            origin_lat_deg,
            origin_lon_deg,
        )

        parser = mavutil.mavlink.MAVLink(None)
        self.assertEqual(len(parser.parse_buffer(output.getvalue())), 4)


if __name__ == "__main__":
    unittest.main()
