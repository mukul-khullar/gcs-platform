import asyncio
import io
from collections.abc import Callable
from pathlib import Path

import pytest
from pymavlink import mavutil
from pymavlink.dialects.v20 import ardupilotmega

from bridge.ingest import IngestedMessage, Ingestor
from tests.support.faulty_link import FaultyLink
from tests.support.synthetic_tlog import make_synthetic_tlog


async def wait_for(predicate: Callable[[], bool], *, timeout_s: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("ingest condition was not reached before timeout")
        await asyncio.sleep(0.005)


@pytest.mark.asyncio
async def test_ingests_autopilot_messages_and_tracks_each_vehicle_sysid(
    tmp_path: Path,
) -> None:
    path = tmp_path / "messages.tlog"
    make_synthetic_tlog(path, duration_s=2, seed=3)
    link = FaultyLink(path, second_sysid=True, gcs_heartbeat=True)
    queue: asyncio.Queue[IngestedMessage] = asyncio.Queue(maxsize=256)
    ingestor = Ingestor(link, queue)

    ingestor.start()
    try:
        await wait_for(
            lambda: (
                queue.qsize() == sum(ingestor.message_counts.values())
                and len(ingestor.message_counts) >= 7
            )
        )
    finally:
        ingestor.stop()
        link.close()

    received = [queue.get_nowait() for _ in range(queue.qsize())]
    received_types = {item.msg.get_type() for item in received}
    assert {"HEARTBEAT", "ATTITUDE", "GPS_RAW_INT"} <= received_types
    assert (1, 1) in ingestor.seen_components
    assert (2, 1) in ingestor.seen_components
    assert all(sysid != 255 for sysid, _ in ingestor.seen_components)
    assert all(item.t_wall_ms > 0 for item in received)
    assert ingestor.last_heartbeat_monotonic is not None
    assert ingestor.message_counts["ATTITUDE"] > 0
    assert ingestor.msg_rate["ATTITUDE"] > 0.0


@pytest.mark.asyncio
async def test_bounded_queue_drops_oldest_message_and_counts_overflow(
    tmp_path: Path,
) -> None:
    path = tmp_path / "overflow.tlog"
    make_synthetic_tlog(path, duration_s=2, seed=4)
    link = FaultyLink(path)
    queue: asyncio.Queue[IngestedMessage] = asyncio.Queue(maxsize=1)
    ingestor = Ingestor(link, queue)

    ingestor.start()
    try:
        await wait_for(
            lambda: (
                ingestor.dropped_count > 0
                and queue.qsize() + ingestor.dropped_count
                == sum(ingestor.message_counts.values())
            )
        )
    finally:
        ingestor.stop()
        link.close()

    assert queue.qsize() == 1
    assert ingestor.dropped_count > 0
    retained = queue.get_nowait()
    assert retained.msg.get_type() == "ATTITUDE"


@pytest.mark.asyncio
async def test_stop_joins_receive_thread_promptly(tmp_path: Path) -> None:
    path = tmp_path / "stop.tlog"
    make_synthetic_tlog(path, duration_s=60, seed=5)
    link = FaultyLink(path)
    queue: asyncio.Queue[IngestedMessage] = asyncio.Queue(maxsize=8)
    ingestor = Ingestor(link, queue)

    ingestor.start()
    await asyncio.sleep(0.02)
    started = asyncio.get_running_loop().time()
    ingestor.stop()
    elapsed_s = asyncio.get_running_loop().time() - started
    link.close()

    assert elapsed_s < 1.0
    assert not ingestor.is_running


@pytest.mark.asyncio
async def test_ignores_non_autopilot_components() -> None:
    messages = [
        _encoded_message(1, "heartbeat"),
        _encoded_message(100, "attitude"),
        _encoded_message(1, "attitude"),
    ]
    link = _MemoryLink(messages)
    queue: asyncio.Queue[IngestedMessage] = asyncio.Queue(maxsize=8)
    ingestor = Ingestor(link, queue)

    ingestor.start()
    try:
        await wait_for(
            lambda: (
                ingestor.message_counts.get("ATTITUDE") == 1
                and queue.qsize() == sum(ingestor.message_counts.values())
            )
        )
    finally:
        ingestor.stop()

    received = [queue.get_nowait() for _ in range(queue.qsize())]
    assert [item.msg.get_type() for item in received] == ["HEARTBEAT", "ATTITUDE"]
    assert ingestor.seen_components == {(1, 1)}


def test_ingested_message_is_frozen() -> None:
    message = mavutil.mavlink.MAVLink_heartbeat_message(2, 3, 0, 0, 4, 3)
    ingested = IngestedMessage(message, 1, 1, 123)

    with pytest.raises(AttributeError):
        ingested.sysid = 2  # type: ignore[misc]


class _MemoryLink:
    def __init__(self, messages: list[object]) -> None:
        self._messages = iter(messages)

    @property
    def target_system(self) -> int:
        return 1

    def recv_match(
        self, blocking: bool = False, timeout: float | None = None
    ) -> object | None:
        del blocking, timeout
        return next(self._messages, None)


def _encoded_message(compid: int, message_type: str) -> object:
    packet = io.BytesIO()
    encoder = ardupilotmega.MAVLink(packet, srcSystem=1, srcComponent=compid)
    if message_type == "heartbeat":
        encoder.heartbeat_send(
            ardupilotmega.MAV_TYPE_QUADROTOR,
            ardupilotmega.MAV_AUTOPILOT_ARDUPILOTMEGA,
            0,
            0,
            ardupilotmega.MAV_STATE_ACTIVE,
        )
    else:
        encoder.attitude_send(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    decoded = ardupilotmega.MAVLink(None).parse_buffer(packet.getvalue())
    assert decoded is not None and len(decoded) == 1
    return decoded[0]
