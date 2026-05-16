"""
可配置的流水线日志（检索 / 嵌入 / RAG / LLM 等）。

环境变量：
- LOG_LEVEL：根日志级别，默认 INFO（DEBUG 时第三方库也更吵）。
- PIPELINE_LOG：0=关闭流水线专用日志；1=简要（INFO）；2=详细（DEBUG）。
- LOG_STAGES：可选，逗号分隔子阶段，只输出这些；留空或 all 表示不筛选。
  阶段名：retrieve, embed, rag, llm, review, scan, index, parse, translate, cache
"""

from __future__ import annotations

import logging
import re
from typing import Pattern

from app.config import settings

_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def setup_logging() -> None:
    """在应用启动时调用一次（见 main.py lifespan）。"""
    root = logging.getLogger()
    if not root.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(h)

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
