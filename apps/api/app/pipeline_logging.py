"""
可配置的流水线日志（检索 / 嵌入 / RAG / LLM 等）。

环境变量：
- LOG_LEVEL：根日志级别，默认 INFO（DEBUG 时第三方库也更吵）。
- PIPELINE_LOG：0=关闭流水线专用日志；1=简要（INFO）；2=详细（DEBUG）。
- LOG_STAGES：可选，逗号分隔子阶段，只输出这些；留空或 all 表示不筛选。
  阶段名：retrieve, embed, rag, llm, review, scan, index, parse, translate, cache
- LOG_CONTEXT：1（默认）时在每条日志前附加当前 task_id / paper_id（多任务并发时便于 grep）。
"""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator, Pattern

from app.config import settings

_paper_id: ContextVar[str | None] = ContextVar("pipeline_log_paper_id", default=None)
_task_id: ContextVar[str | None] = ContextVar("pipeline_log_task_id", default=None)

_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(log_ctx)s%(message)s"


class _PipelineContextFilter(logging.Filter):
    """从 contextvars 注入 log_ctx，便于多 worker / 多文献并发时按行区分。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.log_ctx = _format_log_ctx()  # type: ignore[attr-defined]
        return True


def _format_log_ctx() -> str:
    if not settings.log_context:
        return ""
    parts: list[str] = []
    pid = _paper_id.get()
    tid = _task_id.get()
    if tid:
        parts.append(f"task={tid[:8]}")
    if pid:
        parts.append(f"paper={pid[:8]}")
    if not parts:
        return ""
    return " ".join(parts) + " | "


@contextmanager
def log_context(
    *,
    paper_id: str | None = None,
    task_id: str | None = None,
) -> Iterator[None]:
    """在任务 / index_paper 作用域内设置日志上下文（asyncio 任务与 to_thread 会继承）。"""
    tokens: list[tuple[ContextVar[str | None], Token]] = []
    if paper_id is not None:
        tokens.append((_paper_id, _paper_id.set(paper_id)))
    if task_id is not None:
        tokens.append((_task_id, _task_id.set(task_id)))
    try:
        yield
    finally:
        for var, tok in reversed(tokens):
            var.reset(tok)


def setup_logging() -> None:
    """在应用启动时调用一次（见 main.py lifespan）。"""
    root = logging.getLogger()
    if not root.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter(_FORMAT))
        h.addFilter(_PipelineContextFilter())
        root.addHandler(h)
    else:
        for h in root.handlers:
            if not any(isinstance(f, _PipelineContextFilter) for f in h.filters):
                h.addFilter(_PipelineContextFilter())
            h.setFormatter(logging.Formatter(_FORMAT))

    level = getattr(logging, (settings.log_level or "INFO").upper(), logging.INFO)
    root.setLevel(level)

    for name in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.WARNING)

    pl = logging.getLogger("app.pipeline")
    if settings.pipeline_log <= 0:
        pl.setLevel(logging.CRITICAL + 1)
    elif settings.pipeline_log == 1:
        pl.setLevel(logging.INFO)
    else:
        pl.setLevel(logging.DEBUG)


def _allowed_stage(stage: str) -> bool:
    raw = (settings.log_stages or "").strip()
    if not raw or raw.lower() == "all":
        return True
    allowed = {x.strip().lower() for x in raw.split(",") if x.strip()}
    return stage.lower() in allowed


def _logger(stage: str) -> logging.Logger:
    return logging.getLogger(f"app.pipeline.{stage}")


def plog_info(stage: str, msg: str, *args) -> None:
    if settings.pipeline_log < 1 or not _allowed_stage(stage):
        return
    lg = _logger(stage)
    if args:
        lg.info(msg, *args)
    else:
        lg.info(msg)


def plog_debug(stage: str, msg: str, *args) -> None:
    if settings.pipeline_log < 2 or not _allowed_stage(stage):
        return
    lg = _logger(stage)
    if args:
        lg.debug(msg, *args)
    else:
        lg.debug(msg)


def clip(s: str, n: int = 240) -> str:
    s = s.replace("\n", " ")
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


_WS: Pattern[str] = re.compile(r"\s+")


def one_line(s: str, n: int = 200) -> str:
    return clip(_WS.sub(" ", s).strip(), n)
