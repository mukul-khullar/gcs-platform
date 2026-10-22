from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Callable, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator


class Home(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat_deg: float
    lon_deg: float
    alt_m: float = 0.0
    yaw_deg: float = 0.0


class SetParamAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["set_param"] = "set_param"
    param: str
    value: float

    @field_validator("param")
    @classmethod
    def validate_param(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("param must be a non-empty parameter name")
        return cleaned


class FaultAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["fault"] = "fault"
    subsystem: str
    fault: str
    duration_s: float | None = None


class CommandAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["command"] = "command"
    name: str
    north_m: float | None = None
    east_m: float | None = None
    alt_rel_m: float | None = None
    yaw_deg: float | None = None
    mode: str | None = None
    params: dict[str, float] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        allowed = {"arm", "disarm", "takeoff", "goto", "rtl", "land", "set_mode_guided", "set_mode_auto"}
        if value not in allowed:
            raise ValueError(f"unsupported command: {value!r}; expected one of {sorted(allowed)}")
        return value


class WaitForAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["wait_for"] = "wait_for"
    condition: str
    timeout_s: float = Field(gt=0)


Action = SetParamAction | FaultAction | CommandAction | WaitForAction


class TimelineEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    t_s: float = Field(ge=0)
    action: Action


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    duration_s: float = Field(gt=0)
    home: Home
    vehicle_params: dict[str, float] = Field(default_factory=dict)
    timeline: list[TimelineEntry]

    @staticmethod
    def from_yaml(path: str | Path) -> "Scenario":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"YAML scenario must decode to a mapping: {path}")
        return Scenario.model_validate(data)


ActionAdapter = TypeAdapter(Action)


def load_scenario(path: str | Path) -> Scenario:
    return Scenario.from_yaml(path)


class ScenarioRunner:
    def __init__(self, scenario: Scenario, connection: Any, *, clock: Callable[[], float] | None = None, emit: Callable[[str], None] | None = None) -> None:
        self.scenario = scenario
        self.connection = connection
        self.clock = clock or time.monotonic
        self.emit = emit or (lambda _: None)
        self.trajectory: list[tuple[float, float, float]] = []
        self.logs: list[dict[str, Any]] = []
        self.position = (0.0, 0.0, 0.0)
        self.origin_lat_deg = scenario.home.lat_deg
        self.origin_lon_deg = scenario.home.lon_deg
        self.armed = False
        self.mode = "STABILIZE"
        self.boot_ms = 0
        self.fault_signature_changed = False
        self._fault_handles: list[tuple[Any, float | None]] = []

    def _log(self, action: Any, status: str, details: str | None = None) -> None:
        payload = {
            "t_s": self.clock(),
            "action": action.model_dump(mode="json") if hasattr(action, "model_dump") else action,
            "status": status,
        }
        if details:
            payload["details"] = details
        self.logs.append(payload)
        self.emit(json.dumps(payload, sort_keys=True))

    def _wait_until(self, target_t: float) -> None:
        now = self.clock()
        if target_t > now:
            remaining = target_t - now
            deadline = time.monotonic() + remaining
            while time.monotonic() < deadline:
                self._poll_telemetry(timeout=min(0.05, max(0.01, deadline - time.monotonic())))

    def _poll_telemetry(self, timeout: float = 0.05) -> None:
        message = self.connection.recv_match(blocking=True, timeout=timeout)
        if message is None:
            return
        if getattr(message, "get_type", lambda: "")() == "GLOBAL_POSITION_INT":
            latitude_deg = float(getattr(message, "lat", 0.0)) * 1e-7
            longitude_deg = float(getattr(message, "lon", 0.0)) * 1e-7
            north_m = (latitude_deg - self.origin_lat_deg) * 111_320.0
            east_m = (
                (longitude_deg - self.origin_lon_deg)
                * 111_320.0
                * math.cos(math.radians(self.origin_lat_deg))
            )
            alt_rel_m = float(getattr(message, "relative_alt", 0.0)) / 1000.0
            self.position = (north_m, east_m, alt_rel_m)
            self.trajectory.append(self.position)
            self.boot_ms = int(getattr(message, "time_boot_ms", self.boot_ms))
        elif getattr(message, "get_type", lambda: "")() == "HEARTBEAT":
            custom_mode = getattr(message, "custom_mode", None)
            modes = getattr(self.connection, "mode_mapping", lambda: {})()
            self.mode = next(
                (name for name, number in modes.items() if number == custom_mode),
                self.mode,
            )
            self.armed = bool(getattr(message, "base_mode", 0) & 128)
        current_time = self.clock()
        pending = []
        for handle, expires_at in self._fault_handles:
            if expires_at is not None and current_time >= expires_at:
                handle.clear()
            else:
                pending.append((handle, expires_at))
        self._fault_handles = pending

    def _wait_for_condition(self, condition: str, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self._poll_telemetry(timeout=0.05)
            if self._condition_met(condition):
                return
        raise TimeoutError(f"condition {condition!r} not met within {timeout_s}s")

    def _condition_met(self, condition: str) -> bool:
        lookup = {
            "armed": self.armed,
            "disarmed": not self.armed,
            "gps_ok": self.position[2] >= -1.0,
            "ready": self.mode in {"GUIDED", "AUTO", "MANUAL"},
            "takeoff_complete": self.position[2] >= 9.5,
            "landed": abs(self.position[2]) < 0.5,
            "mode_guided": self.mode == "GUIDED",
        }
        return bool(lookup.get(condition, False))

    def _set_param(self, action: SetParamAction) -> None:
        self.connection.mav.param_set_send(
            self.connection.target_system,
            self.connection.target_component,
            action.param.encode("utf-8"),
            float(action.value),
            0,
        )

    def _simulate_fault(self, action: FaultAction) -> None:
        if action.subsystem != "gps" or action.fault != "lost":
            raise ValueError(f"unsupported scenario fault: {action.subsystem}:{action.fault}")
        from .faults import FaultController

        handle = FaultController(self.connection).gps_loss()
        self.fault_signature_changed = True
        expires_at = self.clock() + action.duration_s if action.duration_s is not None else None
        self._fault_handles.append((handle, expires_at))
        self._log(action, "triggered", f"fault={action.subsystem}:{action.fault}")

    def _set_mode(self, name: str) -> None:
        modes = getattr(self.connection, "mode_mapping", lambda: {})()
        if not modes:
            modes = {"GUIDED": 4, "AUTO": 10, "RTL": 6, "LAND": 9}
        mode_id = modes.get(name)
        if mode_id is None:
            raise RuntimeError(f"vehicle does not advertise {name} mode")
        if hasattr(self.connection, "mav") and hasattr(self.connection.mav, "set_mode_send"):
            self.connection.mav.set_mode_send(
                self.connection.target_system,
                1,
                mode_id,
            )
        else:
            self.connection.set_mode_send(self.connection.target_system, 1, mode_id)
        self.mode = name

    def _command(self, action: CommandAction) -> None:
        name = action.name
        if name == "set_mode_guided":
            self._set_mode("GUIDED")
        elif name == "set_mode_auto":
            self._set_mode("AUTO")
        elif name == "arm":
            if hasattr(self.connection, "mav") and hasattr(self.connection.mav, "command_long_send"):
                self.connection.mav.command_long_send(
                    self.connection.target_system,
                    self.connection.target_component,
                    400, 0, 1.0, 0, 0, 0, 0, 0, 0,
                )
            else:
                self.armed = True
        elif name == "disarm":
            if hasattr(self.connection, "mav"):
                self.connection.mav.command_long_send(
                    self.connection.target_system,
                    self.connection.target_component,
                    400, 0, 0.0, 0, 0, 0, 0, 0, 0,
                )
            else:
                self.armed = False
        elif name == "takeoff":
            alt = float(action.alt_rel_m if action.alt_rel_m is not None else self.position[2])
            if hasattr(self.connection, "mav") and hasattr(self.connection.mav, "command_long_send"):
                self.connection.mav.command_long_send(
                    self.connection.target_system,
                    self.connection.target_component,
                    22, 0, 0, 0, 0, 0, 0, 0, alt,
                )
            else:
                self.position = (self.position[0], self.position[1], alt)
        elif name == "goto":
            north = float(action.north_m if action.north_m is not None else self.position[0])
            east = float(action.east_m if action.east_m is not None else self.position[1])
            alt = float(action.alt_rel_m if action.alt_rel_m is not None else self.position[2])
            if hasattr(self.connection, "mav") and hasattr(self.connection.mav, "set_position_target_local_ned_send"):
                self.connection.mav.set_position_target_local_ned_send(
                    self.boot_ms,
                    self.connection.target_system,
                    self.connection.target_component,
                    1,
                    sum(1 << bit for bit in (3, 4, 5, 6, 7, 8, 10, 11)),
                    north,
                    east,
                    -alt,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                )
            self.position = (north, east, alt)
            self.trajectory.append(self.position)
        elif name == "rtl":
            self._set_mode("RTL")
        elif name == "land":
            self._set_mode("LAND")

    def execute_entry(self, entry: TimelineEntry) -> None:
        action = entry.action
        scheduled_at = entry.t_s
        if scheduled_at > 0:
            self._wait_until(self.start_t + scheduled_at)
        self._log(action, "started")
        if isinstance(action, SetParamAction):
            self._set_param(action)
        elif isinstance(action, FaultAction):
            self._simulate_fault(action)
        elif isinstance(action, CommandAction):
            self._command(action)
        elif isinstance(action, WaitForAction):
            self._wait_for_condition(action.condition, action.timeout_s)
        self._log(action, "completed")

    def run(self) -> list[tuple[float, float, float]]:
        self.start_t = self.clock()
        for key, value in self.scenario.vehicle_params.items():
            self.connection.mav.param_set_send(
                self.connection.target_system,
                self.connection.target_component,
                key.encode("utf-8"),
                float(value),
                0,
            )
        for entry in sorted(self.scenario.timeline, key=lambda item: item.t_s):
            self.execute_entry(entry)
        if self.armed and hasattr(self.connection.mav, "command_long_send"):
            self._set_mode("LAND")
            self._wait_for_condition("disarmed", 60.0)
        for handle, _ in self._fault_handles:
            handle.clear()
        self._fault_handles.clear()
        if not self.trajectory:
            self.trajectory = [self.position]
        return self.trajectory


def main() -> None:
    path = Path(__file__).resolve().parents[1] / "scenarios" / "nominal_square.yaml"
    scenario = load_scenario(path)
    print(json.dumps(scenario.model_dump(mode="json"), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
