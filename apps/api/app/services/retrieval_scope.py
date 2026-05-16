from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field


@dataclass
class RetrievalScope:
    """限定检索文献范围；各列表为 OR 语义（命中任一即纳入）。"""

    paper_ids: list[str] | None = None
    tags_any: list[str] | None = None
    collections_any: list[str] | None = None
    years_min: int | None = None
    years_max: int | None = None
    exclude_chunk_types: list[str] = field(default_factory=lambda: ["references"])

    def is_empty(self) -> bool:
        return not (
            self.paper_ids
            or self.tags_any
            or self.collections_any
            or self.years_min is not None
            or self.years_max is not None
        )


def _json_list_contains(column: str, value: str) -> str:
    """SQLite JSON 数组字符串模糊匹配（zotero_tags / zotero_collections 存 JSON 列表）。"""
    esc = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"COALESCE({column}, '') LIKE '%{esc}%'"


def resolve_paper_ids(conn: sqlite3.Connection, scope: RetrievalScope | None) -> set[str] | None:
    """
    返回允许检索的 paper_id 集合；None 表示不限制（全库）。
  """
    if scope is None or scope.is_empty():
        return None

    clauses: list[str] = ["p.deleted = 0"]
    params: list[object] = []

    if scope.paper_ids:
        placeholders = ",".join("?" * len(scope.paper_ids))
        clauses.append(f"p.id IN ({placeholders})")
        params.extend(scope.paper_ids)

    tag_conds: list[str] = []
    for tag in scope.tags_any or []:
        tag = (tag or "").strip()
        if not tag:
            continue
        tag_conds.append(_json_list_contains("p.zotero_tags", tag))
    if tag_conds:
        clauses.append("(" + " OR ".join(tag_conds) + ")")

    col_conds: list[str] = []
    for col in scope.collections_any or []:
        col = (col or "").strip()
        if not col:
            continue
        col_conds.append(_json_list_contains("p.zotero_collections", col))
    if col_conds:
        clauses.append("(" + " OR ".join(col_conds) + ")")

    if scope.years_min is not None:
        clauses.append("p.year >= ?")
        params.append(scope.years_min)
    if scope.years_max is not None:
        clauses.append("p.year <= ?")
        params.append(scope.years_max)

    where = " AND ".join(clauses)
    rows = conn.execute(f"SELECT p.id FROM papers p WHERE {where}", params).fetchall()
    return {str(r["id"]) for r in rows}


def chunk_type_sql_exclude(exclude_types: list[str] | None) -> tuple[str, list[str]]:
    types = [t.strip() for t in (exclude_types or []) if t and t.strip()]
    if not types:
        return "", []
    placeholders = ",".join("?" * len(types))
    return f" AND (ch.chunk_type IS NULL OR ch.chunk_type NOT IN ({placeholders}))", types


def paper_id_filter_sql(allowed: set[str] | None, alias: str = "p") -> tuple[str, list[str]]:
    if allowed is None:
        return "", []
    if not allowed:
        return " AND 1=0", []
    placeholders = ",".join("?" * len(allowed))
    return f" AND {alias}.id IN ({placeholders})", sorted(allowed)


def scope_from_request(
    *,
    paper_ids: list[str] | None = None,
    tags: list[str] | None = None,
    collections: list[str] | None = None,
    years_min: int | None = None,
    years_max: int | None = None,
    include_references: bool = False,
) -> RetrievalScope | None:
    exclude = [] if include_references else ["references"]
    scope = RetrievalScope(
        paper_ids=paper_ids or None,
        tags_any=tags or None,
        collections_any=collections or None,
        years_min=years_min,
        years_max=years_max,
        exclude_chunk_types=exclude,
    )
    return None if scope.is_empty() and not exclude else scope


def parse_tags_json(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data if x]
    except json.JSONDecodeError:
        pass
    return []
