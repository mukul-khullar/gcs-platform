"""MAVLink wire-unit conversions and unknown-value sentinels."""

from __future__ import annotations

from typing import TypeVar

_Numeric = TypeVar("_Numeric", int, float)


def _not_sentinel(value: _Numeric, sentinels: tuple[int, ...]) -> _Numeric | None:
    return None if value in sentinels else value


def deg_e7_to_deg(value: int, *, sentinel: int | None = None) -> float | None:
    """Convert MAVLink degrees times 1e7 to degrees."""
    if sentinel is not None and value == sentinel:
        return None
    return value / 1e7


def mm_to_m(value: int, *, sentinel: int | None = None) -> float | None:
    """Convert millimetres to metres."""
    if sentinel is not None and value == sentinel:
        return None
    return value / 1000.0


def cmps_to_mps(value: int, *, sentinel: int | None = None) -> float | None:
    """Convert centimetres per second to metres per second."""
    if sentinel is not None and value == sentinel:
        return None
    return value / 100.0


def cdeg_to_deg(value: int, *, sentinel: int = 65535) -> float | None:
    """Convert centidegrees to degrees; 65535 is the MAVLink unknown sentinel."""
    if value == sentinel:
        return None
    return value / 100.0


def millivolts_to_volts(value: int, *, sentinel: int = 65535) -> float | None:
    """Convert millivolts to volts; 65535 means unknown."""
    if value == sentinel:
        return None
    return value / 1000.0


def centiamps_to_amps(value: int, *, sentinel: int = -1) -> float | None:
    """Convert centiamps to amps; -1 means unknown."""
    if value == sentinel:
        return None
    return value / 100.0


def centi_to_unitless(value: int, *, sentinel: int = 65535) -> float | None:
    """Convert centi-units (for example MAVLink eph/hdop) to unitless values."""
    if value == sentinel:
        return None
    return value / 100.0


def nullable_int(value: int, *, sentinels: tuple[int, ...]) -> int | None:
    """Return None for one of the field's MAVLink unknown sentinels."""
    return _not_sentinel(value, sentinels)
