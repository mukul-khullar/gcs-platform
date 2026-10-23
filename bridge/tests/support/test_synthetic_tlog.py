import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from pymavlink import mavutil

from tests.support.synthetic_tlog import make_synthetic_tlog


def read_messages(path: Path) -> list[object]:
    connection = mavutil.mavlink_connection(
        str(path), dialect="ardupilotmega", robust_parsing=True
    )
    messages = []
    while (message := connection.recv_match(blocking=False)) is not None:
        messages.append(message)
    connection.close()
    return messages


def test_tlog_round_trips_expected_message_counts_rates_and_mavlink_v2(
    tmp_path: Path,
) -> None:
    path = tmp_path / "synthetic.tlog"
    make_synthetic_tlog(path, duration_s=10, seed=17)

    messages = read_messages(path)
    counts = Counter(message.get_type() for message in messages)
    expected_counts = {
        "HEARTBEAT": 10,
        "ATTITUDE": 200,
        "GLOBAL_POSITION_INT": 100,
        "GPS_RAW_INT": 20,
        "EKF_STATUS_REPORT": 20,
        "VIBRATION": 20,
        "SYS_STATUS": 20,
    }
    assert counts == expected_counts

    timestamps_by_type: dict[str, list[float]] = defaultdict(list)
    for message in messages:
        timestamps_by_type[message.get_type()].append(message._timestamp)
        assert message.get_srcSystem() == 1
        assert message.get_srcComponent() == 1
        assert message.get_msgbuf()[0] == 0xFD

    for message_type, timestamps in timestamps_by_type.items():
        measured_rate_hz = (len(timestamps) - 1) / (timestamps[-1] - timestamps[0])
        expected_rate_hz = {
            "HEARTBEAT": 1,
            "ATTITUDE": 20,
            "GLOBAL_POSITION_INT": 10,
            "GPS_RAW_INT": 2,
            "EKF_STATUS_REPORT": 2,
            "VIBRATION": 2,
            "SYS_STATUS": 2,
        }[message_type]
        assert abs(measured_rate_hz - expected_rate_hz) <= expected_rate_hz * 0.05


def test_tlog_deterministic_for_same_seed(tmp_path: Path) -> None:
    first_path = tmp_path / "first.tlog"
    second_path = tmp_path / "second.tlog"

    make_synthetic_tlog(first_path, duration_s=2, seed=5)
    make_synthetic_tlog(second_path, duration_s=2, seed=5)

    assert first_path.read_bytes() == second_path.read_bytes()


def test_tlog_is_readable_by_mavlogdump(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.tlog"
    make_synthetic_tlog(path, duration_s=2)

    result = subprocess.run(
        [sys.executable, "-m", "pymavlink.tools.mavlogdump", str(path)],
        capture_output=True,
        check=True,
        text=True,
    )

    assert "HEARTBEAT" in result.stdout
