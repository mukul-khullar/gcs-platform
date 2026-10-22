import pytest
from pydantic import ValidationError

from trajopt.models import PlanRequest, PlanResponse


def test_plan_request_matches_contract_shape() -> None:
    payload = {
        "request_id": "request-1",
        "vehicle": {"cruise_mps": 5.0, "battery_wh": 100.0, "reserve_pct": 20.0},
        "start": {"lat_deg": 37.0, "lon_deg": -122.0, "alt_rel_m": 10.0},
        "goals": [{"lat_deg": 37.1, "lon_deg": -122.1, "alt_rel_m": 20.0}],
        "constraints": {
            "geofence": [[37.0, -122.0], [37.0, -121.9], [37.1, -122.0]],
            "no_fly": [
                {
                    "polygon": [[37.02, -122.02], [37.02, -122.01], [37.03, -122.02]],
                    "floor_m": 5.0,
                    "ceil_m": 15.0,
                }
            ],
            "min_alt_m": 2.0,
            "max_alt_m": 100.0,
            "max_waypoints": 50,
        },
        "environment": {"wind_from_deg": 180.0, "wind_mps": 3.0},
    }

    request = PlanRequest.model_validate(payload)

    assert request.model_dump(mode="json") == payload


def test_plan_response_matches_contract_shape() -> None:
    payload = {
        "request_id": "request-1",
        "status": "ok",
        "waypoints": [
            {
                "seq": 0,
                "lat_deg": 37.0,
                "lon_deg": -122.0,
                "alt_rel_m": 10.0,
                "speed_mps": 5.0,
            }
        ],
        "metrics": {
            "length_m": 100.0,
            "eta_s": 20.0,
            "energy_wh": 2.0,
            "min_clearance_m": 5.0,
        },
        "violations": [{"code": "geofence", "message": "Path leaves the geofence."}],
        "explain": ["Direct path selected."],
        "solve_ms": 3.0,
    }

    response = PlanResponse.model_validate(payload)

    assert response.model_dump(mode="json") == payload


def test_contract_models_reject_undeclared_fields() -> None:
    with pytest.raises(ValidationError):
        PlanRequest.model_validate(
            {
                "request_id": "request-1",
                "vehicle": {"cruise_mps": 5.0, "battery_wh": 100.0, "reserve_pct": 20.0},
                "start": {"lat_deg": 37.0, "lon_deg": -122.0, "alt_rel_m": 10.0},
                "goals": [],
                "constraints": {
                    "geofence": [[37.0, -122.0], [37.0, -121.9], [37.1, -122.0]],
                    "no_fly": [],
                    "min_alt_m": 2.0,
                    "max_alt_m": 100.0,
                    "max_waypoints": 50,
                },
                "environment": {"wind_from_deg": 180.0, "wind_mps": 3.0},
                "unexpected": "not in contract",
            }
        )
