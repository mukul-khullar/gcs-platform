"""Minimal MAVLink receive interface for live and test links."""

from __future__ import annotations

from typing import Any, Protocol, cast

from pymavlink import mavutil

DEFAULT_UDP_ENDPOINT = "udpin:0.0.0.0:14551"


class Link(Protocol):
    """Receive-side interface implemented by pymavlink and test connections."""

    @property
    def target_system(self) -> int: ...

    def recv_match(
        self,
        blocking: bool = False,
        timeout: float | None = None,
    ) -> Any | None: ...


def open_udp_link(endpoint: str = DEFAULT_UDP_ENDPOINT) -> Link:
    """Open the production UDP MAVLink 2 link, or the supplied endpoint."""
    connection = mavutil.mavlink_connection(
        endpoint, dialect="ardupilotmega", robust_parsing=True
    )
    return cast(Link, connection)
