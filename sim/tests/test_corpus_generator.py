import hashlib
import json
from pathlib import Path
import tempfile

import pytest

from sim.corpus.generate import (
    build_manifest,
    expand_matrix,
    load_matrix,
    validate_manifest,
    write_json,
)


MATRIX = Path(__file__).parents[1] / "corpus" / "matrix.yaml"


def test_matrix_expands_to_acceptance_counts_and_speed_cap() -> None:
    matrix = load_matrix(MATRIX)
    flights = expand_matrix(matrix)

    nominal = [flight for flight in flights if flight["fault"] is None]
    faulty = [flight for flight in flights if flight["fault"] is not None]
    assert len(nominal) >= 30
    assert len(faulty) >= 60
    assert matrix["sitl_speedup"] == 4
    assert all(flight["mission_shape"] in {"square", "triangle", "racetrack"} for flight in nominal)
    assert all(0 <= flight["wind_speed_mps"] <= 8 for flight in nominal)
    assert all(flight["fault"] and flight["expected_signals"] for flight in faulty)


def test_manifest_contains_sha256_for_every_artifact_and_validates() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "flight.tlog").write_bytes(b"mavlink-log")
        write_json(root / "labels.json", [{"file": "flight.tlog", "fault": None}])
        (root / "matrix.yaml").write_text("seed: 1\n", encoding="utf-8")

        manifest = build_manifest(root, "Copter-4.7.2")
        write_json(root / "manifest.json", manifest)
        assert manifest["files"]["flight.tlog"] == hashlib.sha256(b"mavlink-log").hexdigest()
        assert validate_manifest(root / "manifest.json", require_minimum=False)["ardupilot_tag"] == "Copter-4.7.2"

        (root / "flight.tlog").write_bytes(b"changed")
        with pytest.raises(ValueError, match="SHA256 mismatch"):
            validate_manifest(root / "manifest.json")


def test_manifest_requires_minimum_corpus_size() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        write_json(root / "labels.json", [{"file": "one.tlog", "fault": None}])
        (root / "one.tlog").write_bytes(b"data")
        manifest = build_manifest(root, "Copter-4.7.2")
        write_json(root / "manifest.json", manifest)
        with pytest.raises(ValueError, match="requires at least"):
            validate_manifest(root / "manifest.json")


def test_labels_are_json_serializable() -> None:
    flights = expand_matrix(load_matrix(MATRIX))
    first = flights[0]
    assert json.loads(json.dumps(first)) == first
