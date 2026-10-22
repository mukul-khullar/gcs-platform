#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Sequence

from pymavlink import mavutil

from sim.simctl.runner import ScenarioRunner, load_scenario


SCENARIO_DIR = Path(__file__).resolve().parents[1] / "scenarios"
NOMINAL = "nominal_square"
SMOKE_SCENARIOS = (NOMINAL, "wind_gust_wp_mission", "gps_loss_at_40s")


def _sample_trajectory(
    trajectory: Sequence[tuple[float, float, float]],
    sample_count: int,
) -> list[tuple[float, float, float]]:
    if not trajectory:
        raise ValueError("trajectories must be non-empty")
    if len(trajectory) == 1:
        return [trajectory[0]] * sample_count
    samples: list[tuple[float, float, float]] = []
    for index in range(sample_count):
        position = index * (len(trajectory) - 1) / (sample_count - 1)
        lower = int(position)
        upper = min(lower + 1, len(trajectory) - 1)
        fraction = position - lower
        samples.append(tuple(
            trajectory[lower][axis] * (1 - fraction) + trajectory[upper][axis] * fraction
            for axis in range(3)
        ))
    return samples


def trajectory_rms_m(
    reference: Sequence[tuple[float, float, float]],
    repeat: Sequence[tuple[float, float, float]],
) -> float:
    if not reference or not repeat:
        raise ValueError("trajectories must be non-empty")
    sample_count = max(2, min(100, max(len(reference), len(repeat))))
    reference_samples = _sample_trajectory(reference, sample_count)
    repeat_samples = _sample_trajectory(repeat, sample_count)
    mean_squared_error = sum(
        sum((first[axis] - second[axis]) ** 2 for axis in range(3))
        for first, second in zip(reference_samples, repeat_samples, strict=True)
    ) / sample_count
    return math.sqrt(mean_squared_error)


def run_scenario(name: str, connection_uri: str) -> tuple[ScenarioRunner, list[tuple[float, float, float]]]:
    scenario = load_scenario(SCENARIO_DIR / f"{name}.yaml")
    connection = mavutil.mavlink_connection(connection_uri)
    runner = ScenarioRunner(scenario, connection, emit=lambda _: None)
    try:
        heartbeat = connection.wait_heartbeat(timeout=30)
        if heartbeat is None:
            raise TimeoutError(f"no SITL heartbeat at {connection_uri}")
        trajectory = runner.run()
        if len(trajectory) < 2:
            raise RuntimeError(f"{name} produced fewer than two trajectory samples")
        if name == "gps_loss_at_40s" and not runner.fault_signature_changed:
            raise RuntimeError("GPS-loss scenario did not detect its telemetry signature")
        return runner, trajectory
    finally:
        connection.close()


def run_smoke(connection_uri: str) -> None:
    _, nominal_first = run_scenario(NOMINAL, connection_uri)
    _, nominal_repeat = run_scenario(NOMINAL, connection_uri)
    rms_m = trajectory_rms_m(nominal_first, nominal_repeat)
    if rms_m > 2.0:
        raise AssertionError(f"nominal trajectory repeatability RMS {rms_m:.3f} m exceeds 2 m")
    print(f"{NOMINAL}: repeatability RMS {rms_m:.3f} m")

    for name in SMOKE_SCENARIOS[1:]:
        run_scenario(name, connection_uri)
        print(f"{name}: completed")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run headless SITL smoke scenarios.")
    parser.add_argument("--connect", default="udpin:0.0.0.0:14551")
    args = parser.parse_args(argv)
    run_smoke(args.connect)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
