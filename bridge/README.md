# bridge

Owner: T2

The bridge is a Python 3.11 `src/`-layout package managed by uv. Dependency
versions are resolved and pinned in `uv.lock`.

## Development

Install uv, then run `make -C bridge test lint typecheck`.

## Run

Start the API with `uv run --locked uvicorn bridge.api:app --host 0.0.0.0
--port 8000`, or build and run the Docker image. It exposes `GET /healthz`,
`GET /api/v1/state`, and `WS /ws/telemetry`. The telemetry lifespan opens
`BRIDGE_LINK_URL` (default `udpin:0.0.0.0:14551`) and forwards normalized frames
to bounded per-client, per-topic WebSocket queues. State is returned as
`{"vehicles":{"<sysid>":{"<topic>":<frame>}}}`.

`schemas/telemetry_frame.json` is a bridge-local snapshot of the telemetry
envelope because `contracts/schemas/` is not populated. Regenerate the checked-in
Pydantic model with `make -C bridge generate-models`. The envelope `seq` starts
at zero and increments independently for each `(sysid, topic)` pair.
