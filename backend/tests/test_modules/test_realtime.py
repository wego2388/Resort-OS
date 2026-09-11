from __future__ import annotations

import asyncio

import fakeredis
import pytest

from app.core.kernel.realtime import DistributedWebSocketManager


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.messages: list[dict] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: dict) -> None:
        self.messages.append(data)


@pytest.mark.asyncio
async def test_realtime_event_crosses_worker_managers_through_redis() -> None:
    server = fakeredis.FakeServer()

    def redis_factory():
        return fakeredis.FakeAsyncRedis(server=server, decode_responses=True)

    worker_one = DistributedWebSocketManager("dining-test", redis_factory=redis_factory)
    worker_two = DistributedWebSocketManager("dining-test", redis_factory=redis_factory)
    first_socket = FakeWebSocket()
    second_socket = FakeWebSocket()

    await worker_one.connect(first_socket, "tables-1")
    await worker_two.connect(second_socket, "tables-1")
    event = {"type": "guest_order_created", "order": {"id": 77}}
    await worker_one.broadcast("tables-1", event)

    for _ in range(20):
        if first_socket.messages and second_socket.messages:
            break
        await asyncio.sleep(0.01)

    assert first_socket.accepted and second_socket.accepted
    assert first_socket.messages == [event]
    assert second_socket.messages == [event]

    await worker_one.shutdown()
    await worker_two.shutdown()


@pytest.mark.asyncio
async def test_realtime_without_redis_keeps_local_development_delivery() -> None:
    manager = DistributedWebSocketManager("dining-test", redis_url="")
    websocket = FakeWebSocket()
    event = {"type": "tables_updated"}

    await manager.connect(websocket, "tables-1")
    await manager.broadcast("tables-1", event)

    assert websocket.accepted
    assert websocket.messages == [event]
    await manager.shutdown()
