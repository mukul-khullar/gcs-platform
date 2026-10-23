"""Per-topic rate limiter loaded from bridge/config/topic_rates.yaml."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import yaml


def _default_rates_path() -> Path:
    """Locate root-level config in both source and installed Docker layouts."""
    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        candidate = parent / "config" / "topic_rates.yaml"
        if candidate.is_file():
            return candidate
    return module_path.parents[3] / "config" / "topic_rates.yaml"


DEFAULT_TOPIC_RATES_PATH = _default_rates_path()


class TopicRateLimiter:
    """Allow the first frame immediately, then enforce per-topic Hz limits.

    A ``null`` rate in the config denotes an event-driven topic without a
    periodic rate limit.
    """

    def __init__(
        self,
        rates_hz: dict[str, float | None],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        for topic, rate_hz in rates_hz.items():
            if rate_hz is not None and rate_hz <= 0:
                raise ValueError(f"rate for {topic!r} must be positive or null")
        self._rates_hz = dict(rates_hz)
        self._clock = clock
        self._last_emitted_s: dict[str, float] = {}

    @classmethod
    def from_yaml(cls, path: str | Path = DEFAULT_TOPIC_RATES_PATH) -> TopicRateLimiter:
        """Load topic rates from a YAML mapping of topic names to Hz or null."""
        with Path(path).open(encoding="utf-8") as rates_file:
            raw_rates = yaml.safe_load(rates_file)
        if not isinstance(raw_rates, dict):
            raise ValueError("topic rate config must be a YAML mapping")
        rates: dict[str, float | None] = {}
        for topic, rate_hz in raw_rates.items():
            if not isinstance(topic, str) or (
                rate_hz is not None and not isinstance(rate_hz, (int, float))
            ):
                raise ValueError("topic rate config must map names to Hz or null")
            rates[topic] = float(rate_hz) if rate_hz is not None else None
        return cls(rates)

    def allow(self, topic: str, *, now_s: float | None = None) -> bool:
        """Return whether the topic may emit at the current monotonic time."""
        rate_hz = self._rates_hz.get(topic)
        if rate_hz is None:
            return True
        current_s = self._clock() if now_s is None else now_s
        last_s = self._last_emitted_s.get(topic)
        min_interval_s = 1.0 / rate_hz
        if last_s is not None and current_s - last_s < min_interval_s * 0.95:
            return False
        self._last_emitted_s[topic] = current_s
        return True
