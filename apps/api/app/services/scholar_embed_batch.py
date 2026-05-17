"""仅更新 chunks.scholar_embedding_json（OpenScholar Retriever），不改动 embedding_json 或分块。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.db import get_db
from app.pipeline_logging import plog_info
from app.services.lance_store import backfill_paper_vectors_from_db, lancedb_enabled
from app.services.openscholar_retrieval import encode_passages, openscholar_retriever_enabled


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_paper_ids_for_scholar_embed(*, missing_only: bool) -> list[str]:
    """返回有 chunk 的文献 id；missing_only 时仅含至少一条缺 scholar 向量的文献。"""
    with get_db() as conn:
        if missing_only:
            sql = """
                SELECT DISTINCT c.paper_id AS paper_id
                FROM chunks c
                INNER JOIN papers p ON p.id = c.paper_id
                WHERE p.deleted = 0
                  AND (
                    c.scholar_embedding_json IS NULL
                    OR TRIM(c.scholar_embedding_json) = ''
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
        SELECT id, text, scholar_embedding_json
        FROM chunks
        WHERE paper_id = ?
        ORDER BY chunk_index ASC
    """
    rows = [dict(r) for r in conn.execute(sql, (paper_id,)).fetchall()]
    if not force:
        rows = [
            r
            for r in rows
            if not r.get("scholar_embedding_json") or not str(r["scholar_embedding_json"]).strip()
        ]
    return rows


def embed_scholar_for_paper(
    paper_id: str,
    *,
    force: bool = False,
    sync_lance: bool = True,
) -> dict:
    """对单篇文献的 chunk 计算 OpenScholar 向量并写回 SQLite（可选同步 Lance）。"""
    if not openscholar_retriever_enabled():
        return {"ok": False, "paper_id": paper_id, "error": "OpenScholar Retriever 未启用或依赖不可用"}

    with get_db() as conn:
        rows = _load_chunk_rows(conn, paper_id, force=force)
        if not rows:
            total = conn.execute("SELECT COUNT(*) AS c FROM chunks WHERE paper_id = ?", (paper_id,)).fetchone()
            n = int(total["c"]) if total else 0
            if n == 0:
                return {"ok": False, "paper_id": paper_id, "error": "该文献无 chunk，请先在本地建立索引"}
            return {
                "ok": True,
                "paper_id": paper_id,
                "chunks": 0,
                "updated": 0,
                "skipped": True,
                "message": "scholar 向量已齐全（使用 --force 可强制重算）",
            }

        texts = [str(r["text"] or "") for r in rows]
        ids = [str(r["id"]) for r in rows]
        try:
            vectors = encode_passages(texts)
        except Exception as e:
            return {"ok": False, "paper_id": paper_id, "error": str(e)}

        if len(vectors) != len(ids):
            return {
                "ok": False,
                "paper_id": paper_id,
                "error": f"向量条数不匹配: got {len(vectors)} expected {len(ids)}",
            }

        now = _utc_now()
        updated = 0
        for cid, vec in zip(ids, vectors, strict=True):
            if vec is None:
                continue
            conn.execute(
                "UPDATE chunks SET scholar_embedding_json = ? WHERE id = ?",
                (json.dumps(vec, ensure_ascii=False), cid),
            )
            updated += 1
        conn.execute("UPDATE papers SET updated_at = ? WHERE id = ?", (now, paper_id))

    lance_res: dict | None = None
    if sync_lance and lancedb_enabled() and updated > 0:
        lance_res = backfill_paper_vectors_from_db(paper_id)

    plog_info(
        "index",
        "scholar_embed_batch paper_id=%s updated=%s lance=%s",
        paper_id,
        updated,
        (lance_res or {}).get("ok"),
    )
    return {
        "ok": True,
        "paper_id": paper_id,
        "chunks": len(ids),
        "updated": updated,
        "lance": lance_res,
    }


def run_scholar_embed_batch(
    paper_ids: list[str],
    *,
    force: bool = False,
    sync_lance: bool = True,
) -> dict:
    ok = fail = skip = 0
    errors: list[dict] = []
    for pid in paper_ids:
        res = embed_scholar_for_paper(pid, force=force, sync_lance=sync_lance)
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
