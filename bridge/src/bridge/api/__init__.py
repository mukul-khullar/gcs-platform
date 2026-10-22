"""FastAPI application and telemetry pipeline lifecycle."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from bridge.ingest import IngestedMessage, Ingestor
from bridge.ingest.link import DEFAULT_UDP_ENDPOINT, Link, open_udp_link
from bridge.normalize import Normalizer
from bridge.store import TelemetryStore

from .state import router as state_router
from .ws import TelemetryBroadcaster
from .ws import router as websocket_router

_INGEST_QUEUE_SIZE = 512


def create_app(*, link_factory: Callable[[], Link] | None = None) -> FastAPI:
    """Create the bridge API, optionally injecting a receive link for tests."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> Any:
        endpoint = os.environ.get("BRIDGE_LINK_URL", DEFAULT_UDP_ENDPOINT)
        link = link_factory() if link_factory is not None else open_udp_link(endpoint)
        queue: asyncio.Queue[IngestedMessage] = asyncio.Queue(
            maxsize=_INGEST_QUEUE_SIZE
        )
        ingestor = Ingestor(link, queue)
        normalizer = Normalizer()
        store = TelemetryStore()
        broadcaster = TelemetryBroadcaster()
        application.state.link = link
        application.state.ingestor = ingestor
        application.state.telemetry_store = store
        application.state.telemetry_broadcaster = broadcaster
        ingestor.start(asyncio.get_running_loop())
        consumer = asyncio.create_task(
            _consume_messages(queue, normalizer, store, broadcaster),
            name="telemetry-pipeline",
        )
        try:
            yield
        finally:
            try:
                ingestor.stop()
            finally:
                consumer.cancel()
                try:
                    await consumer
                except asyncio.CancelledError:
                    pass
                closer = getattr(link, "close", None)
                if callable(closer):
                    closer()

    application = FastAPI(title="MAVLink GCS Bridge", lifespan=lifespan)
    application.include_router(websocket_router)
    application.include_router(state_router)

    @application.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Return the bridge liveness status."""
        return {"status": "ok"}

    return application


async def _consume_messages(
    queue: asyncio.Queue[IngestedMessage],
    normalizer: Normalizer,
    store: TelemetryStore,
    broadcaster: TelemetryBroadcaster,
) -> None:
    while True:
        ingested = await queue.get()
        try:
            frame = normalizer.normalize(
                ingested.msg,
                t_wall_ms=ingested.t_wall_ms,
                now_s=asyncio.get_running_loop().time(),
            )
            store.ingest_mavlink(
                ingested.msg,
                sysid=ingested.sysid,
                t_wall_ms=ingested.t_wall_ms,
            )
            if frame is not None:
                store.ingest_frame(frame)
                broadcaster.publish(frame)
        finally:
            queue.task_done()


app = create_app()

__all__ = ["app", "create_app"]
