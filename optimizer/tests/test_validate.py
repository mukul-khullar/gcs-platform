import pytest

from trajopt.geo import enu_to_latlon
from trajopt.models import (
    Constraints,
    Environment,
    GeoPoint,
    NoFlyVolume,
    PlanRequest,
    PlanWaypoint,
    Vehicle,
)
from trajopt.validate import validate

ORIGIN_LAT_DEG = 37.0
ORIGIN_LON_DEG = -122.0


def point(east_m: float, north_m: float, alt_rel_m: float = 10.0) -> PlanWaypoint:
    lat_deg, lon_deg = enu_to_latlon(
        east_m, north_m, ORIGIN_LAT_DEG, ORIGIN_LON_DEG
    )
    return PlanWaypoint(
        seq=0,
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        alt_rel_m=alt_rel_m,
        speed_mps=5.0,
    )


def polygon_latlon_deg(
    points_enu_m: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    return [
        enu_to_latlon(east_m, north_m, ORIGIN_LAT_DEG, ORIGIN_LON_DEG)
        for east_m, north_m in points_enu_m
    ]


def make_request(
    *,
    geofence_enu_m: list[tuple[float, float]] | None = None,
    no_fly_enu_m: list[tuple[float, float]] | None = None,
    floor_m: float = 5.0,
    ceil_m: float = 15.0,
    min_alt_m: float = 0.0,
    max_alt_m: float = 30.0,
    max_waypoints: int = 10,
) -> PlanRequest:
    geofence = geofence_enu_m or [
        (-10.0, -10.0),
        (10.0, -10.0),
        (10.0, 10.0),
        (-10.0, 10.0),
    ]
    no_fly = []
    if no_fly_enu_m is not None:
        no_fly = [
            NoFlyVolume(
                polygon=polygon_latlon_deg(no_fly_enu_m),
                floor_m=floor_m,
                ceil_m=ceil_m,
            )
        ]

    return PlanRequest(
        request_id="validator-test",
        vehicle=Vehicle(cruise_mps=5.0, battery_wh=100.0, reserve_pct=20.0),
        start=GeoPoint(
            lat_deg=ORIGIN_LAT_DEG,
            lon_deg=ORIGIN_LON_DEG,
            alt_rel_m=10.0,
        ),
        goals=[],
        constraints=Constraints(
            geofence=polygon_latlon_deg(geofence),
            no_fly=no_fly,
            min_alt_m=min_alt_m,
            max_alt_m=max_alt_m,
            max_waypoints=max_waypoints,
        ),
        environment=Environment(wind_from_deg=0.0, wind_mps=0.0),
    )


CONCAVE_GEOFENCE = [
    (-10.0, -10.0),
    (10.0, -10.0),
    (10.0, 10.0),
    (2.0, 10.0),
    (2.0, 0.0),
    (-2.0, 0.0),
    (-2.0, 10.0),
    (-10.0, 10.0),
]
NO_FLY_POLYGON = [
    (-2.0, -2.0),
    (2.0, -2.0),
    (2.0, 2.0),
    (-2.0, 2.0),
]


@pytest.mark.parametrize(
    ("case", "plan_request", "path", "expected_codes"),
    [
        ("inside geofence", make_request(), [point(0, 0)], set()),
        ("outside geofence", make_request(), [point(11, 0)], {"geofence"}),
        ("touching geofence edge", make_request(), [point(10, 0)], set()),
        (
            "inside concave polygon arm",
            make_request(geofence_enu_m=CONCAVE_GEOFENCE),
            [point(5, 5)],
            set(),
        ),
        (
            "outside concave polygon notch",
            make_request(geofence_enu_m=CONCAVE_GEOFENCE),
            [point(0, 5)],
            {"geofence"},
        ),
        (
            "segment crossing concave notch",
            make_request(geofence_enu_m=CONCAVE_GEOFENCE),
            [point(-5, 5), point(5, 5)],
            {"geofence"},
        ),
        (
            "inside no-fly volume",
            make_request(no_fly_enu_m=NO_FLY_POLYGON),
            [point(0, 0, 10)],
            {"no_fly"},
        ),
        (
            "below no-fly floor",
            make_request(no_fly_enu_m=NO_FLY_POLYGON),
            [point(0, 0, 4.9)],
            set(),
        ),
        (
            "at no-fly floor",
            make_request(no_fly_enu_m=NO_FLY_POLYGON),
            [point(0, 0, 5)],
            {"no_fly"},
        ),
        (
            "at no-fly ceiling",
            make_request(no_fly_enu_m=NO_FLY_POLYGON),
            [point(0, 0, 15)],
            {"no_fly"},
        ),
        (
            "above no-fly ceiling",
            make_request(no_fly_enu_m=NO_FLY_POLYGON),
            [point(0, 0, 15.1)],
            set(),
        ),
        (
            "crossing no-fly volume between endpoints",
            make_request(no_fly_enu_m=NO_FLY_POLYGON),
            [point(-5, 0), point(5, 0)],
            {"no_fly"},
        ),
        (
            "touching no-fly polygon boundary",
            make_request(no_fly_enu_m=NO_FLY_POLYGON),
            [point(2, 0)],
            {"no_fly"},
        ),
        (
            "below minimum altitude",
            make_request(min_alt_m=5),
            [point(0, 0, 4.9)],
            {"min_altitude"},
        ),
        (
            "at minimum altitude",
            make_request(min_alt_m=5),
            [point(0, 0, 5)],
            set(),
        ),
        (
            "above maximum altitude",
            make_request(max_alt_m=15),
            [point(0, 0, 15.1)],
            {"max_altitude"},
        ),
        (
            "at maximum altitude",
            make_request(max_alt_m=15),
            [point(0, 0, 15)],
            set(),
        ),
        (
            "too many waypoints",
            make_request(max_waypoints=1),
            [point(0, 0), point(1, 1)],
            {"max_waypoints"},
        ),
        (
            "zero-length leg",
            make_request(),
            [point(0, 0), point(0, 0)],
            set(),
        ),
        (
            "zero-length leg in no-fly volume",
            make_request(no_fly_enu_m=NO_FLY_POLYGON),
            [point(0, 0), point(0, 0)],
            {"no_fly"},
        ),
        (
            "segment rises through no-fly volume",
            make_request(no_fly_enu_m=NO_FLY_POLYGON),
            [point(0, 0, 4), point(0, 0, 16)],
            {"no_fly"},
        ),
        (
            "empty path",
            make_request(),
            [],
            set(),
        ),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_validate_path_constraints(
    case: str,
    plan_request: PlanRequest,
    path: list[PlanWaypoint],
    expected_codes: set[str],
) -> None:
    violations = validate(path, plan_request)

    assert {violation.code for violation in violations} == expected_codes, case
