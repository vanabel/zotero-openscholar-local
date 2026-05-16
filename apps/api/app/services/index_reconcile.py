"""根据磁盘 Markdown 与 chunks/FTS 表校准文献 parse/index 状态，并清理孤儿 FTS。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.db import get_db

_MIN_MD_BYTES = 100


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def paper_has_parsed_markdown(paper_id: str, *, parsed_root: Path | None = None) -> bool:
    root = parsed_root or settings.parsed_dir
    doc = root / paper_id / "document.md"
    try:
        return doc.is_file() and doc.stat().st_size >= _MIN_MD_BYTES
    except OSError:
        return False


def _count_by_paper(conn, table: str, id_col: str) -> dict[str, int]:
    rows = conn.execute(f"SELECT {id_col} AS paper_id, COUNT(*) AS c FROM {table} GROUP BY {id_col}").fetchall()
    return {str(r["paper_id"]): int(r["c"]) for r in rows}


def prune_orphan_chunks_fts(conn, paper_ids: Iterable[str] | None = None) -> int:
    """
    删除 chunks 表中不存在的 chunk_id 对应的 FTS 行。
    paper_ids 为 None 时清理全库；否则仅处理指定文献。
    """
    if paper_ids is None:
        cur = conn.execute(
            "DELETE FROM chunks_fts WHERE chunk_id NOT IN (SELECT id FROM chunks)"
        )
        return int(cur.rowcount)

    removed = 0
    for pid in paper_ids:
        cur = conn.execute(
            """
            DELETE FROM chunks_fts
            WHERE paper_id = ?
              AND chunk_id NOT IN (SELECT id FROM chunks WHERE paper_id = ?)
            """,
            (pid, pid),
        )
        removed += int(cur.rowcount)
    return removed


def reconcile_paper_item(
    conn,
    item: dict,
    *,
    chunk_map: dict[str, int],
    fts_map: dict[str, int],
    parsed_root: Path | None = None,
) -> tuple[str, str, bool]:
    """
    返回 (new_parse_status, new_index_status, fts_pruned)。
    仅以 chunks 行数判定 indexed；FTS 无对应 chunk 时只清理、不提升状态。
    """
    pid = item["id"]
    has_md = paper_has_parsed_markdown(pid, parsed_root=parsed_root)
    nch = chunk_map.get(pid, 0)
    nft = fts_map.get(pid, 0)
    fts_pruned = False

    if nch == 0 and nft > 0:
        cur = conn.execute(
            """
            DELETE FROM chunks_fts
            WHERE paper_id = ?
              AND chunk_id NOT IN (SELECT id FROM chunks WHERE paper_id = ?)
            """,
            (pid, pid),
        )
        fts_pruned = int(cur.rowcount) > 0
        if fts_pruned:
            fts_map[pid] = 0

    ps = item.get("parse_status") or "pending"
    ix = item.get("index_status") or "pending"
    new_ps, new_ix = ps, ix

    if has_md and ps != "parsed":
        new_ps = "parsed"

    if nch > 0:
        if ix != "indexed":
            new_ix = "indexed"
    elif ix in ("indexed", "indexing"):
        new_ix = "pending"

    return new_ps, new_ix, fts_pruned


def reconcile_papers_with_disk(conn, items: list[dict]) -> int:
    """校准列表中的文献状态；返回实际 UPDATE 的行数。"""
    if not items:
        return 0
    chunk_map = _count_by_paper(conn, "chunks", "paper_id")
    fts_map = _count_by_paper(conn, "chunks_fts", "paper_id")
    parsed_root = settings.parsed_dir
    now = _utc_now()
    updated = 0
    for item in items:
        new_ps, new_ix, _ = reconcile_paper_item(
            conn,
            item,
            chunk_map=chunk_map,
            fts_map=fts_map,
            parsed_root=parsed_root,
        )
        ps = item.get("parse_status") or "pending"
        ix = item.get("index_status") or "pending"
        if new_ps != ps or new_ix != ix:
            conn.execute(
                "UPDATE papers SET parse_status = ?, index_status = ?, updated_at = ? WHERE id = ?",
                (new_ps, new_ix, now, item["id"]),
            )
            item["parse_status"] = new_ps
            item["index_status"] = new_ix
            updated += 1
    return updated


def batch_reconcile_parse_from_disk(conn) -> int:
    """将 parsed 目录下已有 document.md 的文献标为 parsed（批量，用于启动）。"""
    root = settings.parsed_dir
    if not root.is_dir():
        return 0
    ids: list[str] = []
    for d in root.iterdir():
        if not d.is_dir():
            continue
        doc = d / "document.md"
        try:
            if doc.is_file() and doc.stat().st_size >= _MIN_MD_BYTES:
                ids.append(d.name)
        except OSError:
            continue
    if not ids:
        return 0
    placeholders = ",".join("?" * len(ids))
    now = _utc_now()
    cur = conn.execute(
        f"""
        UPDATE papers SET parse_status = 'parsed', updated_at = ?
        WHERE deleted = 0 AND parse_status != 'parsed' AND id IN ({placeholders})
        """,
        (now, *ids),
    )
    return int(cur.rowcount)


def reconcile_database_on_startup() -> dict:
    """
    启动时：清理孤儿 FTS、批量修正 index/parse 与 chunks/磁盘不一致。
    """
    from app.pipeline_logging import plog_info

    now = _utc_now()
    with get_db() as conn:
        fts_removed = prune_orphan_chunks_fts(conn)
        parse_fixed = batch_reconcile_parse_from_disk(conn)
        cur_ix_up = conn.execute(
            """
            UPDATE papers SET index_status = 'indexed', status_message = NULL, updated_at = ?
            WHERE deleted = 0 AND index_status != 'indexed'
              AND id IN (SELECT DISTINCT paper_id FROM chunks)
            """,
            (now,),
        )
        cur_ix_down = conn.execute(
            """
            UPDATE papers SET index_status = 'pending', updated_at = ?
            WHERE deleted = 0 AND index_status IN ('indexed', 'indexing')
              AND id NOT IN (SELECT DISTINCT paper_id FROM chunks)
            """,
            (now,),
        )
    out = {
        "fts_orphans_removed": fts_removed,
        "parse_status_fixed": parse_fixed,
        "index_status_promoted": int(cur_ix_up.rowcount),
        "index_status_demoted": int(cur_ix_down.rowcount),
    }
    if any(out.values()):
        plog_info("reconcile", "启动校准 %s", out)
    return out
