"""任务展示分类：index 任务按 payload 细分为 parse / reindex / index。"""

from __future__ import annotations

import json


def task_kind(*, task_type: str, payload_json: str | None = None, payload: dict | None = None) -> str:
    tt = (task_type or "index").strip()
    if tt != "index":
        return tt
    pl = payload
    if pl is None and payload_json:
        try:
            raw = json.loads(payload_json)
            pl = raw if isinstance(raw, dict) else None
        except json.JSONDecodeError:
            pl = None
    if pl:
        if pl.get("mineru_download_only"):
            return "mineru_download"
        if pl.get("parse_only"):
            return "parse"
        if pl.get("reindex_only"):
            return "reindex"
    return "index"


def task_kind_label(kind: str) -> str:
    return {
        "parse": "仅解析",
        "reindex": "仅重建索引",
        "index": "建立索引",
        "mineru_download": "重试 MinerU 下载",
        "summarize": "摘要",
    }.get(kind, kind)
