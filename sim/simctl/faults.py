import argparse
from dataclasses import dataclass
import time
from typing import Any, Callable, Sequence


SIGNATURE_TIMEOUT_S = 5.0
PARAM_TIMEOUT_S = 0.5
PARAMETER_CANDIDATES = {
    "SIM_GPS_DISABLE": ("SIM_GPS_DISABLE",),
    "SIM_MAG1_OFS_X": ("SIM_MAG1_OFS_X", "SIM_MAG_OFS_X"),
    "SIM_MAG1_OFS_Y": ("SIM_MAG1_OFS_Y", "SIM_MAG_OFS_Y"),
    "SIM_MAG1_OFS_Z": ("SIM_MAG1_OFS_Z", "SIM_MAG_OFS_Z"),
    "SIM_ACC_RND": ("SIM_ACC_RND",),
    "SIM_BARO_DRIFT": ("SIM_BARO_DRIFT", "SIM_BAR2_DRIFT", "SIM_BAR3_DRIFT"),
    "SIM_BATT_VOLTAGE": ("SIM_BATT_VOLTAGE", "SIM_BATT1_VOLTAGE"),
    "SIM_RC_FAIL": ("SIM_RC_FAIL",),
}
FAULTS = {
    "gps_loss": (("GPS_RAW_INT",), (24,), "gps"),
    "compass_offset": (("EKF_STATUS_REPORT",), (193,), "compass"),
    "vibration": (("VIBRATION",), (241,), "vibration"),
    "baro_drift": (("EKF_STATUS_REPORT",), (193,), "baro"),
    "battery_sag": (("SYS_STATUS",), (1,), "battery"),
    "rc_loss": (("RC_CHANNELS", "RADIO_STATUS"), (65, 109), "rc"),
}
NEUTRAL = {
    "gps_loss": {"SIM_GPS_DISABLE": 0.0},
    "compass_offset": {
        "SIM_MAG1_OFS_X": 0.0,
        "SIM_MAG1_OFS_Y": 0.0,
        "SIM_MAG1_OFS_Z": 0.0,
    },
    "vibration": {"SIM_ACC_RND": 0.0},
    "baro_drift": {"SIM_BARO_DRIFT": 0.0},
    "battery_sag": {"SIM_BATT_VOLTAGE": 12.6},
    "rc_loss": {"SIM_RC_FAIL": 0.0},
}
MAV_CMD_REQUEST_MESSAGE = 512
MAV_CMD_SET_MESSAGE_INTERVAL = 511


class UnsupportedParameterError(RuntimeError):
    pass


def _type(message: Any) -> str:
    return message.get_type()


def _ekf_changed(before: Any, after: Any, fields: tuple[str, ...]) -> bool:
    return before is not None and after is not None and any(
        getattr(before, field, None) != getattr(after, field, None)
        for field in fields
    )


def _changed(kind: str, before: Any, after: Any) -> bool:
    if before is None or after is None:
        return False
    before_type, after_type = _type(before), _type(after)
    if kind == "gps":
        return before_type == after_type == "GPS_RAW_INT" and (
            after.fix_type < before.fix_type
            or after.satellites_visible < before.satellites_visible
        )
    if kind == "compass":
        return _ekf_changed(before, after, ("compass_variance", "flags"))
    if kind == "baro":
        return _ekf_changed(before, after, ("pos_vert_variance", "flags"))
    if kind == "vibration":
        return max(after.vibration_x, after.vibration_y, after.vibration_z) > max(
            before.vibration_x, before.vibration_y, before.vibration_z
        ) + 0.05
    if kind == "battery":
        return 0 < after.voltage_battery < before.voltage_battery - 50
    if before_type != after_type:
        return False
    if after_type == "RC_CHANNELS":
        return any(
            getattr(after, f"chan{i}_raw", 0) != getattr(before, f"chan{i}_raw", 0)
            for i in range(1, min(before.chancount, after.chancount, 18) + 1)
        ) or after.chancount < before.chancount
    return after.rssi < before.rssi


@dataclass
class FaultHandle:
    controller: "FaultController"
    name: str
    originals: dict[str, float]

    def clear(self) -> None:
        self.controller._restore(self.originals)
        self.controller.active.pop(self.name, None)


class FaultController:
    def __init__(
        self,
        connection: Any,
        *,
        timeout_s: float = SIGNATURE_TIMEOUT_S,
        parameter_timeout_s: float = PARAM_TIMEOUT_S,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.connection = connection
        self.timeout_s = timeout_s
        self.parameter_timeout_s = parameter_timeout_s
        self.monotonic = monotonic
        self.firmware_version: str | None = None
        self.active: dict[str, FaultHandle] = {}

    def _target(self) -> tuple[int, int]:
        return self.connection.target_system, self.connection.target_component

    @staticmethod
    def _param_bytes(name: str) -> bytes:
        encoded = name.encode("ascii")
        if len(encoded) > 16:
            raise ValueError(f"parameter name exceeds MAVLink's 16-byte limit: {name}")
        return encoded + b"\0"

    @staticmethod
    def _param_name(message: Any) -> str:
        name = message.param_id
        if isinstance(name, bytes):
            name = name.decode("ascii", errors="replace")
        return str(name).rstrip("\0")

    def _firmware(self) -> str:
        if self.firmware_version is not None:
            return self.firmware_version
        sysid, compid = self._target()
        self.connection.mav.command_long_send(
            sysid, compid, MAV_CMD_REQUEST_MESSAGE, 0, 148, 0, 0, 0, 0, 0, 0
        )
        version = self.connection.recv_match(
            type="AUTOPILOT_VERSION", blocking=True, timeout=1.0
        )
        if version is None:
            result = "unknown (AUTOPILOT_VERSION unavailable)"
        else:
            packed = int(version.flight_sw_version)
            result = (
                f"ArduCopter {packed >> 24}.{(packed >> 16) & 255}."
                f"{(packed >> 8) & 255}"
            )
        self.firmware_version = result
        return result

    def _read_param(self, name: str) -> tuple[str, float]:
        sysid, compid = self._target()
        candidates = PARAMETER_CANDIDATES.get(name, (name,))
        for candidate in candidates:
            self.connection.mav.param_request_read_send(
                sysid, compid, self._param_bytes(candidate), -1
            )
            deadline = self.monotonic() + self.parameter_timeout_s
            while self.monotonic() < deadline:
                reply = self.connection.recv_match(
                    type="PARAM_VALUE",
                    blocking=True,
                    timeout=min(0.1, deadline - self.monotonic()),
                )
                if reply is not None and self._param_name(reply) == candidate:
                    return candidate, float(reply.param_value)
        raise UnsupportedParameterError(
            f"no parameter {candidates!r} exists on firmware {self._firmware()}"
        )

    def _write_param(self, name: str, value: float) -> None:
        actual, _ = self._read_param(name)
        sysid, compid = self._target()
        self.connection.mav.param_set_send(
            sysid, compid, self._param_bytes(actual), float(value), 9
        )
        deadline = self.monotonic() + 1.0
        while self.monotonic() < deadline:
            reply = self.connection.recv_match(
                type="PARAM_VALUE",
                blocking=True,
                timeout=min(0.1, deadline - self.monotonic()),
            )
            if reply is not None and self._param_name(reply) == actual:
                if abs(float(reply.param_value) - value) > max(abs(value) * 1e-5, 1e-4):
                    raise RuntimeError(
                        f"firmware rejected {actual}={value}; returned {reply.param_value}"
                    )
                return
        raise TimeoutError(f"no PARAM_VALUE confirmation after setting {actual}")

    def _sample(self, types: tuple[str, ...], timeout_s: float) -> Any:
        return self.connection.recv_match(
            type=types, blocking=True, timeout=timeout_s
        )

    def _request_streams(self, message_ids: tuple[int, ...]) -> None:
        sysid, compid = self._target()
        for message_id in message_ids:
            self.connection.mav.command_long_send(
                sysid, compid, MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                message_id, 200_000, 0, 0, 0, 0, 0
            )

    def _apply(self, name: str, assignments: dict[str, float]) -> FaultHandle:
        types, message_ids, signature_kind = FAULTS[name]
        self._request_streams(message_ids)
        before = self._sample(types, min(self.timeout_s, 1.0))
        if before is None:
            raise TimeoutError(f"no baseline {types!r} telemetry for {name}")
        originals: dict[str, float] = {}
        try:
            for param, value in assignments.items():
                actual, old_value = self._read_param(param)
                originals[actual] = old_value
                self._write_param(actual, value)
            deadline = self.monotonic() + self.timeout_s
            while self.monotonic() < deadline:
                after = self._sample(types, min(0.2, deadline - self.monotonic()))
                if after is not None and _changed(signature_kind, before, after):
                    self.last_signature_changed = True
                    handle = FaultHandle(self, name, originals)
                    self.active[name] = handle
                    return handle
            raise TimeoutError(
                f"{name} applied but no expected {types!r} signature appeared "
                f"within {self.timeout_s:g}s"
            )
        except Exception as error:
            self.last_signature_changed = False
            if originals:
                try:
                    self._restore(originals)
                except Exception as restore_error:
                    raise RuntimeError(
                        f"{name} failed ({error}); restore failed ({restore_error})"
                    ) from restore_error
            raise

    def _restore(self, values: dict[str, float]) -> None:
        for name, value in values.items():
            self._write_param(name, value)

    def clear(self, name: str) -> None:
        handle = self.active.get(name)
        if handle is not None:
            handle.clear()
        else:
            for param, value in NEUTRAL[name].items():
                self._write_param(param, value)

    def gps_loss(self) -> FaultHandle:
        return self._apply("gps_loss", {"SIM_GPS_DISABLE": 1})

    def compass_offset(self, x: float, y: float, z: float) -> FaultHandle:
        return self._apply(
            "compass_offset",
            {"SIM_MAG1_OFS_X": x, "SIM_MAG1_OFS_Y": y, "SIM_MAG1_OFS_Z": z},
        )

    def vibration(self, level: float) -> FaultHandle:
        if level <= 0:
            raise ValueError("level must be positive")
        return self._apply("vibration", {"SIM_ACC_RND": level})

    def baro_drift(self, rate: float) -> FaultHandle:
        if rate == 0:
            raise ValueError("rate must be non-zero")
        return self._apply("baro_drift", {"SIM_BARO_DRIFT": rate})

    def battery_sag(self, voltage_v: float) -> FaultHandle:
        if voltage_v <= 0:
            raise ValueError("voltage must be positive")
        return self._apply("battery_sag", {"SIM_BATT_VOLTAGE": voltage_v})

    def rc_loss(self) -> FaultHandle:
        return self._apply("rc_loss", {"SIM_RC_FAIL": 1})


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="simctl")
    commands = parser.add_subparsers(dest="command", required=True)
    fault = commands.add_parser("fault")
    fault.add_argument("name", choices=tuple(FAULTS))
    state = fault.add_mutually_exclusive_group(required=True)
    state.add_argument("--on", action="store_true")
    state.add_argument("--off", action="store_true")
    fault.add_argument("--connection", default="udpin:127.0.0.1:14551")
    fault.add_argument("--x", type=float, default=120)
    fault.add_argument("--y", type=float, default=0)
    fault.add_argument("--z", type=float, default=0)
    fault.add_argument("--level", type=float, default=3)
    fault.add_argument("--rate", type=float, default=1)
    fault.add_argument("--v", type=float, default=9)
    args = parser.parse_args(argv)

    from pymavlink import mavutil

    connection = mavutil.mavlink_connection(args.connection)
    try:
        if connection.wait_heartbeat(timeout=10) is None:
            raise TimeoutError(f"no heartbeat from local SITL at {args.connection}")
        controller = FaultController(connection)
        if args.off:
            controller.clear(args.name)
            print(f"cleared {args.name}")
            return 0
        params = {
            "gps_loss": (),
            "compass_offset": (args.x, args.y, args.z),
            "vibration": (args.level,),
            "baro_drift": (args.rate,),
            "battery_sag": (args.v,),
            "rc_loss": (),
        }
        handle = getattr(controller, args.name)(*params[args.name])
        print(f"applied {args.name}; matching telemetry signature verified")
        del handle
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
