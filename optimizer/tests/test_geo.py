import math

from trajopt.geo import haversine_m, latlon_to_enu, polygon_to_enu, enu_to_latlon


def test_enu_round_trip_within_one_centimeter_over_five_kilometers() -> None:
    origin_lat_deg = 37.422
    origin_lon_deg = -122.084
    east_m, north_m = 3_500.0, 3_500.0

    lat_deg, lon_deg = enu_to_latlon(
        east_m, north_m, origin_lat_deg, origin_lon_deg
    )
    actual_east_m, actual_north_m = latlon_to_enu(
        lat_deg, lon_deg, origin_lat_deg, origin_lon_deg
    )

    assert math.hypot(actual_east_m - east_m, actual_north_m - north_m) < 0.01
    assert math.hypot(east_m, north_m) < 5_000.0


def test_haversine_returns_distance_in_meters() -> None:
    assert math.isclose(
        haversine_m(0.0, 0.0, 0.0, 1.0), 111_194.9, abs_tol=1.0
    )


def test_polygon_conversion_uses_local_enu_frame() -> None:
    origin_lat_deg = 37.422
    origin_lon_deg = -122.084
    polygon_latlon_deg = [
        (origin_lat_deg, origin_lon_deg),
        enu_to_latlon(10.0, 0.0, origin_lat_deg, origin_lon_deg),
        enu_to_latlon(0.0, 10.0, origin_lat_deg, origin_lon_deg),
    ]

    polygon_enu_m = polygon_to_enu(
        polygon_latlon_deg, origin_lat_deg, origin_lon_deg
    )

    assert len(polygon_enu_m) == 3
    assert math.hypot(*polygon_enu_m[0]) < 0.001
    assert math.isclose(polygon_enu_m[1][0], 10.0, abs_tol=0.01)
    assert math.isclose(polygon_enu_m[2][1], 10.0, abs_tol=0.01)
