"""Threaded MAVLink receiver which hands immutable messages to asyncio."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any

from pymavlink.dialects.v20 import ardupilotmega

from .link import Link

_LOGGER = logging.getLogger(__name__)
_POLL_TIMEOUT_S = 0.5


@dataclass(frozen=True, slots=True)
class IngestedMessage:
    """Received MAVLink message and bridge wall-clock receive time in ms."""

    msg: Any
    sysid: int
    compid: int
    t_wall_ms: int


class Ingestor:
    """Receive autopilot-component traffic on a thread and enqueue it safely."""

    def __init__(
        self,
        link: Link,
        queue: asyncio.Queue[IngestedMessage],
    ) -> None:
        if queue.maxsize <= 0:
            raise ValueError("ingest queue must have a finite positive maxsize")

        self._link = link
        self._queue = queue
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._autopilot_systems: set[int] = set()
        self._seen_components: set[tuple[int, int]] = set()
        self._message_counts: Counter[str] = Counter()
        self._parse_errors = 0
        self._dropped_count = 0
        self._last_heartbeat_monotonic: float | None = None
        self._started_monotonic: float | None = None
        self._thread_error: BaseException | None = None

    @property
    def target_system(self) -> int:
        """Return the primary system selected by the underlying link."""
        return self._link.target_system

    @property
    def message_counts(self) -> dict[str, int]:
        """Return accepted message counts keyed by MAVLink message type."""
        with self._lock:
            return dict(self._message_counts)

    @property
    def msg_rate(self) -> dict[str, float]:
        """Return average accepted message rates in messages per second."""
        with self._lock:
            if self._started_monotonic is None:
                return {}
            elapsed_s = max(time.monotonic() - self._started_monotonic, 1e-9)
            return {
                message_type: count / elapsed_s
                for message_type, count in self._message_counts.items()
            }

    @property
    def parse_errors(self) -> int:
        """Return the number of parser-reported malformed packets."""
        with self._lock:
            return self._parse_errors

    @property
    def dropped_count(self) -> int:
        """Return the number of enqueued messages dropped to make queue space."""
        with self._lock:
            return self._dropped_count

    @property
    def last_heartbeat_monotonic(self) -> float | None:
        """Return the receipt monotonic timestamp of the latest vehicle heartbeat."""
        with self._lock:
            return self._last_heartbeat_monotonic

    @property
    def last_heartbeat(self) -> float | None:
        """Return the latest accepted heartbeat receipt time in monotonic seconds."""
        return self.last_heartbeat_monotonic

    @property
    def seen_components(self) -> set[tuple[int, int]]:
        """Return accepted (system ID, component ID) pairs."""
        with self._lock:
            return set(self._seen_components)

    @property
    def thread_error(self) -> BaseException | None:
        """Return an unexpected receive-thread failure, if one occurred."""
        with self._lock:
            return self._thread_error

    @property
    def is_running(self) -> bool:
        """Whether the dedicated receive thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def start(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Start receiving on a dedicated thread using the supplied event loop."""
        if self.is_running:
            raise RuntimeError("ingestor is already running")
        if self._thread is not None:
            raise RuntimeError("ingestor cannot be restarted after stop")

        self._loop = loop if loop is not None else asyncio.get_running_loop()
        self._started_monotonic = time.monotonic()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._receive_loop,
            name="mavlink-ingest",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Request thread shutdown and join for at most one second."""
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=1.0)
        if self._thread.is_alive():
            raise TimeoutError("MAVLink ingest thread did not stop within 1 second")
        if self._thread_error is not None:
            raise RuntimeError("MAVLink ingest thread failed") from self._thread_error

    def _receive_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                msg = self._link.recv_match(
                    blocking=True,
                    timeout=_POLL_TIMEOUT_S,
                )
                if msg is None:
                    self._stop_event.wait(0.01)
                    continue

                t_wall_ms = time.time_ns() // 1_000_000
                self._receive_message(msg, t_wall_ms)
        except (OSError, RuntimeError, ValueError) as error:
            with self._lock:
                self._thread_error = error
            _LOGGER.exception("MAVLink receive thread failed")

    def _receive_message(self, msg: Any, t_wall_ms: int) -> None:
        if msg.get_type() == "BAD_DATA":
            with self._lock:
                self._parse_errors += 1
            return

        sysid = int(msg.get_srcSystem())
        compid = int(msg.get_srcComponent())
        message_type = str(msg.get_type())

        if message_type == "HEARTBEAT":
            if compid != ardupilotmega.MAV_COMP_ID_AUTOPILOT1:
                return
            if msg.type == ardupilotmega.MAV_TYPE_GCS:
                return
            if msg.autopilot == ardupilotmega.MAV_AUTOPILOT_INVALID:
                return
            with self._lock:
                self._autopilot_systems.add(sysid)
                self._seen_components.add((sysid, compid))
                self._message_counts[message_type] += 1
                self._last_heartbeat_monotonic = time.monotonic()
        else:
            if compid != ardupilotmega.MAV_COMP_ID_AUTOPILOT1:
                return
            with self._lock:
                if sysid not in self._autopilot_systems:
                    return
                self._seen_components.add((sysid, compid))
                self._message_counts[message_type] += 1

        ingested = IngestedMessage(
            msg=msg,
            sysid=sysid,
            compid=compid,
            t_wall_ms=t_wall_ms,
        )
        loop = self._loop
        if loop is None:
            raise RuntimeError("ingestor has no asyncio event loop")
        loop.call_soon_threadsafe(self._enqueue, ingested)

    def _enqueue(self, ingested: IngestedMessage) -> None:
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            else:
                self._queue.task_done()
                with self._lock:
                    self._dropped_count += 1
        self._queue.put_nowait(ingested)
