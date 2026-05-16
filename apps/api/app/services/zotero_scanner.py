from __future__ import annotations

import hashlib
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


def _papers_where_clause(q: str | None, include_deleted: bool) -> tuple[str, list]:
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
    where = " AND ".join(clauses) if clauses else "1=1"
    return where, params


def _reconcile_paper_status_with_disk(conn, items: list[dict]) -> None:
    """
    根据 data/parsed/{id}/document.md 与 chunks 表校准 parse_status / index_status，
    修复「已解析/已索引但 DB 仍为 pending」导致重启后文献库状态不对的问题。
    """
    if not items:
        return
    rows = conn.execute("SELECT paper_id, COUNT(*) AS c FROM chunks GROUP BY paper_id").fetchall()
    chunk_map = {str(r["paper_id"]): int(r["c"]) for r in rows}
    parsed_root = settings.parsed_dir
    now = _utc_now()
    for item in items:
        pid = item["id"]
        doc = parsed_root / pid / "document.md"
        try:
            has_md = doc.is_file() and doc.stat().st_size >= 100
        except OSError:
            has_md = False
        nch = chunk_map.get(pid, 0)
        ps = item.get("parse_status") or "pending"
        ix = item.get("index_status") or "pending"
        new_ps, new_ix = ps, ix
        if has_md and ps != "parsed":
            new_ps = "parsed"
        if nch > 0 and ix != "indexed":
            new_ix = "indexed"
        if new_ps != ps or new_ix != ix:
            conn.execute(
                "UPDATE papers SET parse_status = ?, index_status = ?, updated_at = ? WHERE id = ?",
                (new_ps, new_ix, now, pid),
            )
            item["parse_status"] = new_ps
            item["index_status"] = new_ix


def list_papers(
    limit: int = 500,
    offset: int = 0,
    include_deleted: bool = False,
    q: str | None = None,
) -> list[dict]:
    where, params = _papers_where_clause(q, include_deleted)
    with get_db() as conn:
        sql = f"SELECT * FROM papers WHERE {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        rows = conn.execute(sql, (*params, limit, offset)).fetchall()
        items = [dict(r) for r in rows]
        _reconcile_paper_status_with_disk(conn, items)
        return items


def count_papers(include_deleted: bool = False, q: str | None = None) -> int:
    where, params = _papers_where_clause(q, include_deleted)
    with get_db() as conn:
        row = conn.execute(f"SELECT COUNT(*) AS c FROM papers WHERE {where}", params).fetchone()
        return int(row["c"]) if row else 0


def get_paper(paper_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        _reconcile_paper_status_with_disk(conn, [d])
        return d
