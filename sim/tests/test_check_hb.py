import io
import sys
from types import ModuleType
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

pymavlink_stub = ModuleType("pymavlink")
pymavlink_stub.mavutil = MagicMock()
with patch.dict(sys.modules, {"pymavlink": pymavlink_stub}):
    from sim.tools import check_hb


class HeartbeatCheckTests(unittest.TestCase):
    def test_prints_system_id_and_mode(self) -> None:
        message = type("Heartbeat", (), {"get_srcSystem": lambda self: 7})()
        connection = type("Connection", (), {"wait_heartbeat": lambda self, timeout: message})()
        output = io.StringIO()

        with (
            patch.object(check_hb, "load_mavutil", return_value=pymavlink_stub.mavutil),
            patch.object(pymavlink_stub.mavutil, "mavlink_connection", return_value=connection),
            patch.object(pymavlink_stub.mavutil, "mode_string_v10", return_value="GUIDED"),
            redirect_stdout(output),
        ):
            result = check_hb.main(["--in-container", "--connect", "udpin:127.0.0.1:14550"])

        self.assertEqual(result, 0)
        self.assertIn("sysid=7", output.getvalue())
        self.assertIn("mode=GUIDED", output.getvalue())

    def test_fails_when_heartbeat_times_out(self) -> None:
        connection = type("Connection", (), {"wait_heartbeat": lambda self, timeout: None})()

        with (
            patch.object(check_hb, "load_mavutil", return_value=pymavlink_stub.mavutil),
            patch.object(pymavlink_stub.mavutil, "mavlink_connection", return_value=connection),
        ):
            self.assertEqual(check_hb.main(["--in-container", "--timeout", "0.01"]), 1)

    def test_host_check_executes_inside_isolated_container(self) -> None:
        result = type("Result", (), {"returncode": 0})()
        with patch.object(check_hb.subprocess, "run", return_value=result) as run:
            self.assertEqual(check_hb.main([]), 0)
        self.assertEqual(run.call_args.args[0][:5], ["docker", "compose", "exec", "-T", "sitl"])


if __name__ == "__main__":
    unittest.main()
