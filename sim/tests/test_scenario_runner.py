import math
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from sim.simctl.runner import Scenario, ScenarioRunner, load_scenario

SCENARIOS = Path(__file__).parents[1] / "scenarios"


class FakeMAV:
    def __init__(self) -> None:
        self.params: dict[str, float] = {}

    def param_set_send(self, system: int, component: int, param: bytes, value: float, kind: int) -> None:
        self.params[param.decode("utf-8").rstrip("\0")] = float(value)


class FakeConnection:
    target_system = 1
    target_component = 1

    def __init__(self) -> None:
        self.mav = FakeMAV()
        self.position = (0.0, 0.0, 0.0)
        self._mode = "STABILIZE"
        self._armed = False
        self.telemetry: list[Any] = [
            type("Heartbeat", (), {"get_type": lambda self: "HEARTBEAT", "base_mode": 0, "custom_mode": 0})(),
            type("Pos", (), {"get_type": lambda self: "GLOBAL_POSITION_INT", "lat": 374000000, "lon": -1220800000, "relative_alt": 0})(),
        ]

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        self._mode = value

    @property
    def armed(self) -> bool:
        return self._armed

    @armed.setter
    def armed(self, value: bool) -> None:
        self._armed = value

    def recv_match(self, blocking: bool = False, timeout: float = 0.0, **kwargs: Any) -> Any:
        if self.telemetry:
            return self.telemetry.pop(0)
        return None

    def set_mode_send(self, system: int, flag: int, mode: int) -> None:
        self.mode = "GUIDED" if mode == 4 else "AUTO"
        self.telemetry.append(
            type("Heartbeat", (), {"get_type": lambda self: "HEARTBEAT", "base_mode": 128, "custom_mode": mode})()
        )

    def command_long_send(self, system: int, component: int, command: int, confirmation: int, *params: float) -> None:
        if command == 400:
            self.armed = True
        if command == 22:
            self.position = (self.position[0], self.position[1], float(params[6]))
            self.telemetry.append(
                type(
                    "Pos",
                    (),
                    {"get_type": lambda self: "GLOBAL_POSITION_INT", "lat": 374000000, "lon": -1220800000, "relative_alt": int(self.position[2] * 1000)},
                )()
            )

    def set_position_target_local_ned_send(self, *args: Any) -> None:
        north, east, down = args[5:8]
        self.position = (float(north), float(east), float(-down))
        self.telemetry.append(
            type(
                "Pos",
                (),
                {"get_type": lambda self: "GLOBAL_POSITION_INT", "lat": 374000000, "lon": -1220800000, "relative_alt": int(self.position[2] * 1000)},
            )()
        )


def test_scenarios_load_and_validate_timeline() -> None:
    names = []
    for scenario_path in sorted(SCENARIOS.glob("*.yaml")):
        scenario = load_scenario(scenario_path)
        names.append(scenario.name)
        assert scenario.duration_s > 0
        assert scenario.home.lat_deg == pytest.approx(37.4)
        assert scenario.timeline

    assert names == ["gps_loss_at_40s", "nominal_square", "wind_gust_wp_mission"]

    with pytest.raises(ValidationError):
        Scenario.model_validate({
            "name": "bad",
            "duration_s": 1,
            "home": {"lat_deg": 37.4, "lon_deg": -122.08},
            "vehicle_params": {"FENCE_ENABLE": 1},
            "timeline": [{"t_s": 0, "action": {"type": "set_param", "param": "", "value": 0}}],
        })


def test_runner_reproduces_trajectory_between_runs() -> None:
    scenario = load_scenario(SCENARIOS / "nominal_square.yaml")
    first = ScenarioRunner(scenario, FakeConnection()).run()
    second = ScenarioRunner(scenario, FakeConnection()).run()
    assert len(first) == len(second)
    squared = [
        (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2
        for a, b in zip(first, second)
    ]
    rms = math.sqrt(sum(squared) / len(squared))
    assert rms <= 2.0


@pytest.mark.sitl
@pytest.mark.skip(reason="requires local ArduPilot SITL on 127.0.0.1:14551")
def test_sitl_runner_executes_live_scenario() -> None:
    from pymavlink import mavutil

    scenario = load_scenario(SCENARIOS / "nominal_square.yaml")
    connection = mavutil.mavlink_connection("udpin:127.0.0.1:14551")
    try:
        trajectory = ScenarioRunner(scenario, connection).run()
    finally:
        connection.close()
    assert len(trajectory) >= 1
