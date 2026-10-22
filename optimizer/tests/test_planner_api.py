import asyncio
import json
import math
import time
from pathlib import Path
from typing import Any

from trajopt.api import app
from trajopt.geo import enu_to_latlon
from trajopt.models import (
    Constraints,
    Environment,
    GeoPoint,
    NoFlyVolume,
    PlanRequest,
    Vehicle,
)
from trajopt.planners.astar import plan

ORIGIN_LAT_DEG = 31.634
ORIGIN_LON_DEG = 74.8723


def geo(east_m: float, north_m: float, alt_rel_m: float = 30.0) -> GeoPoint:
    lat_deg, lon_deg = enu_to_latlon(
        east_m, north_m, ORIGIN_LAT_DEG, ORIGIN_LON_DEG
    )
    return GeoPoint(lat_deg=lat_deg, lon_deg=lon_deg, alt_rel_m=alt_rel_m)


def polygon(points_enu_m: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return [
        enu_to_latlon(east_m, north_m, ORIGIN_LAT_DEG, ORIGIN_LON_DEG)
        for east_m, north_m in points_enu_m
    ]


def request(
    goal_points_enu_m: list[tuple[float, float]],
    *,
    no_fly_polygons_enu_m: list[list[tuple[float, float]]] | None = None,
    max_waypoints: int = 500,
    geofence_half_width_m: float = 200.0,
    geofence_half_length_m: float = 200.0,
) -> PlanRequest:
    return PlanRequest(
        request_id="planner-test",
        vehicle=Vehicle(cruise_mps=8.0, battery_wh=100.0, reserve_pct=20.0),
        start=geo(0.0, 0.0),
        goals=[geo(east_m, north_m) for east_m, north_m in goal_points_enu_m],
        constraints=Constraints(
            geofence=polygon(
                [
                    (-geofence_half_width_m, -geofence_half_length_m),
                    (geofence_half_width_m, -geofence_half_length_m),
                    (geofence_half_width_m, geofence_half_length_m),
                    (-geofence_half_width_m, geofence_half_length_m),
                ]
            ),
            no_fly=[
                NoFlyVolume(
                    polygon=polygon(obstacle),
                    floor_m=20.0,
                    ceil_m=40.0,
                )
                for obstacle in no_fly_polygons_enu_m or []
            ],
            min_alt_m=5.0,
            max_alt_m=100.0,
            max_waypoints=max_waypoints,
        ),
        environment=Environment(wind_from_deg=270.0, wind_mps=3.0),
    )


def run_asgi(
    path: str, method: str, body: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any]]:
    body_bytes = json.dumps(body).encode() if body is not None else b""
    messages: list[dict[str, Any]] = []
    received = False

    async def receive() -> dict[str, Any]:
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": body_bytes, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"localhost")],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8100),
    }
    asyncio.run(app(scope, receive, send))
    start = next(message for message in messages if message["type"] == "http.response.start")
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return start["status"], json.loads(response_body)


def test_astar_routes_around_no_fly_zone_and_shortcuts_path() -> None:
    plan_request = request(
        [(80.0, 0.0)],
        no_fly_polygons_enu_m=[
            [(25.0, -15.0), (45.0, -15.0), (45.0, 15.0), (25.0, 15.0)]
        ],
    )

    response = plan(plan_request)

    assert response.status == "ok"
    assert len(response.waypoints) < 20
    assert response.violations == []
    assert response.metrics.length_m > 80.0
    assert response.metrics.energy_wh > 0.0


def test_goal_inside_no_fly_zone_is_infeasible() -> None:
    plan_request = request(
        [(0.0, 0.0)],
        no_fly_polygons_enu_m=[
            [(-10.0, -10.0), (10.0, -10.0), (10.0, 10.0), (-10.0, 10.0)]
        ],
    )

    response = plan(plan_request)

    assert response.status == "infeasible"
    assert any(violation.code == "no_fly" for violation in response.violations)


def test_fifty_waypoints_and_five_no_fly_zones_solve_under_two_seconds() -> None:
    obstacles = [
        [
            (east_m - 5.0, -8.0),
            (east_m + 5.0, -8.0),
            (east_m + 5.0, 8.0),
            (east_m - 5.0, 8.0),
        ]
        for east_m in (110.0, 310.0, 510.0, 710.0, 910.0)
    ]
    plan_request = request(
        [(float(index * 20 + 20), 0.0) for index in range(50)],
        no_fly_polygons_enu_m=obstacles,
        max_waypoints=500,
        geofence_half_width_m=1100.0,
        geofence_half_length_m=300.0,
    )

    started = time.perf_counter()
    response = plan(plan_request)
    elapsed_s = time.perf_counter() - started

    assert response.status == "ok"
    assert not response.violations
    assert response.metrics.length_m > 1000.0
    assert elapsed_s < 2.0


def test_plan_response_matches_shared_fixture_shape() -> None:
    response = plan(request([(80.0, 0.0)]))
    fixture_path = (
        Path(__file__).parents[2] / "contracts" / "fixtures" / "plan_response.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert response.model_dump(mode="json").keys() == fixture.keys()
    assert response.model_dump(mode="json")["metrics"].keys() == fixture["metrics"].keys()
    assert response.model_dump(mode="json")["waypoints"][0].keys() == fixture["waypoints"][0].keys()


def test_api_health_and_plan_endpoints() -> None:
    health_status, health_body = run_asgi("/health", "GET")
    plan_status, plan_body = run_asgi(
        "/plan",
        "POST",
        request([(80.0, 0.0)]).model_dump(mode="json"),
    )

    assert health_status == 200
    assert health_body == {"status": "ok"}
    assert plan_status == 200
    assert plan_body["request_id"] == "planner-test"
    assert plan_body["status"] == "ok"


def test_astar_distance_is_finite_for_multiple_goals() -> None:
    response = plan(request([(20.0, 0.0), (40.0, 20.0)]))

    assert response.status == "ok"
    assert math.isfinite(response.metrics.length_m)
