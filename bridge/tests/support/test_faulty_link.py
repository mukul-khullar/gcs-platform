from pathlib import Path

from pymavlink import mavutil

from tests.support.faulty_link import FaultyLink, Link
from tests.support.synthetic_tlog import make_synthetic_tlog


def test_faulty_link_injects_drops_duplicates_and_heartbeat_sources(
    tmp_path: Path,
) -> None:
    path = tmp_path / "synthetic.tlog"
    make_synthetic_tlog(path, duration_s=4, seed=11)
    link: Link = FaultyLink(
        path,
        drop_types={"ATTITUDE"},
        duplicate_types={"GLOBAL_POSITION_INT"},
        heartbeat_loss_s=2.0,
        second_sysid=True,
        gcs_heartbeat=True,
        seed=0,
    )

    received = []
    while (message := link.recv_match(blocking=False)) is not None:
        received.append(message)
    link.close()

    attitude_count = sum(message.get_type() == "ATTITUDE" for message in received)
    global_position_count = sum(
        message.get_type() == "GLOBAL_POSITION_INT" for message in received
    )
    heartbeats = [message for message in received if message.get_type() == "HEARTBEAT"]

    assert attitude_count < 80
    assert global_position_count > 40
    assert any(message.get_srcSystem() == 2 for message in heartbeats)
    assert any(
        message.get_srcSystem() == 255 and message.type == mavutil.mavlink.MAV_TYPE_GCS
        for message in heartbeats
    )
    assert link.target_system == 1


def test_heartbeat_loss_suppresses_primary_vehicle_heartbeat(
    tmp_path: Path,
) -> None:
    path = tmp_path / "synthetic.tlog"
    make_synthetic_tlog(path, duration_s=5, seed=1)
    link = FaultyLink(path, heartbeat_loss_s=3.0)

    received_heartbeats = []
    while (message := link.recv_match(blocking=False)) is not None:
        if message.get_type() == "HEARTBEAT":
            received_heartbeats.append(message)
    link.close()

    assert len(received_heartbeats) == 2
    assert all(
        message._timestamp - 1_700_000_000 >= 3.0 - 1e-6
        for message in received_heartbeats
    )
