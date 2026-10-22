from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import subprocess
from pathlib import Path
from typing import Any, Sequence

import yaml

if __package__:
    from .flight import run_flight
else:
    from flight import run_flight


CORPUS_DIR = Path(__file__).resolve().parent
REPO_ROOT = CORPUS_DIR.parents[1]
MAX_SPEEDUP = 4
MIN_NOMINAL = 30
MIN_FAULTY = 60
def load_matrix(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("corpus matrix must contain a YAML mapping")
    speedup = value.get("sitl_speedup")
    if speedup != MAX_SPEEDUP:
        raise ValueError(f"sitl_speedup must be exactly {MAX_SPEEDUP}")
    if int(value.get("nominal_runs", 0)) < MIN_NOMINAL:
        raise ValueError(f"matrix must request at least {MIN_NOMINAL} nominal runs")
    if not value.get("scenarios") or not value.get("faults"):
        raise ValueError("matrix requires scenarios and faults")
    return value


def expand_matrix(matrix: dict[str, Any], matrix_path: Path = CORPUS_DIR / "matrix.yaml") -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    for relative_path in matrix["scenarios"]:
        scenario_path = (matrix_path.parent / relative_path).resolve()
        if not scenario_path.is_file():
            raise FileNotFoundError(f"scenario file not found: {scenario_path}")
        scenario_data = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
        if not isinstance(scenario_data, dict) or "name" not in scenario_data:
            raise ValueError(f"invalid scenario file: {scenario_path}")
        scenarios.append(scenario_data)

    rng = random.Random(int(matrix["seed"]))
    wind_min, wind_max = matrix["wind_speed_range_mps"]
    shapes = matrix["mission_shapes"]
    flights: list[dict[str, Any]] = []
    for index in range(int(matrix["nominal_runs"])):
        flights.append({
            "scenario": scenarios[index % len(scenarios)]["name"],
            "scenario_params": scenarios[index % len(scenarios)].get("vehicle_params", {}),
            "fault": None,
            "onset_s": None,
            "severity": None,
            "expected_signals": [],
            "mission_shape": shapes[index % len(shapes)],
            "wind_speed_mps": round(rng.uniform(wind_min, wind_max), 2),
            "wind_direction_deg": rng.randrange(360),
            "duration_s": int(matrix["duration_s"]),
        })
    for scenario in scenarios:
        for fault_name, fault in matrix["faults"].items():
            signals = fault["expected_signals"]
            severities = fault["severities"]
            for onset_s in matrix["fault_onsets_s"]:
                for severity, settings in severities.items():
                    flights.append({
                        "scenario": scenario["name"],
                        "scenario_params": scenario.get("vehicle_params", {}),
                        "fault": fault_name,
                        "onset_s": float(onset_s),
                        "severity": severity,
                        "assignments": settings["assignments"],
                        "fault_duration_s": float(settings["duration_s"]),
                        "expected_signals": list(signals),
                        "mission_shape": shapes[len(flights) % len(shapes)],
                        "wind_speed_mps": float(
                            scenario.get("vehicle_params", {}).get("SIM_WIND_SPD", 0.0)
                        ),
                        "wind_direction_deg": 0,
                        "duration_s": int(matrix["duration_s"]),
                    })
    if sum(row["fault"] is not None for row in flights) < MIN_FAULTY:
        raise ValueError(f"matrix must expand to at least {MIN_FAULTY} faulty runs")
    return flights


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)


def build_manifest(root: Path, ardupilot_tag: str) -> dict[str, Any]:
    labels = json.loads((root / "labels.json").read_text(encoding="utf-8"))
    files = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    return {
        "schema_version": 1,
        "ardupilot_tag": ardupilot_tag,
        "flight_count": len(labels),
        "nominal_count": sum(row["fault"] is None for row in labels),
        "faulty_count": sum(row["fault"] is not None for row in labels),
        "files": files,
    }


def validate_manifest(path: Path, *, require_minimum: bool = True) -> dict[str, Any]:
    root = path.resolve().parent
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not re.fullmatch(r"Copter-\d+\.\d+\.\d+", manifest.get("ardupilot_tag", "")):
        raise ValueError("manifest has an invalid ArduPilot tag")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("manifest files must be a non-empty path-to-SHA256 mapping")
    actual_files = {
        item.relative_to(root).as_posix()
        for item in root.rglob("*")
        if item.is_file() and item.name != "manifest.json"
    }
    if actual_files != set(files):
        raise ValueError("manifest file list does not match corpus contents")
    for relative, expected in files.items():
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError(f"invalid SHA256 digest for {relative}")
        file_path = (root / relative).resolve()
        if root not in file_path.parents:
            raise ValueError(f"manifest path escapes corpus directory: {relative}")
        if hashlib.sha256(file_path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"SHA256 mismatch for {relative}")
    labels_path = root / "labels.json"
    if "labels.json" not in files or hashlib.sha256(labels_path.read_bytes()).hexdigest() != files["labels.json"]:
        raise ValueError("manifest does not hash labels.json")
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    if len({row["file"] for row in labels}) != len(labels):
        raise ValueError("labels contain duplicate flight paths")
    for row in labels:
        if row["file"] not in files or row["fault"] is not None and not row["expected_signals"]:
            raise ValueError(f"invalid label entry for {row.get('file')}")
    nominal = sum(row["fault"] is None for row in labels)
    faulty = sum(row["fault"] is not None for row in labels)
    if require_minimum and (nominal < MIN_NOMINAL or faulty < MIN_FAULTY):
        raise ValueError(
            f"corpus requires at least {MIN_NOMINAL} nominal and {MIN_FAULTY} faulty flights; "
            f"found {nominal} and {faulty}"
        )
    if manifest.get("flight_count") != len(labels) or manifest.get("nominal_count") != nominal or manifest.get("faulty_count") != faulty:
        raise ValueError("manifest flight counts do not match labels")
    return manifest


def _tag_from_versions() -> str:
    text = (REPO_ROOT / "sim" / "VERSIONS.md").read_text(encoding="utf-8")
    match = re.search(r"`(Copter-\d+\.\d+\.\d+)`", text)
    if match is None:
        raise ValueError("could not find pinned ArduCopter tag in sim/VERSIONS.md")
    return match.group(1)


def _run_host(matrix_path: Path, corpus_dir: Path, connection: str) -> None:
    matrix = load_matrix(matrix_path)
    jobs = expand_matrix(matrix, matrix_path)
    flights_dir = corpus_dir / "flights"
    flights_dir.mkdir(parents=True, exist_ok=True)
    corpus_dir.mkdir(parents=True, exist_ok=True)
    if matrix_path.resolve() != (corpus_dir / "matrix.yaml").resolve():
        (corpus_dir / "matrix.yaml").write_bytes(matrix_path.read_bytes())
    labels_path = corpus_dir / "labels.json"
    labels: list[dict[str, Any]] = []
    name = f"gcs-corpus-{random.randrange(1_000_000):06d}"
    command = (
        'exec sim_vehicle.py -v ArduCopter -f quad --speedup 4 --no-rebuild '
        '--custom-location="$HOME_LAT,$HOME_LON,$HOME_ALT_M,$HOME_YAW_DEG" '
        '--out=udp:127.0.0.1:14550 --out=udp:127.0.0.1:14551 '
        '--out=udp:host.docker.internal:14551 --out=udp:host.docker.internal:14552'
    )
    container_id = subprocess.check_output(
        [
            "docker", "compose", "run", "--build", "--rm", "--detach", "--no-deps",
            "--name", name, "--entrypoint", "/bin/sh", "sitl", "-ec", command,
        ],
        cwd=REPO_ROOT,
        text=True,
    ).strip()
    try:
        subprocess.run(
            ["docker", "exec", container_id, "python3", "/sim/tools/check_hb.py",
             "--in-container", "--connect", "udpin:127.0.0.1:14550", "--timeout", "60"],
            cwd=REPO_ROOT,
            check=True,
        )
        for index, job in enumerate(jobs):
            prefix = "nominal" if job["fault"] is None else "faulty"
            filename = f"{prefix}_{index + 1:03d}.tlog"
            container_path = f"/tmp/{filename}"
            payload = {**job, "output": container_path, "connection": connection}
            subprocess.run(
                ["docker", "exec", container_id, "python3", "/sim/corpus/generate.py",
                 "--in-container", "--flight-json", json.dumps(payload, separators=(",", ":"))],
                cwd=REPO_ROOT,
                check=True,
            )
            subprocess.run(
                ["docker", "cp", f"{container_id}:{container_path}", str(flights_dir / filename)],
                cwd=REPO_ROOT,
                check=True,
            )
            labels.append({
                "file": f"flights/{filename}",
                "fault": job["fault"],
                "onset_s": job["onset_s"],
                "severity": job["severity"],
                "expected_signals": job["expected_signals"],
                "scenario": job["scenario"],
                "mission_shape": job["mission_shape"],
                "wind_speed_mps": job["wind_speed_mps"],
            })
            write_json(labels_path, labels)
            write_json(corpus_dir / "manifest.json", build_manifest(corpus_dir, _tag_from_versions()))
            print(f"[{index + 1}/{len(jobs)}] captured {filename}")
    finally:
        subprocess.run(["docker", "stop", container_id], cwd=REPO_ROOT, check=False)
    validate_manifest(corpus_dir / "manifest.json")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate and hash the SITL flight corpus.")
    parser.add_argument("--matrix", type=Path, default=CORPUS_DIR / "matrix.yaml")
    parser.add_argument("--corpus-dir", type=Path, default=CORPUS_DIR)
    parser.add_argument("--connection", default="udpin:127.0.0.1:14551")
    parser.add_argument("--confirm-sitl", action="store_true")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--validate-manifest", type=Path)
    parser.add_argument("--in-container", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--flight-json", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.validate_manifest:
        validate_manifest(args.validate_manifest)
        print("manifest valid")
        return 0
    if args.in_container:
        if args.flight_json is None:
            parser.error("--flight-json is required in container mode")
        job = json.loads(args.flight_json)
        run_flight(job, Path(job["output"]), job["connection"])
        return 0
    matrix = load_matrix(args.matrix)
    jobs = expand_matrix(matrix, args.matrix)
    if args.plan:
        print(json.dumps({"runs": len(jobs), "nominal": matrix["nominal_runs"], "faulty": len(jobs) - matrix["nominal_runs"], "speedup": matrix["sitl_speedup"]}, indent=2))
        return 0
    if not args.confirm_sitl:
        parser.error("refusing to arm SITL without --confirm-sitl")
    _run_host(args.matrix.resolve(), args.corpus_dir.resolve(), args.connection)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
