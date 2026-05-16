"""批量筛选「缺解析 / 缺索引 / 缺摘要」的文献并提交任务队列。"""

from __future__ import annotations

from app.config import settings
from app.db import get_db
from app.services.pdf_parse import load_parsed_markdown


def list_parse_missing_ids(*, limit: int | None = None) -> list[str]:
    """无本地 document.md 的未删除文献。"""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id FROM papers
            WHERE deleted = 0
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
