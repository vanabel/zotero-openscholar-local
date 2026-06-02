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


def count_distinct_papers_with_scholar_embeddings() -> int:
    """至少有一条 chunk 含非空 scholar 向量的文献数（SQLite 侧「具备写入 Lance 条件」的候选池）。"""
    from app.db import get_db

    with get_db() as conn:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT paper_id) AS c FROM chunks
            WHERE scholar_embedding_json IS NOT NULL AND TRIM(scholar_embedding_json) != ''
            """
        ).fetchone()
    return int(row["c"] if row else 0)


def distinct_paper_ids_in_lance_scholar() -> set[str]:
    """Lance `scholar_chunks` 表中已出现的文献 id（按 paper_id 去重）。"""
    if not lancedb_enabled():
        return set()
    db = _connect()
    if _TABLE not in db.table_names():
        return set()
    tbl = db.open_table(_TABLE)
    if tbl.count_rows() == 0:
        return set()
    import pyarrow.compute as pc

    arrow = tbl.to_arrow()
    if arrow.num_rows == 0 or "paper_id" not in arrow.column_names:
        return set()
    uni = pc.unique(arrow["paper_id"])
    return {str(x) for x in uni.to_pylist() if x is not None and str(x) != ""}


def count_distinct_papers_in_lance_scholar() -> int:
    """Lance 中至少有一条 scholar 向量行的文献数。"""
    return len(distinct_paper_ids_in_lance_scholar())


def count_lance_scholar_sync_pending() -> int:
    """
    SQLite 已有 scholar 向量、但 Lance 中尚无该 paper_id 的文献数。
    LanceDB 未启用时，视为全部尚未写入 Lance（与批量同步的「可处理」范围一致）。
    """
    if not lancedb_enabled():
        return count_distinct_papers_with_scholar_embeddings()
    lance_ids = distinct_paper_ids_in_lance_scholar()
    pending = 0
    from app.db import get_db

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT paper_id FROM chunks
            WHERE scholar_embedding_json IS NOT NULL AND TRIM(scholar_embedding_json) != ''
            """
        )
        for r in rows:
            if str(r["paper_id"]) not in lance_ids:
                pending += 1
    return pending


def list_lance_sync_pending_paper_ids(*, limit: int | None = None) -> list[str]:
    """
    与 count_lance_scholar_sync_pending 一致的文献 id 列表（用于 work_queue=lance_scholar）。
    LanceDB 未启用时返回全部「SQLite 含向量」的 id（与旧版 lance_scholar 列表行为一致）。
    """
    if not lancedb_enabled():
        return list_paper_ids_with_scholar_embeddings(limit=limit)
    lance_ids = distinct_paper_ids_in_lance_scholar()
    out: list[str] = []
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT paper_id FROM chunks
            WHERE scholar_embedding_json IS NOT NULL AND TRIM(scholar_embedding_json) != ''
            ORDER BY paper_id
            """
        ).fetchall()
    for r in rows:
        pid = str(r["paper_id"])
        if pid not in lance_ids:
            out.append(pid)
            if limit is not None and len(out) >= limit:
                break
    return out


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
