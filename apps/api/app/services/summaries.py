from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.db import get_db
from app.services.retrieval_scope import RetrievalScope, resolve_paper_ids


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_paper_summary(
    paper_id: str,
    summary_type: str,
    content: str,
    *,
    model: str | None = None,
) -> str:
    sid = uuid.uuid4().hex
    now = _utc_now()
    with get_db() as conn:
        conn.execute(
            "DELETE FROM summaries WHERE paper_id = ? AND summary_type = ?",
            (paper_id, summary_type),
        )
        conn.execute(
            """
            INSERT INTO summaries(id, paper_id, summary_type, content, model, created_at)
            VALUES(?,?,?,?,?,?)
            """,
            (sid, paper_id, summary_type, content.strip(), model, now),
        )
    return sid


def get_paper_summary(paper_id: str, summary_type: str = "paper_summary") -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT id, paper_id, summary_type, content, model, created_at
            FROM summaries
            WHERE paper_id = ? AND summary_type = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (paper_id, summary_type),
        ).fetchone()
    return dict(row) if row else None


def retrieve_summaries_for_query(
    query: str,
    *,
    limit: int = 6,
    scope: RetrievalScope | None = None,
) -> list[dict]:
    """按关键词在 summaries 中检索，作为综述/问答的上层上下文。"""
    q = (query or "").strip()
    if not q or len(q) < 2:
        return []
    tokens = [t for t in q.replace("，", " ").split() if len(t) >= 2][:6]
    if not tokens:
        tokens = [q[:24]]

    with get_db() as conn:
        allowed = resolve_paper_ids(conn, scope)
        if allowed is not None and not allowed:
            return []

        conds = ["(s.content LIKE ? OR p.title LIKE ?)" for _ in tokens]
        params: list[object] = []
        for t in tokens:
            pat = f"%{t}%"
            params.extend([pat, pat])

        paper_sql, paper_params = "", []
        if allowed is not None:
            placeholders = ",".join("?" * len(allowed))
            paper_sql = f" AND p.id IN ({placeholders})"
            paper_params = sorted(allowed)

        sql = f"""
        SELECT s.id AS summary_id, s.paper_id, s.summary_type, s.content,
               p.title AS paper_title, p.year
        FROM summaries s
        JOIN papers p ON p.id = s.paper_id AND p.deleted = 0
        WHERE ({' OR '.join(conds)}){paper_sql}
        ORDER BY p.year DESC NULLS LAST, s.created_at DESC
        LIMIT ?
        """
        rows = conn.execute(sql, [*params, *paper_params, limit]).fetchall()

    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "summary_id": r["summary_id"],
                "paper_id": r["paper_id"],
                "title": r["paper_title"],
                "year": r["year"],
                "summary_type": r["summary_type"],
                "text": r["content"],
                "is_summary": True,
            }
        )
    return out


def summaries_to_pseudo_contexts(summaries: list[dict], start_ref: int = 1) -> list[dict]:
    """将 summary 行转为与 chunk 兼容的 context 结构（用于 prompt）。"""
    contexts: list[dict] = []
    for i, s in enumerate(summaries, start=start_ref):
        contexts.append(
            {
                "chunk_id": f"summary:{s.get('summary_id') or s.get('paper_id')}",
                "paper_id": s["paper_id"],
                "title": s.get("title"),
                "section_path": f"summary/{s.get('summary_type', 'paper')}",
                "text": s["text"],
                "is_summary": True,
                "_display_ref": i,
            }
        )
    return contexts
