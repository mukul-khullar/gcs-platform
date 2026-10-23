from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pymavlink import mavutil

from bridge import api as bridge_api
from bridge.api import create_app
from tests.support.synthetic_tlog import make_synthetic_tlog


class _PacedTlogLink:
    """Replay a finite tlog against its recorded timestamps in real time."""

    def __init__(self, path: Path) -> None:
        connection = mavutil.mavlink_connection(str(path), dialect="ardupilotmega")
        self._messages: list[Any] = []
        while (message := connection.recv_match(blocking=False)) is not None:
            self._messages.append(message)
        connection.close()
        if not self._messages:
            raise ValueError("test tlog must contain messages")
        self._first_timestamp = float(self._messages[0]._timestamp)
        self._started_at: float | None = None
        self._index = 0

    @property
    def target_system(self) -> int:
        return 1

    def recv_match(
        self, blocking: bool = False, timeout: float | None = None
    ) -> Any | None:
        if self._index >= len(self._messages):
            return None
        message = self._messages[self._index]
        if self._started_at is None:
            self._started_at = time.monotonic()
        target = self._started_at + float(message._timestamp) - self._first_timestamp
        delay_s = target - time.monotonic()
        if delay_s > 0:
            if not blocking:
                return None
            wait_s = delay_s if timeout is None else min(delay_s, timeout)
            time.sleep(wait_s)
            if target > time.monotonic():
                return None
        self._index += 1
        return message

    def close(self) -> None:
        return


def test_two_clients_receive_bounded_telemetry_and_state(tmp_path: Path) -> None:
    log_path = tmp_path / "realtime.tlog"
    make_synthetic_tlog(log_path, duration_s=2.0, seed=17)
    app = create_app(link_factory=lambda: _PacedTlogLink(log_path))

    with TestClient(app) as client:
        with (
            client.websocket_connect("/ws/telemetry") as first,
            client.websocket_connect("/ws/telemetry") as second,
        ):
            first_times = _receive_attitude_times(first, count=8)
            second_times = _receive_attitude_times(second, count=8)

            first_hz = 7 / (first_times[-1] - first_times[0])
            second_hz = 7 / (second_times[-1] - second_times[0])
            assert 14 <= first_hz <= 26, first_times
            assert 14 <= second_hz <= 26, second_times

            sizes = app.state.telemetry_broadcaster.client_queue_sizes
            assert len(sizes) == 2
            assert all(
                size <= 1
                for client_sizes in sizes.values()
                for size in client_sizes.values()
            )

            first.send_text('{"type":"ping"}')
            while first.receive_json()["type"] != "pong":
                pass

            state_response = client.get("/api/v1/state")
            assert state_response.status_code == 200
            topics = state_response.json()["vehicles"]["1"]
            assert {
                "telemetry.attitude",
                "telemetry.position",
                "vehicle.status",
            } <= set(topics)
            assert topics["telemetry.attitude"]["v"] == 1

    assert app.state.telemetry_broadcaster.client_count == 0


def test_lifespan_uses_bridge_link_url_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoints: list[str] = []

    def open_test_link(endpoint: str) -> _EmptyLink:
        endpoints.append(endpoint)
        return _EmptyLink()

    monkeypatch.setenv("BRIDGE_LINK_URL", "udpin:127.0.0.1:14552")
    monkeypatch.setattr(bridge_api, "open_udp_link", open_test_link)
    with TestClient(create_app()):
        pass

    assert endpoints == ["udpin:127.0.0.1:14552"]


def _receive_attitude_times(websocket: Any, *, count: int) -> list[float]:
    timestamps: list[float] = []
    while len(timestamps) < count:
        frame = websocket.receive_json()
        if frame.get("type") == "telemetry.attitude":
            timestamps.append(frame["t_wall_ms"] / 1000)
    return timestamps


class _EmptyLink:
    @property
    def target_system(self) -> int:
        return 1

    def recv_match(self, blocking: bool = False, timeout: float | None = None) -> None:
        del blocking, timeout
        time.sleep(0.005)
        return None

    def close(self) -> None:
        return
