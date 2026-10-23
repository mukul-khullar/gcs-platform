"""Test-only support for synthetic MAVLink links and logs."""

from .faulty_link import FaultyLink, Link
from .synthetic_tlog import make_synthetic_tlog

__all__ = ["FaultyLink", "Link", "make_synthetic_tlog"]
