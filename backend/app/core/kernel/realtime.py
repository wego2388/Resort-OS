"""Distributed WebSocket fan-out backed by Redis pub/sub.

Uvicorn runs multiple worker processes in production. A process-local list of
WebSockets therefore cannot reliably deliver an event produced by an HTTP
request: the request and the connected tablet may live in different workers.
This manager keeps sockets local (they are not serializable) while using Redis
to fan each small event out to every worker that currently owns subscribers.

When Redis is not configured (local development) or briefly unavailable, the
manager falls back to same-process delivery. The underlying domain data stays
the source of truth, so clients can still reload after reconnecting.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
from contextlib import suppress
from typing import Any, Callable

from loguru import logger

RedisFactory = Callable[[], Any]


class DistributedWebSocketManager:
    """Keep WebSockets local and distribute their event stream through Redis."""

    def __init__(
        self,
        namespace: str,
        *,
        redis_url: str | None = None,
        redis_factory: RedisFactory | None = None,
    ) -> None:
        self.namespace = namespace
        self.active: dict[str, list[Any]] = {}
        self._listener_tasks: dict[str, asyncio.Task[None]] = {}
        self._listener_ready: dict[str, asyncio.Event] = {}

        resolved_url = os.getenv("REDIS_URL") if redis_url is None else redis_url
        if redis_factory is not None:
            self._redis_factory: RedisFactory | None = redis_factory
        elif resolved_url:
            from redis import asyncio as redis_asyncio

            self._redis_factory = lambda: redis_asyncio.from_url(
                resolved_url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=2,
                health_check_interval=30,
            )
        else:
            self._redis_factory = None

    def _channel(self, key: str) -> str:
        return f"resort-os:realtime:{self.namespace}:{key}"

    async def connect(self, websocket: Any, key: str) -> None:
        await websocket.accept()
        self.active.setdefault(key, []).append(websocket)
        await self._ensure_listener(key)

    def disconnect(self, websocket: Any, key: str) -> None:
        connections = self.active.get(key, [])
        if websocket in connections:
            connections.remove(websocket)
        if connections:
            return

        self.active.pop(key, None)
        self._listener_ready.pop(key, None)
        task = self._listener_tasks.pop(key, None)
        if task and not task.done():
            task.cancel()

    async def _ensure_listener(self, key: str) -> None:
        if self._redis_factory is None:
            return
        task = self._listener_tasks.get(key)
        if task is None or task.done():
            ready = asyncio.Event()
            self._listener_ready[key] = ready
            self._listener_tasks[key] = asyncio.create_task(self._listen(key, ready))
        else:
            ready = self._listener_ready[key]

        # Do not hold a WebSocket handshake indefinitely if Redis is down.
        # The listener keeps retrying and same-worker events still fall back.
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(ready.wait(), timeout=1.5)

    async def _listen(self, key: str, ready: asyncio.Event) -> None:
        backoff_seconds = 0.25
        while self.active.get(key):
            client = None
            pubsub = None
            try:
                client = self._redis_factory() if self._redis_factory else None
                if client is None:
                    return
                pubsub = client.pubsub()
                await pubsub.subscribe(self._channel(key))
                ready.set()
                backoff_seconds = 0.25

                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    payload = json.loads(message["data"])
                    if isinstance(payload, dict):
                        await self._send_local(key, payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Let connect() proceed with its local fallback, then retry so
                # a transient Redis restart does not require restarting Uvicorn.
                ready.set()
                logger.warning(
                    "[Realtime] Redis subscriber {}:{} unavailable: {}",
                    self.namespace,
                    key,
                    exc,
                )
                await asyncio.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, 5)
            finally:
                await self._close_resource(pubsub)
                await self._close_resource(client)

    async def broadcast(self, key: str, data: dict[str, Any]) -> None:
        if self._redis_factory is not None:
            client = None
            try:
                client = self._redis_factory()
                subscribers = await client.publish(
                    self._channel(key),
                    json.dumps(data, ensure_ascii=False, default=str),
                )
                # A zero count means no worker subscribed (or the local
                # listener is reconnecting). Preserve the former local behavior.
                if subscribers:
                    return
            except Exception as exc:
                logger.warning(
                    "[Realtime] Redis publisher {}:{} unavailable; using local fan-out: {}",
                    self.namespace,
                    key,
                    exc,
                )
            finally:
                await self._close_resource(client)

        await self._send_local(key, data)

    async def _send_local(self, key: str, data: dict[str, Any]) -> None:
        for websocket in list(self.active.get(key, [])):
            try:
                await websocket.send_json(data)
            except Exception:
                # The owning endpoint removes the socket in its disconnect
                # path. One broken tablet must not block the rest of the floor.
                continue

    async def shutdown(self) -> None:
        """Cancel Redis listeners; used by tests and graceful app shutdowns."""
        tasks = list(self._listener_tasks.values())
        self._listener_tasks.clear()
        self._listener_ready.clear()
        self.active.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    async def _close_resource(resource: Any) -> None:
        if resource is None:
            return
        closer = getattr(resource, "aclose", None) or getattr(resource, "close", None)
        if closer is None:
            return
        result = closer()
        if inspect.isawaitable(result):
            await result
