from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.db import get_db, get_zotero_storage_path
from app.pipeline_logging import plog_info
from app.services.pdf_parse import sha256_file


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def paper_id_for_path(pdf_path: Path) -> str:
    return hashlib.sha256(str(pdf_path.resolve()).encode("utf-8")).hexdigest()[:32]


def scan_storage() -> dict:
    root = get_zotero_storage_path()
    plog_info("scan", "scan_storage 开始 root=%s", root)
    if not root.exists():
        return {"root": str(root), "found": 0, "error": "路径不存在"}

    # Zotero 存储里可能出现名为 *.pdf 的目录（例如误建或同步残留），必须只处理常规文件。
    pdfs_raw: list[Path] = sorted(root.rglob("*.pdf"))
    pdfs: list[Path] = [p for p in pdfs_raw if p.is_file()]
    skipped_non_file = len(pdfs_raw) - len(pdfs)
    now = _utc_now()
    inserted = 0
    updated = 0
    seen_paths: set[str] = set()

    with get_db() as conn:
        for pdf in pdfs:
            try:
                st = pdf.stat()
            except OSError:
                continue
            path_s = str(pdf.resolve())
            seen_paths.add(path_s)
            pid = paper_id_for_path(pdf)
            sha = sha256_file(pdf)
            row = conn.execute("SELECT id, sha256, file_size, mtime, deleted FROM papers WHERE pdf_path = ?", (path_s,)).fetchone()

            if row is None:
                conn.execute(
                    """
                    INSERT INTO papers(
                      id, pdf_path, file_name, file_size, mtime, sha256,
                      parse_status, index_status, deleted, created_at, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        pid,
                        path_s,
                        pdf.name,
                        st.st_size,
                        st.st_mtime,
                        sha,
                        "pending",
                        "pending",
                        0,
                        now,
                        now,
                    ),
                )
                inserted += 1
                continue

            old_sha = row["sha256"]
            old_size = row["file_size"]
            old_mtime = row["mtime"]
            needs_update = (st.st_size != old_size) or (st.st_mtime != old_mtime)
            if needs_update:
                new_sha = sha256_file(pdf)
                if new_sha != old_sha:
                    conn.execute(
                        """
                        UPDATE papers SET
                          sha256=?, file_size=?, mtime=?, deleted=0,
                          parse_status='pending', index_status='pending',
                          md_sha256=NULL, updated_at=?
                        WHERE id=?
                        """,
                        (new_sha, st.st_size, st.st_mtime, now, row["id"]),
                    )
                    updated += 1
                else:
                    conn.execute(
                        "UPDATE papers SET file_size=?, mtime=?, deleted=0, updated_at=? WHERE id=?",
                        (st.st_size, st.st_mtime, now, row["id"]),
                    )
            else:
                if row["deleted"]:
                    conn.execute(
                        "UPDATE papers SET deleted=0, updated_at=? WHERE id=?",
                        (now, row["id"]),
                    )

        # 标记删除：数据库有而磁盘无
        rows = conn.execute("SELECT id, pdf_path FROM papers WHERE deleted = 0").fetchall()
        for r in rows:
            p = r["pdf_path"]
            if p not in seen_paths:
                conn.execute(
                    "UPDATE papers SET deleted=1, updated_at=? WHERE id=?",
                    (now, r["id"]),
                )

    out = {
        "root": str(root),
        "found": len(pdfs),
        "skipped_non_file": skipped_non_file,
        "inserted": inserted,
        "updated": updated,
    }
    plog_info(
        "scan",
        "scan_storage 完成 found=%s skipped_non_file=%s inserted=%s updated=%s",
        out["found"],
        out["skipped_non_file"],
        out["inserted"],
        out["updated"],
    )

    try:
        from app.services.zotero_sqlite_sync import sync_zotero_metadata_to_papers

        zmeta = sync_zotero_metadata_to_papers(include_deleted=False)
        out["zotero_metadata"] = zmeta
    except Exception as e:
        plog_info("scan", "zotero 元数据同步异常（已忽略）: %s", e)
        out["zotero_metadata"] = {"ok": False, "error": str(e)}

    return out


def _papers_where_clause(
    q: str | None,
    include_deleted: bool,
    *,
    parse_quality_lte: float | None = None,
    parse_quality_gte: float | None = None,
    parse_quality_missing: bool = False,
) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if not include_deleted:
        clauses.append("deleted = 0")
    term = (q or "").strip()
    if term:
        like = f"%{term}%"
        clauses.append(
            "(COALESCE(title, '') LIKE ? OR COALESCE(file_name, '') LIKE ? "
            "OR pdf_path LIKE ? OR COALESCE(authors, '') LIKE ? "
            "OR COALESCE(zotero_tags, '') LIKE ? OR COALESCE(zotero_collections, '') LIKE ?)"
        )
        params.extend([like, like, like, like, like, like])
    if parse_quality_missing:
        clauses.append("parse_quality_score IS NULL")
    else:
        if parse_quality_lte is not None:
            clauses.append("parse_quality_score IS NOT NULL AND parse_quality_score <= ?")
            params.append(parse_quality_lte)
        if parse_quality_gte is not None:
            clauses.append("parse_quality_score IS NOT NULL AND parse_quality_score >= ?")
            params.append(parse_quality_gte)
    where = " AND ".join(clauses) if clauses else "1=1"
    return where, params


WORK_QUEUE_VALUES = frozenset(
    {
        "index_missing",
        "parse_missing",
        "summarize_missing",
        "unscored_rescore",
        "lance_scholar",
    }
)


def _work_queue_extra_clauses(work_queue: str | None) -> tuple[list[str], list]:
    """
    与 batch-work-summary / *-missing 入队范围一致的附加筛选。
    基于 id 列表的队列使用 json_each，避免超长 IN 列表。
    """
    if not work_queue:
        return [], []
    if work_queue not in WORK_QUEUE_VALUES:
        raise ValueError(f"invalid work_queue: {work_queue!r}")
    if work_queue == "index_missing":
        return ["index_status IN ('pending', 'failed')"], []
    if work_queue == "summarize_missing":
        return [
            "index_status = 'indexed'",
            "NOT EXISTS (SELECT 1 FROM summaries s WHERE s.paper_id = papers.id AND s.summary_type = 'paper_summary')",
        ], []
    if work_queue == "lance_scholar":
        from app.services.lance_store import list_lance_sync_pending_paper_ids

        ids = list_lance_sync_pending_paper_ids(limit=None)
        if not ids:
            return ["1=0"], []
        return ["id IN (SELECT value FROM json_each(?))"], [json.dumps(ids)]
    if work_queue == "parse_missing":
        from app.services.paper_batch import list_parse_missing_ids

        ids = list_parse_missing_ids(limit=None)
    elif work_queue == "unscored_rescore":
        from app.services.parse_rescore import list_unscored_with_markdown_ids

        ids = list_unscored_with_markdown_ids(limit=None)
    else:
        return [], []
    if not ids:
        return ["1=0"], []
    return ["id IN (SELECT value FROM json_each(?))"], [json.dumps(ids)]


def _papers_where_with_work_queue(
    q: str | None,
    include_deleted: bool,
    *,
    parse_quality_lte: float | None = None,
    parse_quality_gte: float | None = None,
    parse_quality_missing: bool = False,
    work_queue: str | None = None,
) -> tuple[str, list]:
    base_where, base_params = _papers_where_clause(
        q,
        include_deleted,
        parse_quality_lte=parse_quality_lte,
        parse_quality_gte=parse_quality_gte,
        parse_quality_missing=parse_quality_missing,
    )
    w_clauses, w_params = _work_queue_extra_clauses(work_queue)
    if not w_clauses:
        return base_where, base_params
    return f"({base_where}) AND ({' AND '.join(w_clauses)})", [*base_params, *w_params]


def _reconcile_paper_status_with_disk(conn, items: list[dict]) -> None:
    from app.services.index_reconcile import reconcile_papers_with_disk

    reconcile_papers_with_disk(conn, items)


def _attach_paper_summary_flags(conn, items: list[dict]) -> None:
    if not items:
        return
    ids = [i["id"] for i in items]
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        f"""
        SELECT DISTINCT paper_id FROM summaries
        WHERE summary_type = 'paper_summary' AND paper_id IN ({placeholders})
        """,
        ids,
    ).fetchall()
    has = {r["paper_id"] for r in rows}
    for item in items:
        item["has_paper_summary"] = item["id"] in has


def list_papers(
    limit: int = 500,
    offset: int = 0,
    include_deleted: bool = False,
    q: str | None = None,
    *,
    parse_quality_lte: float | None = None,
    parse_quality_gte: float | None = None,
    parse_quality_missing: bool = False,
    sort: str = "updated",
    work_queue: str | None = None,
    reconcile: bool = False,
) -> list[dict]:
    where, params = _papers_where_with_work_queue(
        q,
        include_deleted,
        parse_quality_lte=parse_quality_lte,
        parse_quality_gte=parse_quality_gte,
        parse_quality_missing=parse_quality_missing,
        work_queue=work_queue,
    )
    order = "updated_at DESC"
    if sort == "quality_asc":
        order = "parse_quality_score IS NULL, parse_quality_score ASC, updated_at DESC"
    elif sort == "quality_desc":
        order = "parse_quality_score IS NULL, parse_quality_score DESC, updated_at DESC"
    with get_db() as conn:
        sql = f"SELECT * FROM papers WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?"
        rows = conn.execute(sql, (*params, limit, offset)).fetchall()
        items = [dict(r) for r in rows]
        if reconcile:
            _reconcile_paper_status_with_disk(conn, items)
        _attach_paper_summary_flags(conn, items)
        return items


def count_papers(
    include_deleted: bool = False,
    q: str | None = None,
    *,
    parse_quality_lte: float | None = None,
    parse_quality_gte: float | None = None,
    parse_quality_missing: bool = False,
    work_queue: str | None = None,
) -> int:
    where, params = _papers_where_with_work_queue(
        q,
        include_deleted,
        parse_quality_lte=parse_quality_lte,
        parse_quality_gte=parse_quality_gte,
        parse_quality_missing=parse_quality_missing,
        work_queue=work_queue,
    )
    with get_db() as conn:
        row = conn.execute(f"SELECT COUNT(*) AS c FROM papers WHERE {where}", params).fetchone()
        return int(row["c"]) if row else 0


def parse_quality_summary(include_deleted: bool = False) -> dict:
    """全库解析质量分布（用于文献库筛选摘要）。"""
    del_clause = "" if include_deleted else "WHERE deleted = 0"
    with get_db() as conn:
        row = conn.execute(
            f"""
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN parse_quality_score IS NULL THEN 1 ELSE 0 END) AS unscored,
              SUM(CASE WHEN parse_quality_score IS NOT NULL AND parse_quality_score < 0.65 THEN 1 ELSE 0 END) AS low,
              SUM(CASE WHEN parse_quality_score IS NOT NULL AND parse_quality_score >= 0.85 THEN 1 ELSE 0 END) AS high
            FROM papers {del_clause}
            """
        ).fetchone()
    return {
        "total": int(row["total"] or 0),
        "unscored": int(row["unscored"] or 0),
        "low_quality": int(row["low"] or 0),
        "high_quality": int(row["high"] or 0),
        "low_quality_threshold": 0.65,
    }


def get_paper(paper_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        _reconcile_paper_status_with_disk(conn, [d])
        return d
