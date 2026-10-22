"""WebSocket telemetry fan-out with bounded per-client topic queues."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from bridge.models import FrameModel, Topic

router = APIRouter()
_CLIENT_QUEUE_SIZE = 1


class ClientSubscription:
    """One client with an independent latest-value queue for each topic."""

    def __init__(self, client_id: UUID) -> None:
        self.client_id = client_id
        self.queues: dict[str, asyncio.Queue[dict[str, Any]]] = {
            topic.value: asyncio.Queue(maxsize=_CLIENT_QUEUE_SIZE) for topic in Topic
        }
        self.controls: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=8)
        self.dropped_count = 0

    def offer(self, frame: dict[str, Any]) -> None:
        topic = str(frame["type"])
        queue = self.queues[topic]
        if queue.full():
            queue.get_nowait()
            queue.task_done()
            self.dropped_count += 1
        queue.put_nowait(frame)

    def offer_control(self, message: dict[str, Any]) -> None:
        if self.controls.full():
            self.controls.get_nowait()
            self.controls.task_done()
        self.controls.put_nowait(message)

    @property
    def queue_sizes(self) -> dict[str, int]:
        return {topic: queue.qsize() for topic, queue in self.queues.items()}


class TelemetryBroadcaster:
    """Fan out contract frames without allowing slow clients to build backlog."""

    def __init__(self) -> None:
        self._clients: dict[UUID, ClientSubscription] = {}

    def subscribe(self) -> ClientSubscription:
        """Register a new client and return its independent bounded queues."""
        client = ClientSubscription(uuid4())
        self._clients[client.client_id] = client
        return client

    def unsubscribe(self, client_id: UUID) -> None:
        """Remove a disconnected client."""
        self._clients.pop(client_id, None)

    def publish(self, frame: FrameModel) -> None:
        """Publish one normalized frame to every connected client."""
        payload = frame.model_dump(mode="json")
        for client in tuple(self._clients.values()):
            client.offer(payload)

    @property
    def client_queue_sizes(self) -> dict[UUID, dict[str, int]]:
        """Expose bounded queue sizes for diagnostics and lifecycle tests."""
        return {
            client_id: client.queue_sizes for client_id, client in self._clients.items()
        }

    @property
    def client_count(self) -> int:
        """Return the number of active client subscriptions."""
        return len(self._clients)


@router.websocket("/ws/telemetry")
async def telemetry_websocket(websocket: WebSocket) -> None:
    """Stream versioned telemetry envelopes and respond to application pings."""
    await websocket.accept()
    broadcaster: TelemetryBroadcaster = websocket.app.state.telemetry_broadcaster
    client = broadcaster.subscribe()
    sender = asyncio.create_task(_send_to_client(websocket, client))
    try:
        while True:
            message = await websocket.receive_text()
            if _is_ping(message):
                client.offer_control({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        broadcaster.unsubscribe(client.client_id)
        sender.cancel()
        try:
            await sender
        except asyncio.CancelledError:
            pass


async def _send_to_client(websocket: WebSocket, client: ClientSubscription) -> None:
    while True:
        waiters = {
            asyncio.create_task(queue.get()): queue
            for queue in (*client.queues.values(), client.controls)
        }
        try:
            done, _ = await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
        finally:
            pending = [task for task in waiters if not task.done()]
            for task in pending:
                task.cancel()
            await asyncio.gather(*waiters, return_exceptions=True)

        for task in done:
            queue = waiters[task]
            payload = task.result()
            queue.task_done()
            await websocket.send_json(payload)


def _is_ping(message: str) -> bool:
    if message == "ping":
        return True
    try:
        payload: Any = json.loads(message)
    except json.JSONDecodeError:
        return False
    return isinstance(payload, Mapping) and payload.get("type") == "ping"
