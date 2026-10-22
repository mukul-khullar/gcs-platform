"""Geodetic and local ENU conversions; coordinates use degrees and metres."""

import math
from functools import lru_cache

from pyproj import CRS, Transformer

EARTH_MEAN_RADIUS_M = 6_371_008.8


@lru_cache(maxsize=32)
def _transformers(
    origin_lat_deg: float, origin_lon_deg: float
) -> tuple[Transformer, Transformer]:
    if not -90.0 <= origin_lat_deg <= 90.0:
        raise ValueError("origin_lat_deg must be between -90 and 90 degrees")
    if not -180.0 <= origin_lon_deg <= 180.0:
        raise ValueError("origin_lon_deg must be between -180 and 180 degrees")

    geodetic_crs = CRS.from_epsg(4326)
    enu_crs = CRS.from_proj4(
        f"+proj=aeqd +lat_0={origin_lat_deg} +lon_0={origin_lon_deg} "
        "+datum=WGS84 +units=m +no_defs +type=crs"
    )
    to_enu = Transformer.from_crs(geodetic_crs, enu_crs, always_xy=True)
    to_geodetic = Transformer.from_crs(enu_crs, geodetic_crs, always_xy=True)
    return to_enu, to_geodetic


def latlon_to_enu(
    lat_deg: float,
    lon_deg: float,
    origin_lat_deg: float,
    origin_lon_deg: float,
) -> tuple[float, float]:
    """Convert geodetic degrees to local east/north metres about the given origin."""
    if not -90.0 <= lat_deg <= 90.0:
        raise ValueError("lat_deg must be between -90 and 90 degrees")
    if not -180.0 <= lon_deg <= 180.0:
        raise ValueError("lon_deg must be between -180 and 180 degrees")
    to_enu, _ = _transformers(origin_lat_deg, origin_lon_deg)
    east_m, north_m = to_enu.transform(lon_deg, lat_deg, errcheck=True)
    return east_m, north_m


def enu_to_latlon(
    east_m: float,
    north_m: float,
    origin_lat_deg: float,
    origin_lon_deg: float,
) -> tuple[float, float]:
    """Convert local east/north metres to geodetic latitude/longitude degrees."""
    _, to_geodetic = _transformers(origin_lat_deg, origin_lon_deg)
    lon_deg, lat_deg = to_geodetic.transform(east_m, north_m, errcheck=True)
    return lat_deg, lon_deg


def haversine_m(
    lat1_deg: float, lon1_deg: float, lat2_deg: float, lon2_deg: float
) -> float:
    """Return great-circle distance in metres between geodetic degree coordinates."""
    lat1_rad = math.radians(lat1_deg)
    lat2_rad = math.radians(lat2_deg)
    delta_lat_rad = lat2_rad - lat1_rad
    delta_lon_rad = math.radians(lon2_deg - lon1_deg)
    haversine = (
        math.sin(delta_lat_rad / 2.0) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lon_rad / 2.0) ** 2
    )
    central_angle_rad = 2.0 * math.asin(math.sqrt(min(1.0, haversine)))
    return EARTH_MEAN_RADIUS_M * central_angle_rad


def polygon_to_enu(
    polygon_latlon_deg: list[tuple[float, float]],
    origin_lat_deg: float,
    origin_lon_deg: float,
) -> list[tuple[float, float]]:
    """Project a polygon of (latitude, longitude) degrees to local ENU metres."""
    return [
        latlon_to_enu(lat_deg, lon_deg, origin_lat_deg, origin_lon_deg)
        for lat_deg, lon_deg in polygon_latlon_deg
    ]


def _point_on_segment_enu(
    east_m: float,
    north_m: float,
    start: tuple[float, float],
    end: tuple[float, float],
) -> bool:
    delta_east_m = end[0] - start[0]
    delta_north_m = end[1] - start[1]
    segment_length_sq_m2 = delta_east_m**2 + delta_north_m**2
    if segment_length_sq_m2 == 0.0:
        return math.hypot(east_m - start[0], north_m - start[1]) <= 1e-7

    projection = (
        (east_m - start[0]) * delta_east_m
        + (north_m - start[1]) * delta_north_m
    ) / segment_length_sq_m2
    if not 0.0 <= projection <= 1.0:
        return False

    closest_east_m = start[0] + projection * delta_east_m
    closest_north_m = start[1] + projection * delta_north_m
    return math.hypot(east_m - closest_east_m, north_m - closest_north_m) <= 1e-7


def point_in_polygon_enu(
    east_m: float,
    north_m: float,
    polygon_enu_m: list[tuple[float, float]],
) -> bool:
    """Return whether an ENU point lies in or on an ENU polygon boundary."""
    inside = False
    for index, start in enumerate(polygon_enu_m):
        end = polygon_enu_m[(index + 1) % len(polygon_enu_m)]
        if _point_on_segment_enu(east_m, north_m, start, end):
            return True
        if (start[1] > north_m) != (end[1] > north_m):
            crossing_east_m = start[0] + (
                (north_m - start[1]) * (end[0] - start[0]) / (end[1] - start[1])
            )
            if east_m < crossing_east_m:
                inside = not inside
    return inside
