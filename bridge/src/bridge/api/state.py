"""Latest telemetry snapshot endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from bridge.store import TelemetryStore

router = APIRouter()


@router.get("/api/v1/state")
async def latest_state(request: Request) -> dict[str, object]:
    """Return the latest frame for every topic, grouped by vehicle system ID."""
    store: TelemetryStore = request.app.state.telemetry_store
    vehicles: dict[str, dict[str, dict[str, object]]] = {}
    for (sysid, topic), frame in store.latest_values.items():
        vehicles.setdefault(str(sysid), {})[topic] = frame.model_dump(mode="json")
    return {"vehicles": vehicles}
