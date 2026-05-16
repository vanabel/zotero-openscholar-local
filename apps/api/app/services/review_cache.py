from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone

from app.config import settings
from app.db import get_db, json_dumps_safe
from app.pipeline_logging import plog_info
from app.services.chat_cache import config_fingerprint, corpus_fingerprint


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(s: str) -> str:
    return " ".join((s or "").strip().split())


def review_cache_key(topic: str, focus: str | None, lang: str) -> str:
    base = (
        f"{_normalize_text(topic)}\n"
        f"focus={_normalize_text(focus or '')}\n"
        f"lang={lang}\n"
        f"corpus={corpus_fingerprint()}\n"
        f"config={config_fingerprint()}"
    )
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _row_cache_valid(topic_norm: str, focus_norm: str, lang: str, row_key: str, created_at: str) -> bool:
    if review_cache_key(topic_norm, focus_norm or None, lang) != row_key:
        return False
    if settings.chat_cache_ttl_sec > 0:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - created).total_seconds()
        if age > settings.chat_cache_ttl_sec:
            return False
    return True


def list_recent_reviews(lang: str, *, limit: int = 10, pool: int = 80) -> list[dict]:
    if not settings.chat_cache_enabled or limit <= 0:
        return []
    lang = (lang or "zh").strip() or "zh"
    pool = max(limit, min(pool, 200))
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT topic_norm, focus_norm, lang, cache_key, created_at
            FROM review_cache
            WHERE lang = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (lang, pool),
        ).fetchall()
    valid: list[dict] = []
    for r in rows:
        topic = (r["topic_norm"] or "").strip()
        if not topic:
            continue
        focus_norm = (r["focus_norm"] or "").strip()
        if not _row_cache_valid(topic, focus_norm, lang, r["cache_key"], r["created_at"]):
            continue
        valid.append(
            {
                "topic": topic,
                "focus": focus_norm,
                "lang": lang,
                "has_cache": True,
                "created_at": r["created_at"],
            }
        )
    random.shuffle(valid)
    return valid[:limit]


def get_cached_review(topic: str, focus: str | None, lang: str) -> dict | None:
    if not settings.chat_cache_enabled:
        return None
    key = review_cache_key(topic, focus, lang)
    with get_db() as conn:
        row = conn.execute(
            "SELECT payload_json, created_at FROM review_cache WHERE cache_key = ?",
            (key,),
        ).fetchone()
    if not row:
        return None
    if settings.chat_cache_ttl_sec > 0:
        created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - created).total_seconds()
        if age > settings.chat_cache_ttl_sec:
            plog_info("cache", "review 缓存过期 key=%s age=%.0fs", key[:12], age)
            return None
    try:
        data = json.loads(row["payload_json"])
    except json.JSONDecodeError:
        return None
    plog_info("cache", "review 缓存命中 key=%s", key[:12])
    out = dict(data)
    out["cached"] = True
    return out


def put_cached_review(topic: str, focus: str | None, lang: str, payload: dict) -> None:
    if not settings.chat_cache_enabled:
        return
    key = review_cache_key(topic, focus, lang)
    store = {k: v for k, v in payload.items() if k != "cached"}
    now = _utc_now()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO review_cache(cache_key, topic_norm, focus_norm, lang, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
              payload_json = excluded.payload_json,
              created_at = excluded.created_at
            """,
            (
                key,
                _normalize_text(topic),
                _normalize_text(focus or ""),
                lang,
                json_dumps_safe(store),
                now,
            ),
        )
    plog_info("cache", "review 已写入缓存 key=%s", key[:12])


def stream_events_from_payload(payload: dict) -> list[dict]:
    events: list[dict] = [
        {
            "type": "citations",
            "citations": payload.get("citations") or [],
            "contexts_used": payload.get("contexts_used"),
            "cached": True,
        },
    ]
    review = payload.get("review") or ""
    if review:
        chunk = 120
        for i in range(0, len(review), chunk):
            events.append({"type": "token", "t": review[i : i + chunk]})
    events.append({"type": "done", "cached": True})
    return events
