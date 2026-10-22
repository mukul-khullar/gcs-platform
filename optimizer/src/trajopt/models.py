"""Pydantic models for the optimizer's SI-unit REST contract."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LatLonDeg = tuple[float, float]


class ContractModel(BaseModel):
    """Base for contract payloads; reject fields not defined by the wire schema."""

    model_config = ConfigDict(extra="forbid")


class GeoPoint(ContractModel):
    """Geodetic point in degrees with altitude relative to the launch point in metres."""

    lat_deg: float = Field(ge=-90.0, le=90.0)
    lon_deg: float = Field(ge=-180.0, le=180.0)
    alt_rel_m: float


class Vehicle(ContractModel):
    """Vehicle performance inputs; cruise speed is in m/s and battery energy in Wh."""

    cruise_mps: float
    battery_wh: float
    reserve_pct: float


class NoFlyVolume(ContractModel):
    """Closed geodetic polygon with floor and ceiling altitudes in relative metres."""

    polygon: list[LatLonDeg] = Field(min_length=3)
    floor_m: float
    ceil_m: float


class Constraints(ContractModel):
    """Route limits, with altitude and waypoint limits in metres and count respectively."""

    geofence: list[LatLonDeg] = Field(min_length=3)
    no_fly: list[NoFlyVolume]
    min_alt_m: float
    max_alt_m: float
    max_waypoints: int


class Environment(ContractModel):
    """Wind direction in degrees-from and wind speed in m/s."""

    wind_from_deg: float
    wind_mps: float


class PlanRequest(ContractModel):
    """Optimizer request; coordinates are geodetic and altitudes are relative metres."""

    request_id: str
    vehicle: Vehicle
    start: GeoPoint
    goals: list[GeoPoint]
    constraints: Constraints
    environment: Environment


class PlanWaypoint(ContractModel):
    """Planned waypoint in geodetic degrees, relative altitude metres, and speed m/s."""

    seq: int
    lat_deg: float = Field(ge=-90.0, le=90.0)
    lon_deg: float = Field(ge=-180.0, le=180.0)
    alt_rel_m: float
    speed_mps: float


class Violation(ContractModel):
    """A route-constraint violation identified by a stable code and human message."""

    code: str
    message: str


class PlanMetrics(ContractModel):
    """Plan metrics in metres, seconds, and watt-hours."""

    length_m: float
    eta_s: float
    energy_wh: float
    min_clearance_m: float


class PlanResponse(ContractModel):
    """Optimizer response with status, geodetic waypoints, metrics, and diagnostics."""

    request_id: str
    status: Literal["ok", "infeasible", "error"]
    waypoints: list[PlanWaypoint]
    metrics: PlanMetrics
    violations: list[Violation]
    explain: list[str]
    solve_ms: float
