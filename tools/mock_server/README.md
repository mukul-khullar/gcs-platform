# Mock telemetry server

Replays the telemetry fixture over `ws://localhost:8000/ws/telemetry`. It emits synthetic attitude and position frames at 20 Hz, with the vehicle following a slow 30 m circle, and replays the remaining fixture events at 20 Hz.

## Run

```powershell
pnpm start -- --loop
```

Omit `--loop` to replay status and event fixture frames once per server process. The synthetic telemetry continues while connected either way. Run `pnpm test` to exercise the synthetic trajectory.
