from __future__ import annotations

import pytest

from sim.tools.sitl_smoke import trajectory_rms_m


def test_trajectory_rms_resamples_repeats_with_different_sample_counts() -> None:
    reference = [(0.0, 0.0, 0.0), (5.0, 0.0, 5.0), (10.0, 0.0, 10.0)]
    repeat = [(0.0, 0.5, 0.0), (2.5, 0.5, 2.5), (5.0, 0.5, 5.0),
              (7.5, 0.5, 7.5), (10.0, 0.5, 10.0)]

    assert trajectory_rms_m(reference, repeat) == pytest.approx(0.5)


def test_trajectory_rms_rejects_empty_trajectory() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        trajectory_rms_m([], [(0.0, 0.0, 0.0)])
