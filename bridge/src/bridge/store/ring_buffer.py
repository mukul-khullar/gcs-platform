"""Fixed-capacity NumPy ring buffer with a 60-second time window."""

from __future__ import annotations

import math
import threading

import numpy as np
from numpy.typing import NDArray


class TimeRingBuffer:
    """Store timestamped float samples, retaining at least the latest 60 seconds."""

    def __init__(
        self,
        columns: int,
        *,
        rate_hz: float,
        duration_s: float = 60.0,
    ) -> None:
        if columns <= 0:
            raise ValueError("columns must be positive")
        if not math.isfinite(rate_hz) or rate_hz <= 0:
            raise ValueError("rate_hz must be finite and positive")
        if not math.isfinite(duration_s) or duration_s <= 0:
            raise ValueError("duration_s must be finite and positive")
        self.duration_s = duration_s
        self.columns = columns
        self.capacity = math.ceil(rate_hz * duration_s) + 1
        self._timestamps = np.full(self.capacity, np.nan, dtype=np.float64)
        self._values = np.full((self.capacity, columns), np.nan, dtype=np.float64)
        self._next = 0
        self._size = 0
        self._lock = threading.Lock()

    def append(
        self, timestamp_s: float, values: NDArray[np.float64] | list[float]
    ) -> None:
        """Append one sample with a monotonic timestamp in seconds."""
        value_array = np.asarray(values, dtype=np.float64)
        if value_array.shape != (self.columns,):
            raise ValueError(f"expected {self.columns} sample values")
        if not math.isfinite(timestamp_s):
            raise ValueError("timestamp_s must be finite")
        with self._lock:
            self._timestamps[self._next] = timestamp_s
            self._values[self._next] = value_array
            self._next = (self._next + 1) % self.capacity
            self._size = min(self._size + 1, self.capacity)

    def snapshot(
        self, *, now_s: float | None = None
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """Return chronological (timestamps, values) within the 60-second window."""
        with self._lock:
            start = (self._next - self._size) % self.capacity
            indices = (start + np.arange(self._size)) % self.capacity
            timestamps = self._timestamps[indices].copy()
            values = self._values[indices].copy()
        if now_s is None or timestamps.size == 0:
            return timestamps, values
        keep = timestamps >= now_s - self.duration_s
        return timestamps[keep], values[keep]
