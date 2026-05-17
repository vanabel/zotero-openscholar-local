"""仅更新 chunks.embedding_json（EMBED_PROVIDER，超算常用 OpenAI 兼容 API），不改动 scholar 向量或分块。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from app.config import settings
from app.db import get_db
from app.pipeline_logging import plog_info
from app.services.llm import EmbeddingClient, embed_model_id


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_paper_ids_for_embed(*, missing_only: bool) -> list[str]:
    with get_db() as conn:
        if missing_only:
            sql = """
                SELECT DISTINCT c.paper_id AS paper_id
                FROM chunks c
                INNER JOIN papers p ON p.id = c.paper_id
                WHERE p.deleted = 0
                  AND (
                    c.embedding_json IS NULL
                    OR TRIM(c.embedding_json) = ''
                  )
                ORDER BY c.paper_id
            """
        else:
            sql = """
                SELECT DISTINCT c.paper_id AS paper_id
                FROM chunks c
                INNER JOIN papers p ON p.id = c.paper_id
                WHERE p.deleted = 0
                ORDER BY c.paper_id
            """
        return [str(r["paper_id"]) for r in conn.execute(sql).fetchall()]


def _load_chunk_rows(conn, paper_id: str, *, force: bool) -> list[dict]:
    sql = """
        SELECT id, text, embedding_json
        FROM chunks
        WHERE paper_id = ?
        ORDER BY chunk_index ASC
    """
    rows = [dict(r) for r in conn.execute(sql, (paper_id,)).fetchall()]
    if not force:
        rows = [
            r
            for r in rows
            if not r.get("embedding_json") or not str(r["embedding_json"]).strip()
        ]
    return rows


async def embed_vectors_for_paper(
    paper_id: str,
    *,
    force: bool = False,
    batch_size: int = 8,
) -> dict:
    if settings.resolved_embed_provider() != "openai":
        return {
            "ok": False,
            "paper_id": paper_id,
            "error": (
                "超算批处理需 EMBED_PROVIDER=openai 且配置 OPENAI_API_BASE/KEY；"
                f"当前解析为 {settings.resolved_embed_provider()}（{embed_model_id()}）"
            ),
        }
    if not settings.openai_ready():
        return {"ok": False, "paper_id": paper_id, "error": "未配置 OPENAI_API_BASE 与 OPENAI_API_KEY"}

    with get_db() as conn:
        rows = _load_chunk_rows(conn, paper_id, force=force)
        if not rows:
            total = conn.execute("SELECT COUNT(*) AS c FROM chunks WHERE paper_id = ?", (paper_id,)).fetchone()
            n = int(total["c"]) if total else 0
            if n == 0:
                return {
                    "ok": False,
                    "paper_id": paper_id,
                    "error": "该文献无 chunk，请先运行 chunk_batch 或建立索引",
                }
            return {
                "ok": True,
                "paper_id": paper_id,
                "chunks": 0,
                "updated": 0,
                "skipped": True,
                "message": "embedding_json 已齐全（使用 --force 可强制重算）",
            }

        client = EmbeddingClient()
        ids = [str(r["id"]) for r in rows]
        texts = [str(r["text"] or "") for r in rows]
        vectors: list[list[float] | None] = [None] * len(texts)
        try:
            for i in range(0, len(texts), batch_size):
                slice_t = texts[i : i + batch_size]
                vecs = await client.embed(slice_t)
                for j, v in enumerate(vecs):
                    vectors[i + j] = v
        except Exception as e:
            return {"ok": False, "paper_id": paper_id, "error": str(e)}

        now = _utc_now()
        updated = 0
        for cid, vec in zip(ids, vectors, strict=True):
            if vec is None:
                continue
            conn.execute(
                "UPDATE chunks SET embedding_json = ? WHERE id = ?",
                (json.dumps(vec, ensure_ascii=False), cid),
            )
            updated += 1
        conn.execute("UPDATE papers SET updated_at = ? WHERE id = ?", (now, paper_id))

    plog_info("index", "embed_batch paper_id=%s updated=%s model=%s", paper_id, updated, embed_model_id())
    return {
        "ok": True,
        "paper_id": paper_id,
        "chunks": len(ids),
        "updated": updated,
        "model": embed_model_id(),
    }


async def run_embed_batch(
    paper_ids: list[str],
    *,
    force: bool = False,
    batch_size: int = 8,
) -> dict:
    ok = fail = skip = 0
    errors: list[dict] = []
    for pid in paper_ids:
        res = await embed_vectors_for_paper(pid, force=force, batch_size=batch_size)
        if res.get("ok") and res.get("skipped"):
            skip += 1
        elif res.get("ok"):
            ok += 1
        else:
            fail += 1
            errors.append({"paper_id": pid, "error": res.get("error") or "失败"})
    return {
        "ok": fail == 0,
        "total": len(paper_ids),
        "succeeded": ok,
        "skipped": skip,
        "failed": fail,
        "errors": errors[:50],
    }
