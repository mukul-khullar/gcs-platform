from collections import deque
from types import SimpleNamespace
from typing import Any

import pytest

from sim.simctl.faults import FaultController, UnsupportedParameterError


def msg(kind: str, **attrs: Any) -> Any:
    return SimpleNamespace(get_type=lambda: kind, **attrs)


class FakeMav:
    def __init__(self, params: dict[str, float], changed: Any) -> None:
        self.params = params
        self.changed = changed
        self.reads: list[str] = []
        self.writes: list[str] = []
        self.pending = deque([msg("AUTOPILOT_VERSION", flight_sw_version=0x04070200)])
        self.pending.append(changed[0])

    def command_long_send(self, *args: Any) -> None:
        if args[2] == 512:
            self.pending.append(msg("AUTOPILOT_VERSION", flight_sw_version=0x04070200))

    def param_request_read_send(self, *args: Any) -> None:
        name = args[2].rstrip(b"\0").decode()
        self.reads.append(name)
        if name in self.params:
            self.pending.append(msg("PARAM_VALUE", param_id=name, param_value=self.params[name]))

    def param_set_send(self, *args: Any) -> None:
        name, value = args[2].rstrip(b"\0").decode(), args[3]
        self.params[name] = value
        self.writes.append(name)
        self.pending.append(msg("PARAM_VALUE", param_id=name, param_value=value))
        self.pending.append(self.changed[1])

    def recv_match(self, type: Any = None, **kwargs: Any) -> Any:
        for _ in range(len(self.pending)):
            item = self.pending.popleft()
            if type is None or item.get_type() in (type if isinstance(type, tuple) else (type,)):
                return item
            self.pending.append(item)
        return None


class FakeConnection:
    target_system = target_component = 1

    def __init__(self, params: dict[str, float], changed: Any) -> None:
        self.mav = FakeMav(params, changed)

    def recv_match(self, **kwargs: Any) -> Any:
        return self.mav.recv_match(**kwargs)


CASES = [
    ("gps_loss", (), {"SIM_GPS_DISABLE": 0}, "GPS_RAW_INT", {"fix_type": 3, "satellites_visible": 10}, {"fix_type": 1, "satellites_visible": 0}),
    ("compass_offset", (120, -30, 15), {"SIM_MAG1_OFS_X": 0, "SIM_MAG1_OFS_Y": 0, "SIM_MAG1_OFS_Z": 0}, "EKF_STATUS_REPORT", {"compass_variance": 0.1, "pos_vert_variance": 0.1, "pos_horiz_variance": 0.1, "flags": 1}, {"compass_variance": 1, "pos_vert_variance": 0.1, "pos_horiz_variance": 0.1, "flags": 1}),
    ("vibration", (3,), {"SIM_ACC_RND": 0}, "VIBRATION", {"vibration_x": 0.01, "vibration_y": 0.01, "vibration_z": 0.01}, {"vibration_x": 3, "vibration_y": 0.01, "vibration_z": 0.01}),
    ("baro_drift", (1,), {"SIM_BARO_DRIFT": 0}, "EKF_STATUS_REPORT", {"compass_variance": 0.1, "pos_vert_variance": 0.1, "pos_horiz_variance": 0.1, "flags": 1}, {"compass_variance": 0.1, "pos_vert_variance": 1, "pos_horiz_variance": 0.1, "flags": 1}),
    ("battery_sag", (9,), {"SIM_BATT_VOLTAGE": 12.6}, "SYS_STATUS", {"voltage_battery": 12600}, {"voltage_battery": 9000}),
    ("rc_loss", (), {"SIM_RC_FAIL": 0}, "RC_CHANNELS", {"chancount": 4, "chan1_raw": 1500}, {"chancount": 4, "chan1_raw": 0}),
]


@pytest.mark.parametrize(("method", "args", "initial", "kind", "before", "after"), CASES)
def test_fault_signature_within_five_seconds_and_clear_restores(
    method: str, args: tuple[float, ...], initial: dict[str, float],
    kind: str, before: dict[str, float], after: dict[str, float],
) -> None:
    connection = FakeConnection(initial.copy(), (msg(kind, **before), msg(kind, **after)))
    controller = FaultController(connection, timeout_s=5)
    handle = getattr(controller, method)(*args)
    assert controller.last_signature_changed
    assert all(name in connection.mav.reads for name in connection.mav.writes)
    handle.clear()
    assert connection.mav.params == initial


def test_missing_parameter_error_includes_firmware_version() -> None:
    fake = FakeConnection({}, (msg("GPS_RAW_INT", fix_type=3, satellites_visible=9),) * 2)
    with pytest.raises(UnsupportedParameterError, match="ArduCopter 4.7.2"):
        FaultController(fake, timeout_s=0.01, parameter_timeout_s=0.01).gps_loss()


def test_missing_signature_fails_loudly() -> None:
    initial = {"SIM_GPS_DISABLE": 0.0}
    base = msg("GPS_RAW_INT", fix_type=3, satellites_visible=9)
    controller = FaultController(FakeConnection(initial, (base, base)), timeout_s=0.01)
    with pytest.raises(TimeoutError, match="GPS_RAW_INT"):
        controller.gps_loss()
