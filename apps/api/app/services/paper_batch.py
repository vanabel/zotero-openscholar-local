"""批量筛选「缺解析 / 缺索引 / 缺摘要」的文献并提交任务队列。"""

from __future__ import annotations

from app.config import settings
from app.db import get_db
from app.services.pdf_parse import load_parsed_markdown


def list_parse_missing_ids(*, limit: int | None = None) -> list[str]:
    """无本地 document.md 的未删除文献（优先检查 parse_status != parsed 以减少磁盘 stat）。"""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id FROM papers
            WHERE deleted = 0 AND parse_status != 'parsed'
            ORDER BY updated_at DESC
            """
        ).fetchall()
    out: list[str] = []
    for r in rows:
        pid = str(r["id"])
        if load_parsed_markdown(settings.parsed_dir / pid) is None:
            out.append(pid)
            if limit is not None and len(out) >= limit:
                break
    return out


def list_index_missing_ids(*, limit: int | None = None, include_indexing: bool = False) -> list[str]:
    """index_status 非 indexed（可选含 indexing）。"""
    statuses = ("pending", "failed")
    if include_indexing:
        statuses = ("pending", "failed", "indexing")
    placeholders = ",".join("?" * len(statuses))
    sql = f"""
        SELECT id FROM papers
        WHERE deleted = 0 AND index_status IN ({placeholders})
        ORDER BY updated_at DESC
    """
    params: list[object] = list(statuses)
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [str(r["id"]) for r in rows]


def list_summarize_missing_ids(*, limit: int | None = None) -> list[str]:
    """已 indexed 但尚无 paper_summary。"""
    sql = """
        SELECT p.id FROM papers p
        WHERE p.deleted = 0 AND p.index_status = 'indexed'
          AND NOT EXISTS (
            SELECT 1 FROM summaries s
            WHERE s.paper_id = p.id AND s.summary_type = 'paper_summary'
          )
        ORDER BY p.updated_at DESC
    """
    params: list[object] = []
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [str(r["id"]) for r in rows]


def batch_enqueue_response(tasks: list[dict], *, matched: int) -> dict:
    errors = [t for t in tasks if t.get("error")]
    body: dict = {
        "ok": len(errors) == 0,
        "matched": matched,
        "queued": len(tasks) - len(errors),
        "failed": len(errors),
    }
    if len(tasks) <= 50:
        body["tasks"] = tasks
    else:
        body["tasks_sample"] = tasks[:5]
    return body


def count_index_missing(*, include_indexing: bool = False) -> int:
    """与 list_index_missing_ids 筛选一致的数量（仅计数，不返回 id）。"""
    statuses = ("pending", "failed")
    if include_indexing:
        statuses = ("pending", "failed", "indexing")
    ph = ",".join("?" * len(statuses))
    with get_db() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) AS c FROM papers WHERE deleted = 0 AND index_status IN ({ph})",
            list(statuses),
        ).fetchone()
    return int(row["c"] if row else 0)


def count_summarize_missing() -> int:
    """与 list_summarize_missing_ids 一致的数量。"""
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c FROM papers p
            WHERE p.deleted = 0 AND p.index_status = 'indexed'
              AND NOT EXISTS (
                SELECT 1 FROM summaries s
                WHERE s.paper_id = p.id AND s.summary_type = 'paper_summary'
              )
            """
        ).fetchone()
    return int(row["c"] if row else 0)


def get_batch_work_summary() -> dict:
    """
    文献库批量操作面板的待处理数量（与各 *-missing 入队逻辑一致）。
    parse_missing / unscored 需扫磁盘，文献极多时会稍慢。
    """
    from app.services.lance_store import (
        count_distinct_papers_in_lance_scholar,
        count_distinct_papers_with_scholar_embeddings,
        count_lance_scholar_sync_pending,
        lancedb_enabled,
    )
    from app.services.parse_rescore import list_unscored_with_markdown_ids

    return {
        "index_missing": count_index_missing(include_indexing=False),
        "index_missing_including_indexing": count_index_missing(include_indexing=True),
        "parse_missing": len(list_parse_missing_ids()),
        "summarize_missing": count_summarize_missing(),
        "unscored_with_markdown": len(list_unscored_with_markdown_ids()),
        # 主数字：尚未出现在 Lance 的「待同步」篇数（同步成功后会下降）
        "lance_scholar_papers": count_lance_scholar_sync_pending(),
        # SQLite 含 scholar 向量的文献总数（候选池，同步后不变）
        "lance_scholar_sqlite_with_vectors": count_distinct_papers_with_scholar_embeddings(),
        # Lance 表中已有向量的文献数（按 paper_id 去重）
        "lance_scholar_in_lance": count_distinct_papers_in_lance_scholar() if lancedb_enabled() else 0,
        "lancedb_enabled": lancedb_enabled(),
    }
