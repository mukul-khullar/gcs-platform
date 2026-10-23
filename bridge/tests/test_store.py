from pathlib import Path

import pytest
from pymavlink import mavutil

from bridge.models import FrameModel
from bridge.store import TelemetryStore, TimeRingBuffer
from tests.support.synthetic_tlog import make_synthetic_tlog


def test_ring_buffer_returns_chronological_values_in_window() -> None:
    buffer = TimeRingBuffer(1, rate_hz=2, duration_s=3)
    for timestamp_s in range(5):
        buffer.append(float(timestamp_s), [float(timestamp_s)])

    timestamps, values = buffer.snapshot(now_s=4.0)
    assert timestamps.tolist() == [1.0, 2.0, 3.0, 4.0]
    assert values[:, 0].tolist() == [1.0, 2.0, 3.0, 4.0]


def test_store_latest_per_system_and_keeps_attitude_samples() -> None:
    store = TelemetryStore()
    first = _frame(sysid=1, seq=0, t_wall_ms=1000, roll_rad=0.1)
    second = _frame(sysid=1, seq=1, t_wall_ms=1050, roll_rad=0.2)
    other_vehicle = _frame(sysid=2, seq=0, t_wall_ms=1050, roll_rad=0.3)
    store.ingest_frame(first)
    store.ingest_frame(second)
    store.ingest_frame(other_vehicle)

    assert store.latest(1, "telemetry.attitude") == second
    assert store.latest(2, "telemetry.attitude") == other_vehicle
    times, values = store.samples(1, "attitude")
    assert times.tolist() == [1.0, 1.05]
    assert values[:, 0].tolist() == pytest.approx([0.1, 0.2])


def test_store_records_vibration_and_ekf_variance_histories(tmp_path: Path) -> None:
    path = tmp_path / "store.tlog"
    make_synthetic_tlog(path, duration_s=1.1, seed=8)
    connection = mavutil.mavlink_connection(str(path))
    store = TelemetryStore()
    while (message := connection.recv_match(blocking=False)) is not None:
        store.ingest_mavlink(
            message,
            sysid=1,
            t_wall_ms=1_000 + int(getattr(message, "time_boot_ms", 0)),
        )

    vibration_times, vibration_values = store.samples(1, "vibration")
    ekf_times, ekf_values = store.samples(1, "ekf_variances")
    assert vibration_values.shape == (3, 6)
    assert ekf_values.shape == (3, 6)
    assert vibration_times.size == ekf_times.size == 3


def _frame(*, sysid: int, seq: int, t_wall_ms: int, roll_rad: float) -> FrameModel:
    return FrameModel(
        v=1,
        type="telemetry.attitude",
        seq=seq,
        sysid=sysid,
        t_wall_ms=t_wall_ms,
        t_boot_ms=t_wall_ms,
        data={
            "roll_rad": roll_rad,
            "pitch_rad": 0.0,
            "yaw_rad": 0.0,
            "rates_rps": [0.0, 0.0, 0.0],
        },
    )
