"""
只读读取 Zotero 的 zotero.sqlite，将题录、作者、标签、集合同步到本地 papers 表。

存储目录下路径形如：{ZOTERO_STORAGE}/<itemKey>/file.pdf，其中 <itemKey> 为附件条目的 `items.key`。
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.db import get_db, get_zotero_storage_path
from app.pipeline_logging import plog_info


@dataclass
class ZoteroItemMeta:
    zotero_key: str
    title: str | None
    authors: str | None
    year: int | None
    venue: str | None
    doi: str | None
    tags_json: str  # JSON list[str]
    collections_json: str  # JSON list[str]


def storage_folder_key(pdf_path: Path, storage_root: Path) -> str | None:
    """从 PDF 绝对路径解析出 Zotero storage 子目录名（即附件 items.key）。"""
    try:
        pdf_r = pdf_path.resolve()
        root_r = storage_root.resolve()
    except OSError:
        return None
    try:
        rel = pdf_r.relative_to(root_r)
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) < 2:
        return None
    key = parts[0]
    if not key or key.startswith("."):
        return None
    return key


def _open_zotero_readonly(path: Path) -> sqlite3.Connection | None:
    if not path.is_file():
        return None
    uri = path.resolve().as_uri()
    if not uri.startswith("file:"):
        return None
    # mode=ro 避免与 Zotero 主程序争写；若 Zotero 正独占锁，可能失败
    try:
        conn = sqlite3.connect(f"{uri}?mode=ro", uri=True, check_same_thread=False)
    except sqlite3.Error:
        return None
    conn.row_factory = sqlite3.Row
    return conn


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def _is_deleted(conn: sqlite3.Connection, item_id: int) -> bool:
    if not _has_table(conn, "deletedItems"):
        return False
    r = conn.execute("SELECT 1 FROM deletedItems WHERE itemID = ? LIMIT 1", (item_id,)).fetchone()
    return r is not None


def _fields_table(conn: sqlite3.Connection) -> str:
    if _has_table(conn, "fieldsCombined"):
        return "fieldsCombined"
    return "fields"


def _fetch_item_fields(conn: sqlite3.Connection, item_id: int) -> dict[str, str]:
    ft = _fields_table(conn)
    rows = conn.execute(
        f"""
        SELECT f.fieldName AS fn, v.value AS val
        FROM itemData id
        JOIN {ft} f ON f.fieldID = id.fieldID
        JOIN itemDataValues v ON v.valueID = id.valueID
        WHERE id.itemID = ?
        """,
        (item_id,),
    ).fetchall()
    return {str(r["fn"]): (r["val"] or "") for r in rows if r["fn"]}


def _year_from_fields(fields: dict[str, str]) -> int | None:
    for k in ("year", "date", "issueDate", "accessDate"):
        if k in fields and fields[k]:
            m = re.search(r"\b(19|20)\d{2}\b", fields[k])
            if m:
                return int(m.group(0))
    return None


def _format_one_creator(first_name: str | None, last_name: str | None, field_mode: int) -> str:
    fn = (first_name or "").strip()
    ln = (last_name or "").strip()
    if field_mode == 1:
        return ln or fn
    if ln and fn:
        return f"{ln}, {fn}"
    return ln or fn


def _fetch_authors(conn: sqlite3.Connection, item_id: int) -> str | None:
    if not _has_table(conn, "itemCreators") or not _has_table(conn, "creators"):
        return None
    has_ct = _has_table(conn, "creatorTypes")
    rows = conn.execute(
        """
        SELECT c.firstName AS fn, c.lastName AS ln, c.fieldMode AS fm,
               ic.orderIndex AS oi, ic.creatorTypeID AS ctid
        FROM itemCreators ic
        JOIN creators c ON c.creatorID = ic.creatorID
        WHERE ic.itemID = ?
        ORDER BY ic.orderIndex
        """,
        (item_id,),
    ).fetchall()
    if not rows:
        return None
    type_by_id: dict[int, str] = {}
    if has_ct:
        for tr in conn.execute("SELECT creatorTypeID, creatorType FROM creatorTypes").fetchall():
            type_by_id[int(tr["creatorTypeID"])] = str(tr["creatorType"] or "")

    preferred = frozenset({"author", "contributor"})
    use_rows = rows
    if has_ct:
        typed = [(r, type_by_id.get(int(r["ctid"]), "")) for r in rows]
        pref = [r for r, t in typed if t in preferred]
        if pref:
            use_rows = pref

    parts: list[str] = []
    for r in use_rows:
        s = _format_one_creator(r["fn"], r["ln"], int(r["fm"] or 0))
        if s:
            parts.append(s)
    return "; ".join(parts) if parts else None


def _fetch_tags(conn: sqlite3.Connection, item_ids: list[int]) -> list[str]:
    if not item_ids or not _has_table(conn, "itemTags") or not _has_table(conn, "tags"):
        return []
    placeholders = ",".join("?" * len(item_ids))
    rows = conn.execute(
        f"""
        SELECT DISTINCT t.name AS n
        FROM itemTags it
        JOIN tags t ON t.tagID = it.tagID
        WHERE it.itemID IN ({placeholders})
        ORDER BY n COLLATE NOCASE
        """,
        item_ids,
    ).fetchall()
    return [str(r["n"]) for r in rows if r["n"]]


def _fetch_collections(conn: sqlite3.Connection, item_id: int) -> list[str]:
    if not _has_table(conn, "collectionItems") or not _has_table(conn, "collections"):
        return []
    rows = conn.execute(
        """
        SELECT DISTINCT c.collectionName AS n
        FROM collectionItems ci
        JOIN collections c ON c.collectionID = ci.collectionID
        WHERE ci.itemID = ?
        ORDER BY n COLLATE NOCASE
        """,
        (item_id,),
    ).fetchall()
    return [str(r["n"]) for r in rows if r["n"]]


def _lookup_attachment(conn: sqlite3.Connection, folder_key: str) -> tuple[int, int | None] | None:
    """返回 (attachment_item_id, parent_item_id)。"""
    rows = conn.execute(
        """
        SELECT i.itemID AS aid, ia.parentItemID AS pid
        FROM items i
        JOIN itemAttachments ia ON ia.itemID = i.itemID
        WHERE i.key = ? COLLATE NOCASE
        """,
        (folder_key,),
    ).fetchall()
    if not rows:
        return None
    for r in rows:
        aid = int(r["aid"])
        pid = r["pid"]
        parent_id = int(pid) if pid is not None else None
        if _is_deleted(conn, aid):
            continue
        if parent_id and _is_deleted(conn, parent_id):
            continue
        return aid, parent_id
    return None


def _build_meta(conn: sqlite3.Connection, folder_key: str) -> ZoteroItemMeta | None:
    hit = _lookup_attachment(conn, folder_key)
    if not hit:
        return None
    attach_id, parent_id = hit
    bib_id = parent_id if parent_id else attach_id
    fields = _fetch_item_fields(conn, bib_id)
    if not fields and bib_id != attach_id:
        fields = _fetch_item_fields(conn, attach_id)

    title = (fields.get("title") or "").strip() or None
    doi = (fields.get("DOI") or fields.get("doi") or "").strip() or None
    venue = (
        (fields.get("publicationTitle") or fields.get("bookTitle") or fields.get("websiteTitle") or "")
        .strip()
        or None
    )
    year = _year_from_fields(fields)
    authors = _fetch_authors(conn, bib_id)
    if not authors and bib_id != attach_id:
        authors = _fetch_authors(conn, attach_id)

    tag_ids = [bib_id]
    if bib_id != attach_id:
        tag_ids.append(attach_id)
    tags = _fetch_tags(conn, tag_ids)
    collections = _fetch_collections(conn, bib_id)

    return ZoteroItemMeta(
        zotero_key=folder_key,
        title=title,
        authors=authors,
        year=year,
        venue=venue,
        doi=doi,
        tags_json=json.dumps(tags, ensure_ascii=False),
        collections_json=json.dumps(collections, ensure_ascii=False),
    )


def sync_zotero_metadata_to_papers(*, include_deleted: bool = False) -> dict[str, Any]:
    """
    根据 pdf_path 对应的 storage 子目录 key，从 zotero.sqlite 回填 papers 的题录字段。
    若库文件不存在、无法打开或表结构不匹配，则跳过并返回说明。
    """
    zp = settings.zotero_sqlite_path
    if zp is None:
        return {"ok": True, "skipped": "ZOTERO_SQLITE_PATH 未配置", "updated": 0, "unmatched": 0, "errors": 0}
    path = Path(zp).expanduser()
    zconn = _open_zotero_readonly(path)
    if zconn is None:
        return {
            "ok": True,
            "skipped": f"zotero.sqlite 不可读或不存在: {path}",
            "updated": 0,
            "unmatched": 0,
            "errors": 0,
        }

    storage = get_zotero_storage_path()
    required = ("items", "itemAttachments", "itemData", "itemDataValues")
    missing = [t for t in required if not _has_table(zconn, t)]
    if missing:
        zconn.close()
        return {
            "ok": False,
            "error": f"Zotero 数据库缺少表: {', '.join(missing)}",
            "updated": 0,
            "unmatched": 0,
            "errors": 0,
        }

    updated = 0
    unmatched = 0
    errors = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        with get_db() as conn:
            where = "1=1" if include_deleted else "deleted = 0"
            rows = conn.execute(f"SELECT id, pdf_path FROM papers WHERE {where}").fetchall()
            for r in rows:
                pdf_path = Path(r["pdf_path"])
                key = storage_folder_key(pdf_path, storage)
                if not key:
                    unmatched += 1
                    continue
                try:
                    meta = _build_meta(zconn, key)
                except sqlite3.Error:
                    errors += 1
                    continue
                if meta is None:
                    unmatched += 1
                    continue
                try:
                    conn.execute(
                        """
                        UPDATE papers SET
                          zotero_key = ?,
                          title = COALESCE(?, title),
                          authors = ?,
                          year = ?,
                          venue = ?,
                          doi = ?,
                          zotero_tags = ?,
                          zotero_collections = ?,
                          updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            meta.zotero_key,
                            meta.title,
                            meta.authors,
                            meta.year,
                            meta.venue,
                            meta.doi,
                            meta.tags_json,
                            meta.collections_json,
                            now_iso,
                            r["id"],
                        ),
                    )
                except sqlite3.Error:
                    errors += 1
                    continue
                updated += 1
    finally:
        zconn.close()

    plog_info(
        "scan",
        "zotero 元数据同步完成 updated=%s unmatched=%s errors=%s",
        updated,
        unmatched,
        errors,
    )
    return {
        "ok": True,
        "zotero_sqlite": str(path),
        "updated": updated,
        "unmatched": unmatched,
        "errors": errors,
    }
