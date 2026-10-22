from __future__ import annotations

from collections import deque
import socket
import struct
import threading
import time

from pymavlink import mavutil
import pytest

from sim.replay.cli import replay_file


def _write_tlog(path, intervals_s: list[float]) -> list[bytes]:
    encoder = mavutil.mavlink.MAVLink(None)
    encoder.srcSystem = 23
    encoder.srcComponent = 42
    frames = [
        mavutil.mavlink.MAVLink_heartbeat_message(2, 3, 0, 4, 3, 3).pack(encoder)
        for _ in intervals_s
    ]
    timestamp_us = 1_800_000_000_000_000
    with path.open("wb") as output:
        for frame, interval_s in zip(frames, intervals_s, strict=True):
            output.write(struct.pack(">Q", timestamp_us))
            output.write(frame)
            timestamp_us += round(interval_s * 1_000_000)
    return frames


def test_replays_fixture_over_udp_with_count_ids_and_timing(tmp_path) -> None:
    source = tmp_path / "fixture.tlog"
    intervals_s = [0.08, 0.12, 0.16, 0.20, 0.24]
    expected_frames = _write_tlog(source, intervals_s)
    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener.bind(("127.0.0.1", 0))
    listener.settimeout(1)
    address, port = listener.getsockname()
    received: deque[tuple[bytes, float]] = deque()

    def collect() -> None:
        for _ in expected_frames:
            frame, _ = listener.recvfrom(2048)
            received.append((frame, time.monotonic()))

    receiver = threading.Thread(target=collect)
    receiver.start()
    count = replay_file(source, f"udp:{address}:{port}", speed=2)
    receiver.join(timeout=2)
    listener.close()

    assert not receiver.is_alive()
    assert count == len(expected_frames)
    assert [frame for frame, _ in received] == expected_frames
    decoder = mavutil.mavlink.MAVLink(None)
    messages = [
        message
        for frame, _ in received
        for message in decoder.parse_buffer(frame)
    ]
    assert all(message.get_srcSystem() == 23 for message in messages)
    assert all(message.get_srcComponent() == 42 for message in messages)
    observed_intervals = [
        received[index + 1][1] - received[index][1]
        for index in range(len(received) - 1)
    ]
    expected_intervals = [interval / 2 for interval in intervals_s[:-1]]
    assert max(
        abs(observed - expected)
        for observed, expected in zip(observed_intervals, expected_intervals, strict=True)
    ) < 0.020


def test_loop_restarts_log_until_interrupted(tmp_path, monkeypatch) -> None:
    source = tmp_path / "fixture.tlog"
    expected_frames = _write_tlog(source, [0.01, 0.02, 0.03])
    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener.bind(("127.0.0.1", 0))
    listener.settimeout(1)
    address, port = listener.getsockname()
    received = []

    def collect() -> None:
        for _ in range(len(expected_frames) * 2):
            received.append(listener.recvfrom(2048)[0])

    receiver = threading.Thread(target=collect)
    receiver.start()
    sleep_count = 0

    def stop_after_two_passes(_delay_s: float) -> None:
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count == len(expected_frames) * 2:
            raise KeyboardInterrupt

    monkeypatch.setattr("sim.replay.cli.time.sleep", stop_after_two_passes)
    with pytest.raises(KeyboardInterrupt):
        replay_file(source, f"udp:{address}:{port}", speed=2, loop=True)
    receiver.join(timeout=2)
    listener.close()

    assert not receiver.is_alive()
    assert received == expected_frames * 2


@pytest.mark.parametrize("speed", [0.49, 8.01, 0, -1])
def test_rejects_speed_outside_supported_range(speed) -> None:
    with pytest.raises(ValueError, match="between 0.5 and 8"):
        replay_file("unused.tlog", "udp:127.0.0.1:14551", speed=speed)
