"""Test link protocol and deterministic fault injection over MAVLink tlogs."""

from __future__ import annotations

import io
import math
import random
from collections import deque
from pathlib import Path
from typing import Any, Protocol

from pymavlink import mavutil
from pymavlink.dialects.v20 import ardupilotmega


class Link(Protocol):
    """Minimal receive interface consumed by bridge ingest."""

    @property
    def target_system(self) -> int: ...

    def recv_match(
        self,
        blocking: bool = False,
        timeout: float | None = None,
    ) -> Any | None: ...


class FaultyLink:
    """Wrap a tlog reader with repeatable packet and heartbeat fault injection."""

    def __init__(
        self,
        path: str | Path,
        *,
        drop_probability: float = 0.0,
        duplicate_probability: float = 0.0,
        drop_types: set[str] | None = None,
        duplicate_types: set[str] | None = None,
        heartbeat_loss_s: float = 0.0,
        second_sysid: bool = False,
        gcs_heartbeat: bool = False,
        seed: int = 0,
    ) -> None:
        if not math.isfinite(drop_probability) or not 0.0 <= drop_probability <= 1.0:
            raise ValueError("drop_probability must be finite and between 0 and 1")
        if (
            not math.isfinite(duplicate_probability)
            or not 0.0 <= duplicate_probability <= 1.0
        ):
            raise ValueError("duplicate_probability must be finite and between 0 and 1")
        if not math.isfinite(heartbeat_loss_s) or heartbeat_loss_s < 0.0:
            raise ValueError("heartbeat_loss_s must be finite and non-negative")

        self._connection = mavutil.mavlink_connection(
            str(path), dialect="ardupilotmega", robust_parsing=True
        )
        self._drop_probability = drop_probability
        self._duplicate_probability = duplicate_probability
        self._drop_types = drop_types or set()
        self._duplicate_types = duplicate_types or set()
        self._heartbeat_loss_s = heartbeat_loss_s
        self._inject_second_sysid = second_sysid
        self._inject_gcs_heartbeat = gcs_heartbeat
        self._injected_heartbeats = False
        self._first_timestamp_s: float | None = None
        self._random = random.Random(seed)
        self._pending: deque[Any] = deque()

    @property
    def target_system(self) -> int:
        """Return the primary vehicle system ID."""
        return 1

    def recv_match(
        self,
        blocking: bool = False,
        timeout: float | None = None,
    ) -> Any | None:
        """Read a message while applying configured deterministic test faults."""
        while True:
            if self._pending:
                message = self._pending.popleft()
                is_duplicate = True
            else:
                message = self._connection.recv_match(
                    # A tlog is a finite file: pymavlink can block indefinitely
                    # after EOF when asked for a blocking read.
                    blocking=False,
                )
                is_duplicate = False
                if message is None:
                    return None

            if not is_duplicate and not self._injected_heartbeats:
                if message.get_type() == "HEARTBEAT" and message.get_srcSystem() == 1:
                    self._injected_heartbeats = True
                    injected = []
                    if self._inject_second_sysid:
                        injected.append(
                            _heartbeat_message(
                                sysid=2,
                                component_type=ardupilotmega.MAV_TYPE_QUADROTOR,
                            )
                        )
                    if self._inject_gcs_heartbeat:
                        injected.append(
                            _heartbeat_message(
                                sysid=255,
                                component_type=ardupilotmega.MAV_TYPE_GCS,
                            )
                        )
                    self._pending.extend(injected)

            if not is_duplicate:
                timestamp_s = float(getattr(message, "_timestamp", 0.0))
                if self._first_timestamp_s is None:
                    self._first_timestamp_s = timestamp_s
                elapsed_s = timestamp_s - self._first_timestamp_s

                if (
                    message.get_type() == "HEARTBEAT"
                    and message.get_srcSystem() == 1
                    and elapsed_s < self._heartbeat_loss_s - 1e-6
                ):
                    continue
                if message.get_type() in self._drop_types:
                    continue
                if self._random.random() < self._drop_probability:
                    continue

                should_duplicate = (
                    message.get_type() in self._duplicate_types
                    or self._random.random() < self._duplicate_probability
                )
                if should_duplicate:
                    self._pending.append(message)
                return message

            return message

    def close(self) -> None:
        """Close the underlying tlog connection."""
        self._connection.close()


def _heartbeat_message(sysid: int, component_type: int) -> Any:
    writer = io.BytesIO()
    encoder = ardupilotmega.MAVLink(writer, srcSystem=sysid, srcComponent=1)
    encoder.heartbeat_send(
        component_type,
        (
            ardupilotmega.MAV_AUTOPILOT_INVALID
            if component_type == ardupilotmega.MAV_TYPE_GCS
            else ardupilotmega.MAV_AUTOPILOT_ARDUPILOTMEGA
        ),
        0,
        0,
        ardupilotmega.MAV_STATE_ACTIVE,
    )
    parser = ardupilotmega.MAVLink(None)
    messages = parser.parse_buffer(writer.getvalue())
    if not messages:
        raise RuntimeError("could not decode injected heartbeat")
    return messages[0]
