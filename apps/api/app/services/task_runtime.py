"""任务运行时并发控制（MinerU 解析 / 嵌入批处理）。"""

from __future__ import annotations

import asyncio

from app.config import settings

_parse_sem: asyncio.Semaphore | None = None
_embed_sem: asyncio.Semaphore | None = None


def mineru_parse_semaphore() -> asyncio.Semaphore:
    global _parse_sem
    if _parse_sem is None:
        n = max(1, int(settings.mineru_parse_concurrency))
        _parse_sem = asyncio.Semaphore(n)
    return _parse_sem


def index_embed_semaphore() -> asyncio.Semaphore:
    global _embed_sem
    if _embed_sem is None:
        n = max(1, int(settings.index_embed_concurrency))
        _embed_sem = asyncio.Semaphore(n)
    return _embed_sem
