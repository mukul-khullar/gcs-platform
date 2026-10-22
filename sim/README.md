# SITL simulator platform

Owner: T1

This area contains the ArduPilot SITL runtime, scenario definitions, simulator
control utilities, reusable test data, and replay support. Simulator artifacts
and tools belong here; shared message and API contracts remain in `contracts/`.

## Layout

| Directory | Purpose |
|-----------|---------|
| `docker/` | Container definitions and simulator image configuration |
| `scenarios/` | Repeatable SITL scenario definitions |
| `simctl/` | Simulator lifecycle and control entry points |
| `corpus/` | Reusable inputs for simulator and regression runs |
| `replay/` | Flight-log and telemetry replay support |
| `fixtures/` | Small checked-in simulator fixtures |
| `tools/` | Simulator-specific helper tools |

## Versions

Pinned simulator dependencies and the ArduCopter release are recorded in
[`VERSIONS.md`](VERSIONS.md). Do not change pins without an explicit review.

## Docker prerequisite

Run `docker info` before starting containerized SITL. On the host inspected for
this setup, Docker CLI 29.9.2 was installed, but the Docker Desktop Linux engine
was not running or reachable.

## Build and run

Start the container and wait up to 60 seconds for its MAVLink heartbeat
healthcheck:

```powershell
make sim-up
```

The first invocation builds ArduCopter from the tag in `VERSIONS.md`; the
initial image build takes longer than the startup healthcheck. Subsequent
starts use the cached image. Set `COPTER_TAG` only when intentionally building
a different reviewed release.

The vehicle starts at the fixed home position configured by `HOME_LAT`,
`HOME_LON`, `HOME_ALT_M`, and `HOME_YAW_DEG` (defaults: `37.4000`,
`-122.0800`, `20`, and `0`). It runs headless with no map or console. MAVLink
outputs are sent to host UDP ports 14551 and 14552; the image downloads and
builds its dependencies at image-build time, not container runtime.

Check for a heartbeat from the host:

```powershell
python sim/tools/check_hb.py
```

The checker uses `docker compose exec` to read the container-local heartbeat
and prints the MAVLink system ID and flight mode. Set the timeout with
`--timeout`.

## Record a nominal motion fixture

The recorder requests rates for the required MAVLink messages, switches the
local SITL vehicle to GUIDED, arms, takes off to 20 m, and flies a 10 m square.
It captures a 60-second raw MAVLink tlog, validates the message coverage and
motion, then lands and disarms. It prints counts for each message type. This
tool sends only its fixed allow-listed SITL commands; run it only against the
local simulator:

```powershell
python -m pip install -r sim/requirements.txt
python sim/tools/record_fixture.py --confirm-sitl
```

The recorder runs in the SITL container and listens only on
`127.0.0.1:14551`. After validation, the host command copies the tlog into
`sim/fixtures/nominal_60s.tlog`. The file is ignored by Git because flight
recordings are generated artifacts.

Load the tlog with pymavlink:

```python
from pymavlink import mavutil
log = mavutil.mavlink_connection("sim/fixtures/nominal_60s.tlog")
while (msg := log.recv_match(blocking=False)) is not None:
    print(msg.get_type(), msg.to_dict())
log.close()
```

Stop SITL with:

```powershell
make sim-down
```

CI builds the pinned SITL image with a GitHub Actions layer cache, starts it
headless, and runs heartbeat, repeatability, fault-signature, and scenario smoke
checks. The smoke runner waits on MAVLink telemetry rather than fixed sleeps.

## Generate a labeled corpus

See [`docs/corpus.md`](docs/corpus.md) for the seeded 102-flight nominal and
fault sweep, manifest validation, and pandas loading example.

## Replay a telemetry log

Replay preserves each MAVLink packet’s raw bytes, including its original
system/component IDs, and scales capture timing by the requested speed:

```powershell
replay run sim/fixtures/nominal_60s.tlog --speed 2 --out udp:127.0.0.1:14551
replay run sim/fixtures/nominal_60s.tlog --speed 1 --out udp:127.0.0.1:14551 --loop
```

Install the project with `python -m pip install -e sim` to add the `replay`
command. Speed must be between 0.5x and 8x.
