from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone

from app.config import settings
from app.db import get_db, json_dumps_safe
from app.pipeline_logging import plog_info
from app.services.llm import chat_model_id, embed_model_id
from app.services.translation import (
    translation_for_answer_enabled,
    translation_for_retrieval_enabled,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_question(q: str) -> str:
    return " ".join(q.strip().split())


def corpus_fingerprint() -> str:
    """索引库变更（扫描/建索引）后指纹变化，旧缓存自动失效。"""
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM papers WHERE deleted = 0 AND index_status = 'indexed') AS indexed,
              (SELECT COUNT(*) FROM chunks ch
                 JOIN papers p ON p.id = ch.paper_id AND p.deleted = 0) AS chunks,
              (SELECT COALESCE(MAX(updated_at), '') FROM papers WHERE deleted = 0) AS max_upd
            """
        ).fetchone()
    if not row:
        return "0:0:"
    return f"{row['indexed']}:{row['chunks']}:{row['max_upd']}"


def config_fingerprint() -> str:
    parts = [
        chat_model_id(),
        embed_model_id(),
        f"cp={settings.chat_provider}",
        f"ep={settings.embed_provider}",
        f"br={int(settings.bilingual_retrieval)}",
        f"ba={int(settings.bilingual_answer)}",
        f"rk={settings.retrieve_top_k_fts}:{settings.retrieve_top_k_final}",
        f"osr={int(settings.openscholar_retriever_enabled)}:{settings.openscholar_retriever_model}",
        f"osk={int(settings.openscholar_reranker_enabled)}:{settings.openscholar_reranker_model}",
        settings.translation_ollama_model.strip() or "-",
    ]
    return "|".join(parts)


def cache_key(question: str, lang: str) -> str:
    base = f"{_normalize_question(question)}\nlang={lang}\ncorpus={corpus_fingerprint()}\nconfig={config_fingerprint()}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _row_cache_valid(question_norm: str, lang: str, row_key: str, created_at: str) -> bool:
    if cache_key(question_norm, lang) != row_key:
        return False
    if settings.chat_cache_ttl_sec > 0:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - created).total_seconds()
        if age > settings.chat_cache_ttl_sec:
            return False
    return True


def list_recent_questions(lang: str, *, limit: int = 10, pool: int = 80) -> list[dict]:
    """返回近期提问（随机顺序），仅含当前仍有效的缓存条目。"""
    if not settings.chat_cache_enabled or limit <= 0:
        return []
    lang = (lang or "zh").strip() or "zh"
    pool = max(limit, min(pool, 200))
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT question_norm, lang, cache_key, created_at
            FROM chat_cache
            WHERE lang = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (lang, pool),
        ).fetchall()
    valid: list[dict] = []
    for r in rows:
        q = (r["question_norm"] or "").strip()
        if not q:
            continue
        if not _row_cache_valid(q, lang, r["cache_key"], r["created_at"]):
            continue
        valid.append(
            {
                "question": q,
                "lang": lang,
                "has_cache": True,
                "created_at": r["created_at"],
            }
        )
    random.shuffle(valid)
    return valid[:limit]


def get_cached_answer(question: str, lang: str) -> dict | None:
    if not settings.chat_cache_enabled:
        return None
    key = cache_key(question, lang)
    with get_db() as conn:
        row = conn.execute(
            "SELECT payload_json, created_at FROM chat_cache WHERE cache_key = ?",
            (key,),
        ).fetchone()
    if not row:
        return None
    if settings.chat_cache_ttl_sec > 0:
        created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - created).total_seconds()
        if age > settings.chat_cache_ttl_sec:
            plog_info("cache", "chat 缓存过期 key=%s age=%.0fs", key[:12], age)
            return None
    try:
        data = json.loads(row["payload_json"])
    except json.JSONDecodeError:
        return None
    plog_info("cache", "chat 缓存命中 key=%s", key[:12])
    out = dict(data)
    out["cached"] = True
    return out


def clear_cached_translation(question: str, lang: str) -> bool:
    """从问答缓存中移除译文（answer_other），保留主答与引用。返回是否更新了条目。"""
    if not settings.chat_cache_enabled:
        return False
    hit = get_cached_answer(question, lang)
    if hit is None:
        return False
    if not hit.get("answer_other"):
        return False
    store = {k: v for k, v in hit.items() if k not in ("cached", "answer_other", "answer_other_lang")}
    put_cached_answer(question, lang, store)
    plog_info("cache", "chat 已清除缓存译文 key=%s", cache_key(question, lang)[:12])
    return True


def put_cached_answer(question: str, lang: str, payload: dict) -> None:
    if not settings.chat_cache_enabled:
        return
    key = cache_key(question, lang)
    store = {k: v for k, v in payload.items() if k != "cached"}
    now = _utc_now()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO chat_cache(cache_key, question_norm, lang, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
              payload_json = excluded.payload_json,
              created_at = excluded.created_at
            """,
            (key, _normalize_question(question), lang, json_dumps_safe(store), now),
        )
    plog_info("cache", "chat 已写入缓存 key=%s", key[:12])


def stream_events_from_payload(payload: dict) -> list[dict]:
    """将完整回答重放为 SSE 事件序列。"""
    events: list[dict] = [
        {
            "type": "citations",
            "citations": payload.get("citations") or [],
            "contexts_used": payload.get("contexts_used"),
            "cached": True,
        },
    ]
    answer = payload.get("answer") or ""
    if answer:
        chunk = 120
        for i in range(0, len(answer), chunk):
            events.append({"type": "token", "t": answer[i : i + chunk]})
    alt = payload.get("answer_other")
    alt_lang = payload.get("answer_other_lang")
    if alt and alt_lang in ("zh", "en"):
        events.append({"type": "bilingual_start", "lang": alt_lang})
        chunk = 80
        for i in range(0, len(alt), chunk):
            events.append({"type": "bilingual_token", "lang": alt_lang, "t": alt[i : i + chunk]})
        events.append({"type": "bilingual", "lang": alt_lang, "text": alt})
    events.append({"type": "done", "cached": True})
    return events
