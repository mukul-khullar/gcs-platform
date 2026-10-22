"""Wind-aware A* planning on a 5 m ENU grid with 8-connected movement."""

from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass
from typing import TypeAlias

from ..geo import enu_to_latlon, latlon_to_enu, point_in_polygon_enu, polygon_to_enu
from ..models import (
    PlanMetrics,
    PlanRequest,
    PlanResponse,
    PlanWaypoint,
    Violation,
)
from ..validate import validate

_CELL_SIZE_M = 5.0
_MAX_SAMPLE_SPACING_M = 1.0
_NEIGHBORS = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)
GridCell: TypeAlias = tuple[int, int]
PointENU: TypeAlias = tuple[float, float, float]


@dataclass(frozen=True)
class _WorldModel:
    geofence_enu_m: list[tuple[float, float]]
    no_fly_enu_m: list[tuple[list[tuple[float, float]], float, float]]
    min_east_m: float
    max_east_m: float
    min_north_m: float
    max_north_m: float
    min_alt_m: float
    max_alt_m: float


def _world_model(request: PlanRequest) -> _WorldModel:
    geofence_enu_m = polygon_to_enu(
        request.constraints.geofence,
        request.start.lat_deg,
        request.start.lon_deg,
    )
    return _WorldModel(
        geofence_enu_m=geofence_enu_m,
        no_fly_enu_m=[
            (
                polygon_to_enu(
                    volume.polygon,
                    request.start.lat_deg,
                    request.start.lon_deg,
                ),
                volume.floor_m,
                volume.ceil_m,
            )
            for volume in request.constraints.no_fly
        ],
        min_east_m=min(point[0] for point in geofence_enu_m),
        max_east_m=max(point[0] for point in geofence_enu_m),
        min_north_m=min(point[1] for point in geofence_enu_m),
        max_north_m=max(point[1] for point in geofence_enu_m),
        min_alt_m=request.constraints.min_alt_m,
        max_alt_m=request.constraints.max_alt_m,
    )


def _altitude_at(
    east_m: float,
    north_m: float,
    start: PointENU,
    end: PointENU,
) -> float:
    delta_east_m = end[0] - start[0]
    delta_north_m = end[1] - start[1]
    horizontal_length_sq_m2 = delta_east_m**2 + delta_north_m**2
    if horizontal_length_sq_m2 == 0.0:
        return end[2]
    fraction = (
        (east_m - start[0]) * delta_east_m
        + (north_m - start[1]) * delta_north_m
    ) / horizontal_length_sq_m2
    fraction = min(1.0, max(0.0, fraction))
    return start[2] + fraction * (end[2] - start[2])


def _point_is_clear(point: PointENU, world: _WorldModel) -> bool:
    east_m, north_m, alt_rel_m = point
    if not point_in_polygon_enu(east_m, north_m, world.geofence_enu_m):
        return False
    if not world.min_alt_m <= alt_rel_m <= world.max_alt_m:
        return False
    return not any(
        floor_m <= alt_rel_m <= ceil_m
        and point_in_polygon_enu(east_m, north_m, polygon_enu_m)
        for polygon_enu_m, floor_m, ceil_m in world.no_fly_enu_m
    )


def _segment_is_clear(start: PointENU, end: PointENU, world: _WorldModel) -> bool:
    delta_east_m = end[0] - start[0]
    delta_north_m = end[1] - start[1]
    delta_alt_m = end[2] - start[2]
    length_m = math.sqrt(
        delta_east_m**2 + delta_north_m**2 + delta_alt_m**2
    )
    sample_count = max(1, math.ceil(length_m / _MAX_SAMPLE_SPACING_M))
    for sample_index in range(sample_count + 1):
        fraction = sample_index / sample_count
        sample = (
            start[0] + fraction * delta_east_m,
            start[1] + fraction * delta_north_m,
            start[2] + fraction * delta_alt_m,
        )
        if not _point_is_clear(sample, world):
            return False
    return True


def _wind_adjusted_cost_m(
    start: PointENU, end: PointENU, request: PlanRequest
) -> float:
    delta_east_m = end[0] - start[0]
    delta_north_m = end[1] - start[1]
    horizontal_distance_m = math.hypot(delta_east_m, delta_north_m)
    distance_m = math.sqrt(
        horizontal_distance_m**2 + (end[2] - start[2]) ** 2
    )
    if horizontal_distance_m == 0.0 or request.vehicle.cruise_mps <= 0.0:
        return distance_m

    wind_from_rad = math.radians(request.environment.wind_from_deg)
    wind_east_mps = -math.sin(wind_from_rad) * request.environment.wind_mps
    wind_north_mps = -math.cos(wind_from_rad) * request.environment.wind_mps
    unit_east = delta_east_m / horizontal_distance_m
    unit_north = delta_north_m / horizontal_distance_m
    headwind_mps = max(
        0.0, -(wind_east_mps * unit_east + wind_north_mps * unit_north)
    )
    energy_term_m = (
        horizontal_distance_m * (headwind_mps / request.vehicle.cruise_mps) ** 2
    )
    return distance_m + energy_term_m


def _grid_point(cell: GridCell, alt_rel_m: float) -> PointENU:
    return (cell[0] * _CELL_SIZE_M, cell[1] * _CELL_SIZE_M, alt_rel_m)


def _cell_for_point(point: PointENU) -> GridCell:
    return (
        round(point[0] / _CELL_SIZE_M),
        round(point[1] / _CELL_SIZE_M),
    )


def _a_star(
    start: PointENU,
    goal: PointENU,
    request: PlanRequest,
    world: _WorldModel,
) -> list[PointENU] | None:
    source = _cell_for_point(start)
    target = _cell_for_point(goal)

    def altitude_for(cell: GridCell) -> float:
        point = _grid_point(cell, start[2])
        return _altitude_at(point[0], point[1], start, goal)

    source_point = (*_grid_point(source, start[2])[:2], altitude_for(source))
    target_point = (*_grid_point(target, start[2])[:2], altitude_for(target))
    if not _segment_is_clear(start, source_point, world):
        return None
    if not _segment_is_clear(target_point, goal, world):
        return None
    if not _point_is_clear(source_point, world) or not _point_is_clear(
        target_point, world
    ):
        return None

    min_cell_x = math.floor(world.min_east_m / _CELL_SIZE_M)
    max_cell_x = math.ceil(world.max_east_m / _CELL_SIZE_M)
    min_cell_y = math.floor(world.min_north_m / _CELL_SIZE_M)
    max_cell_y = math.ceil(world.max_north_m / _CELL_SIZE_M)

    frontier: list[tuple[float, float, GridCell]] = [(0.0, 0.0, source)]
    came_from: dict[GridCell, GridCell] = {}
    cost_so_far: dict[GridCell, float] = {source: 0.0}

    while frontier:
        _, current_cost, current = heapq.heappop(frontier)
        if current_cost > cost_so_far.get(current, math.inf):
            continue
        if current == target:
            cells = [target]
            while cells[-1] != source:
                cells.append(came_from[cells[-1]])
            cells.reverse()
            points = [start]
            points.extend(
                (*_grid_point(cell, start[2])[:2], altitude_for(cell))
                for cell in cells
            )
            points.append(goal)
            return points

        current_point = (
            *_grid_point(current, start[2])[:2],
            altitude_for(current),
        )
        for offset_x, offset_y in _NEIGHBORS:
            neighbor = (current[0] + offset_x, current[1] + offset_y)
            if not (
                min_cell_x <= neighbor[0] <= max_cell_x
                and min_cell_y <= neighbor[1] <= max_cell_y
            ):
                continue
            neighbor_point = (
                *_grid_point(neighbor, start[2])[:2],
                altitude_for(neighbor),
            )
            if not _segment_is_clear(current_point, neighbor_point, world):
                continue
            new_cost = current_cost + _wind_adjusted_cost_m(
                current_point, neighbor_point, request
            )
            if new_cost >= cost_so_far.get(neighbor, math.inf):
                continue
            cost_so_far[neighbor] = new_cost
            came_from[neighbor] = current
            heuristic_m = math.hypot(
                (target[0] - neighbor[0]) * _CELL_SIZE_M,
                (target[1] - neighbor[1]) * _CELL_SIZE_M,
            )
            heapq.heappush(
                frontier, (new_cost + heuristic_m, new_cost, neighbor)
            )
    return None


def _shortcut_path(
    path: list[PointENU], world: _WorldModel
) -> list[PointENU]:
    if len(path) < 3:
        return path
    shortened = [path[0]]
    current_index = 0
    while current_index < len(path) - 1:
        next_index = len(path) - 1
        while next_index > current_index + 1 and not _segment_is_clear(
            path[current_index], path[next_index], world
        ):
            next_index -= 1
        shortened.append(path[next_index])
        current_index = next_index
    return shortened


def _point_segment_distance_m(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    delta_east_m = end[0] - start[0]
    delta_north_m = end[1] - start[1]
    length_sq_m2 = delta_east_m**2 + delta_north_m**2
    if length_sq_m2 == 0.0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    fraction = min(
        1.0,
        max(
            0.0,
            (
                (point[0] - start[0]) * delta_east_m
                + (point[1] - start[1]) * delta_north_m
            )
            / length_sq_m2,
        ),
    )
    closest = (
        start[0] + fraction * delta_east_m,
        start[1] + fraction * delta_north_m,
    )
    return math.hypot(point[0] - closest[0], point[1] - closest[1])


def _polygon_edge_distance_m(
    point: tuple[float, float],
    polygon_enu_m: list[tuple[float, float]],
) -> float:
    return min(
        _point_segment_distance_m(
            point, polygon_enu_m[index], polygon_enu_m[(index + 1) % len(polygon_enu_m)]
        )
        for index in range(len(polygon_enu_m))
    )


def _minimum_clearance_m(path: list[PointENU], world: _WorldModel) -> float:
    clearances: list[float] = []
    segments = list(zip(path, path[1:]))
    if not segments and path:
        segments = [(path[0], path[0])]
    for start, end in segments:
        length_m = math.sqrt(
            (end[0] - start[0]) ** 2
            + (end[1] - start[1]) ** 2
            + (end[2] - start[2]) ** 2
        )
        sample_count = max(1, math.ceil(length_m / _MAX_SAMPLE_SPACING_M))
        for sample_index in range(sample_count + 1):
            fraction = sample_index / sample_count
            east_m = start[0] + fraction * (end[0] - start[0])
            north_m = start[1] + fraction * (end[1] - start[1])
            alt_rel_m = start[2] + fraction * (end[2] - start[2])
            clearances.append(
                _polygon_edge_distance_m((east_m, north_m), world.geofence_enu_m)
            )
            for polygon_enu_m, floor_m, ceil_m in world.no_fly_enu_m:
                horizontal_m = _polygon_edge_distance_m(
                    (east_m, north_m), polygon_enu_m
                )
                if point_in_polygon_enu(east_m, north_m, polygon_enu_m):
                    horizontal_m = 0.0
                vertical_m = (
                    floor_m - alt_rel_m
                    if alt_rel_m < floor_m
                    else alt_rel_m - ceil_m
                    if alt_rel_m > ceil_m
                    else 0.0
                )
                clearances.append(math.hypot(horizontal_m, vertical_m))
    if not clearances:
        return 0.0
    return min(clearances)


def _response(
    request: PlanRequest,
    path: list[PointENU],
    violations: list[Violation],
    world: _WorldModel,
    solve_ms: float,
    explain: list[str],
) -> PlanResponse:
    waypoints: list[PlanWaypoint] = []
    origin_lat_deg = request.start.lat_deg
    origin_lon_deg = request.start.lon_deg
    for seq, (east_m, north_m, alt_rel_m) in enumerate(path):
        lat_deg, lon_deg = enu_to_latlon(
            east_m, north_m, origin_lat_deg, origin_lon_deg
        )
        waypoints.append(
            PlanWaypoint(
                seq=seq,
                lat_deg=lat_deg,
                lon_deg=lon_deg,
                alt_rel_m=alt_rel_m,
                speed_mps=request.vehicle.cruise_mps,
            )
        )

    length_m = 0.0
    eta_s = 0.0
    energy_wh = 0.0
    for start, end in zip(path, path[1:]):
        segment_length_m = math.sqrt(
            (end[0] - start[0]) ** 2
            + (end[1] - start[1]) ** 2
            + (end[2] - start[2]) ** 2
        )
        length_m += segment_length_m
        horizontal_m = math.hypot(end[0] - start[0], end[1] - start[1])
        if horizontal_m > 0.0 and request.vehicle.cruise_mps > 0.0:
            wind_from_rad = math.radians(request.environment.wind_from_deg)
            wind_east_mps = -math.sin(wind_from_rad) * request.environment.wind_mps
            wind_north_mps = -math.cos(wind_from_rad) * request.environment.wind_mps
            tailwind_mps = (
                wind_east_mps * (end[0] - start[0]) / horizontal_m
                + wind_north_mps * (end[1] - start[1]) / horizontal_m
            )
            groundspeed_mps = max(
                0.1, request.vehicle.cruise_mps + tailwind_mps
            )
            eta_s += segment_length_m / groundspeed_mps
        elif request.vehicle.cruise_mps > 0.0:
            eta_s += segment_length_m / request.vehicle.cruise_mps
        energy_wh += _wind_adjusted_cost_m(start, end, request) / 1000.0

    status = "infeasible" if violations else "ok"
    return PlanResponse(
        request_id=request.request_id,
        status=status,
        waypoints=waypoints,
        metrics=PlanMetrics(
            length_m=length_m,
            eta_s=eta_s,
            energy_wh=energy_wh,
            min_clearance_m=_minimum_clearance_m(path, world),
        ),
        violations=violations,
        explain=explain,
        solve_ms=solve_ms,
    )


def plan(request: PlanRequest) -> PlanResponse:
    """Plan through local ENU metres using 5 m cells and 8-connected A*."""
    started = time.perf_counter()
    world = _world_model(request)
    current: PointENU = (0.0, 0.0, request.start.alt_rel_m)
    path: list[PointENU] = [current]
    explain: list[str] = []

    for goal in request.goals:
        goal_east_m, goal_north_m = latlon_to_enu(
            goal.lat_deg,
            goal.lon_deg,
            request.start.lat_deg,
            request.start.lon_deg,
        )
        target: PointENU = (goal_east_m, goal_north_m, goal.alt_rel_m)
        if not _point_is_clear(target, world):
            path.append(target)
            violations = validate(
                _to_waypoints(path, request), request
            )
            if not violations:
                violations = [
                    Violation(
                        code="unreachable",
                        message="Goal is outside the traversable world model.",
                    )
                ]
            return _response(
                request,
                path,
                violations,
                world,
                (time.perf_counter() - started) * 1000.0,
                ["A goal is not traversable at its requested altitude."],
            )

        leg_path = _a_star(current, target, request, world)
        if leg_path is None:
            violations = validate(_to_waypoints(path, request), request)
            violations.append(
                Violation(
                    code="unreachable",
                    message="No collision-free 5 m grid route reaches the goal.",
                )
            )
            return _response(
                request,
                path,
                violations,
                world,
                (time.perf_counter() - started) * 1000.0,
                ["A goal is unreachable within the geofence and altitude limits."],
            )

        leg_path = _shortcut_path(leg_path, world)
        path.extend(leg_path[1:])
        current = target

    final_waypoints = _to_waypoints(path, request)
    violations = validate(final_waypoints, request)
    if violations:
        explain.append("Final route failed validation.")
    elif request.constraints.no_fly:
        explain.append("A* route validated against the geofence and no-fly volumes.")
    else:
        explain.append("A* route validated against the geofence.")
    explain.append(
        "Energy is a 1 Wh/km distance proxy scaled by headwind; vehicle power data "
        "is not part of the request contract."
    )
    if not request.goals:
        explain.append("No goals were requested; returning the start position.")

    return _response(
        request,
        path,
        violations,
        world,
        (time.perf_counter() - started) * 1000.0,
        explain,
    )


def _to_waypoints(
    path: list[PointENU], request: PlanRequest
) -> list[PlanWaypoint]:
    waypoints = []
    for seq, (east_m, north_m, alt_rel_m) in enumerate(path):
        lat_deg, lon_deg = enu_to_latlon(
            east_m, north_m, request.start.lat_deg, request.start.lon_deg
        )
        waypoints.append(
            PlanWaypoint(
                seq=seq,
                lat_deg=lat_deg,
                lon_deg=lon_deg,
                alt_rel_m=alt_rel_m,
                speed_mps=request.vehicle.cruise_mps,
            )
        )
    return waypoints
