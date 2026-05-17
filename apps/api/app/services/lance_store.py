"""LanceDB 稠密向量索引（OpenScholar scholar_embedding）。"""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.pipeline_logging import plog_info

_TABLE = "scholar_chunks"


def lancedb_enabled() -> bool:
    if not settings.lancedb_enabled:
        return False
    try:
        import lancedb  # noqa: F401

        return True
    except ImportError:
        return False


def _connect():
    import lancedb

    return lancedb.connect(str(settings.lance_dir))


def _escape_id(pid: str) -> str:
    return pid.replace("'", "''")


def replace_paper_vectors(
    paper_id: str,
    chunk_ids: list[str],
    vectors: list[list[float] | None],
) -> None:
    if not lancedb_enabled():
        return
    rows = []
    for cid, vec in zip(chunk_ids, vectors, strict=True):
        if vec is None:
            continue
        rows.append({"chunk_id": cid, "paper_id": paper_id, "vector": [float(x) for x in vec]})
    db = _connect()
    if _TABLE in db.table_names():
        tbl = db.open_table(_TABLE)
        try:
            tbl.delete(f"paper_id = '{_escape_id(paper_id)}'")
        except Exception:
            pass
        if rows:
            tbl.add(rows)
    elif rows:
        db.create_table(_TABLE, rows)
    if rows:
        plog_info("lance", "写入 scholar 向量 paper_id=%s rows=%s", paper_id, len(rows))


def backfill_paper_vectors_from_db(paper_id: str) -> dict:
    """从 SQLite chunks.scholar_embedding_json 写入 Lance（不重新分块/嵌入）。"""
    if not lancedb_enabled():
        return {"ok": False, "error": "LanceDB 未启用或未安装 lancedb 包"}
    from app.db import get_db
    from app.services.openscholar_retrieval import parse_stored_embedding

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, scholar_embedding_json FROM chunks
            WHERE paper_id = ?
            ORDER BY chunk_index ASC
            """,
            (paper_id,),
        ).fetchall()
    chunk_ids: list[str] = []
    vectors: list[list[float]] = []
    for row in rows:
        vec = parse_stored_embedding(row["scholar_embedding_json"])
        if vec is None:
            continue
        chunk_ids.append(str(row["id"]))
        vectors.append(vec)
    if not chunk_ids:
        return {"ok": False, "error": "该文献尚无 OpenScholar 向量（请先建立索引且 Retriever 已开启）"}
    replace_paper_vectors(paper_id, chunk_ids, vectors)
    return {"ok": True, "paper_id": paper_id, "rows": len(chunk_ids)}


def backfill_lance_batch(paper_ids: list[str]) -> dict:
    synced = 0
    rows_total = 0
    errors: list[dict] = []
    for pid in paper_ids:
        res = backfill_paper_vectors_from_db(pid)
        if res.get("ok"):
            synced += 1
            rows_total += int(res.get("rows") or 0)
        else:
            errors.append({"paper_id": pid, "error": res.get("error") or "失败"})
    return {
        "ok": not errors,
        "matched": len(paper_ids),
        "synced": synced,
        "rows": rows_total,
        "failed": len(errors),
        "errors": errors[:20],
    }


def list_paper_ids_with_scholar_embeddings(*, limit: int | None = None) -> list[str]:
    from app.db import get_db

    sql = """
        SELECT DISTINCT paper_id FROM chunks
        WHERE scholar_embedding_json IS NOT NULL AND TRIM(scholar_embedding_json) != ''
        ORDER BY paper_id
    """
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    with get_db() as conn:
        return [str(r["paper_id"]) for r in conn.execute(sql).fetchall()]


def delete_paper_vectors(paper_id: str) -> None:
    if not lancedb_enabled():
        return
    db = _connect()
    if _TABLE not in db.table_names():
        return
    tbl = db.open_table(_TABLE)
    try:
        tbl.delete(f"paper_id = '{_escape_id(paper_id)}'")
    except Exception:
        pass


def search_scholar(
    query_vec: list[float],
    *,
    limit: int,
    allowed_paper_ids: set[str] | None = None,
) -> list[str] | None:
    """向量检索；失败或未安装时返回 None（调用方回退 SQLite 全表扫描）。"""
    if not lancedb_enabled():
        return None
    try:
        db = _connect()
        if _TABLE not in db.table_names():
            return None
        tbl = db.open_table(_TABLE)
        if tbl.count_rows() == 0:
            return None
        q = [float(x) for x in query_vec]
        builder = tbl.search(q).metric("cosine").limit(max(limit * 3, limit))
        if allowed_paper_ids is not None:
            if not allowed_paper_ids:
                return []
            ids_sql = ",".join(f"'{_escape_id(p)}'" for p in allowed_paper_ids)
            builder = builder.where(f"paper_id IN ({ids_sql})")
        hits = builder.to_list()
    except Exception as e:
        plog_info("lance", "检索失败，回退 SQLite: %s", e)
        return None

    out: list[str] = []
    for row in hits:
        cid = str(row.get("chunk_id") or "")
        if cid:
            out.append(cid)
        if len(out) >= limit:
            break
    if out:
        plog_info("lance", "dense 召回=%s limit=%s", len(out), limit)
    return out
