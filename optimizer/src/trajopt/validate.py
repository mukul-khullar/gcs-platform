"""Sampled route constraint validation in a local ENU frame."""

import math
from collections.abc import Sequence

from .geo import latlon_to_enu, point_in_polygon_enu, polygon_to_enu
from .models import PlanRequest, PlanWaypoint, Violation

_MAX_SAMPLE_SPACING_M = 1.0


def _path_samples(
    path: Sequence[PlanWaypoint], request: PlanRequest
) -> list[tuple[float, float, float]]:
    origin_lat_deg = request.start.lat_deg
    origin_lon_deg = request.start.lon_deg
    points_enu_m = [
        (
            *latlon_to_enu(
                waypoint.lat_deg,
                waypoint.lon_deg,
                origin_lat_deg,
                origin_lon_deg,
            ),
            waypoint.alt_rel_m,
        )
        for waypoint in path
    ]
    if not points_enu_m:
        return []

    samples = [points_enu_m[0]]
    for start, end in zip(points_enu_m, points_enu_m[1:]):
        delta_east_m = end[0] - start[0]
        delta_north_m = end[1] - start[1]
        delta_alt_m = end[2] - start[2]
        segment_length_m = math.sqrt(
            delta_east_m**2 + delta_north_m**2 + delta_alt_m**2
        )
        sample_count = max(1, math.ceil(segment_length_m / _MAX_SAMPLE_SPACING_M))
        for sample_index in range(1, sample_count + 1):
            fraction = sample_index / sample_count
            samples.append(
                (
                    start[0] + fraction * delta_east_m,
                    start[1] + fraction * delta_north_m,
                    start[2] + fraction * delta_alt_m,
                )
            )
    return samples


def validate(
    path: Sequence[PlanWaypoint], request: PlanRequest
) -> list[Violation]:
    """Validate geodetic waypoints projected to local ENU metres at request.start."""
    violations: list[Violation] = []
    reported: set[tuple[str, str]] = set()

    def report_once(code: str, message: str) -> None:
        key = (code, message)
        if key not in reported:
            reported.add(key)
            violations.append(Violation(code=code, message=message))

    if len(path) > request.constraints.max_waypoints:
        report_once(
            "max_waypoints",
            f"Path has {len(path)} waypoints; maximum is "
            f"{request.constraints.max_waypoints}.",
        )

    origin_lat_deg = request.start.lat_deg
    origin_lon_deg = request.start.lon_deg
    geofence_enu_m = polygon_to_enu(
        request.constraints.geofence, origin_lat_deg, origin_lon_deg
    )
    no_fly_enu_m = [
        (
            polygon_to_enu(volume.polygon, origin_lat_deg, origin_lon_deg),
            volume.floor_m,
            volume.ceil_m,
        )
        for volume in request.constraints.no_fly
    ]

    for east_m, north_m, alt_rel_m in _path_samples(path, request):
        if not point_in_polygon_enu(east_m, north_m, geofence_enu_m):
            report_once("geofence", "Path leaves the geofence.")
        if alt_rel_m < request.constraints.min_alt_m:
            report_once(
                "min_altitude",
                f"Path is below min_alt_m ({request.constraints.min_alt_m} m).",
            )
        if alt_rel_m > request.constraints.max_alt_m:
            report_once(
                "max_altitude",
                f"Path is above max_alt_m ({request.constraints.max_alt_m} m).",
            )

        for volume_index, (polygon_enu_m, floor_m, ceil_m) in enumerate(
            no_fly_enu_m
        ):
            if (
                floor_m <= alt_rel_m <= ceil_m
                and point_in_polygon_enu(east_m, north_m, polygon_enu_m)
            ):
                report_once(
                    "no_fly",
                    f"Path intersects no-fly volume {volume_index}.",
                )

    return violations
