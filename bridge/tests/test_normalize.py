import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pymavlink import mavutil

from bridge.normalize import (
    Normalizer,
    cdeg_to_deg,
    centi_to_unitless,
    centiamps_to_amps,
    cmps_to_mps,
    deg_e7_to_deg,
    millivolts_to_volts,
    mm_to_m,
    normalize_message,
    nullable_int,
)
from bridge.normalize.rate_limiter import TopicRateLimiter
from tests.support.synthetic_tlog import make_synthetic_tlog

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    ("convert", "raw", "expected"),
    [
        (deg_e7_to_deg, 374219999, 37.4219999),
        (mm_to_m, 12345, 12.345),
        (cmps_to_mps, -250, -2.5),
        (cdeg_to_deg, 12345, 123.45),
        (millivolts_to_volts, 16500, 16.5),
        (centiamps_to_amps, -420, -4.2),
        (centi_to_unitless, 123, 1.23),
    ],
)
def test_conversions_have_expected_si_values(
    convert: Any, raw: int, expected: float
) -> None:
    assert convert(raw) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("convert", "raw"),
    [
        (lambda value: deg_e7_to_deg(value, sentinel=0), 0),
        (lambda value: mm_to_m(value, sentinel=-1), -1),
        (lambda value: cmps_to_mps(value, sentinel=32767), 32767),
        (cdeg_to_deg, 65535),
        (millivolts_to_volts, 65535),
        (centiamps_to_amps, -1),
        (centi_to_unitless, 65535),
        (lambda value: nullable_int(value, sentinels=(-1, 255)), 255),
    ],
)
def test_unknown_sentinels_are_null(convert: Any, raw: int) -> None:
    assert convert(raw) is None


def test_rate_limiter_enforces_topic_rate_but_allows_event_topics() -> None:
    limiter = TopicRateLimiter({"telemetry.attitude": 20.0, "anomaly.event": None})

    assert limiter.allow("telemetry.attitude", now_s=10.0)
    assert not limiter.allow("telemetry.attitude", now_s=10.01)
    assert limiter.allow("telemetry.attitude", now_s=10.048)
    assert not limiter.allow("telemetry.attitude", now_s=10.09)
    assert limiter.allow("telemetry.attitude", now_s=10.096)
    assert limiter.allow("anomaly.event", now_s=10.0)
    assert limiter.allow("anomaly.event", now_s=10.001)


def test_rate_limiter_loads_contract_rates_from_yaml() -> None:
    limiter = TopicRateLimiter.from_yaml()

    assert limiter.allow("telemetry.attitude", now_s=10.0)
    assert not limiter.allow("telemetry.attitude", now_s=10.01)
    assert limiter.allow("telemetry.attitude", now_s=10.05)


def test_replayed_tlog_frames_validate_against_json_schema(tmp_path: Path) -> None:
    path = tmp_path / "frames.tlog"
    make_synthetic_tlog(path, duration_s=1, seed=22)
    schema = json.loads((ROOT / "schemas" / "telemetry_frame.json").read_text())
    validator = Draft202012Validator(schema)
    limiter = TopicRateLimiter(
        {
            "telemetry.attitude": None,
            "telemetry.position": None,
            "vehicle.status": None,
        }
    )
    normalizer = Normalizer(limiter)
    connection = mavutil.mavlink_connection(str(path))
    frames = []
    while (message := connection.recv_match(blocking=False)) is not None:
        frame = normalizer.normalize(message, t_wall_ms=1_700_000_000_000)
        if frame is not None:
            frame_dict = frame.model_dump(mode="json")
            validator.validate(frame_dict)
            frames.append(frame_dict)

    assert {frame["type"] for frame in frames} == {
        "telemetry.attitude",
        "telemetry.position",
        "vehicle.status",
    }
    assert len(frames) >= 30
    malformed = dict(frames[0])
    malformed["data"] = {}
    assert not validator.is_valid(malformed)
    attitude_frames = [
        frame for frame in frames if frame["type"] == "telemetry.attitude"
    ]
    assert [frame["seq"] for frame in attitude_frames] == list(range(20))


def test_standalone_normalize_starts_sequence_at_zero(tmp_path: Path) -> None:
    path = tmp_path / "single.tlog"
    make_synthetic_tlog(path, duration_s=0.1, seed=1)
    connection = mavutil.mavlink_connection(str(path))
    frame = normalize_message(connection.recv_match(blocking=False), t_wall_ms=1000)
    assert frame is not None
    assert frame.seq == 0
