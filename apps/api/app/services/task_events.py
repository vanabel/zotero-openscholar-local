"""任务进度 SSE 广播（内存 hub，单 API / Worker 进程内有效）。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

_subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
_lock = asyncio.Lock()


async def subscribe() -> asyncio.Queue[dict[str, Any]]:
    q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
    async with _lock:
        _subscribers.add(q)
    return q


async def unsubscribe(q: asyncio.Queue[dict[str, Any]]) -> None:
    async with _lock:
        _subscribers.discard(q)


def publish_task_event(event: dict[str, Any]) -> None:
    """同步调用；向所有 SSE 订阅者投递（队列满则丢弃）。"""
    if not _subscribers:
        return
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


async def sse_stream(
    *,
    initial: dict[str, Any] | None = None,
    heartbeat_sec: float = 20.0,
) -> AsyncIterator[str]:
    q = await subscribe()
    try:
        if initial is not None:
            yield _sse_line(initial)
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=heartbeat_sec)
                yield _sse_line(event)
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
    finally:
        await unsubscribe(q)


def _sse_line(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
