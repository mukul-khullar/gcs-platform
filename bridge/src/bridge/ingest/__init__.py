"""MAVLink message ingestion."""

from .link import DEFAULT_UDP_ENDPOINT, Link, open_udp_link
from .receiver import IngestedMessage, Ingestor

__all__ = [
    "DEFAULT_UDP_ENDPOINT",
    "IngestedMessage",
    "Ingestor",
    "Link",
    "open_udp_link",
]
