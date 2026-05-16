from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.db import get_db


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_answer_id() -> str:
    return uuid.uuid4().hex


def save_answer_citations(
    answer_id: str,
    source_type: str,
    claims: list[dict],
) -> None:
    if not claims:
        return
    now = _utc_now()
    with get_db() as conn:
        for row in claims:
            conn.execute(
                """
                INSERT INTO answer_citations(
                  id, answer_id, source_type, claim_text, chunk_id, ref_num,
                  verified, verifier_score, status, created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    uuid.uuid4().hex,
                    answer_id,
                    source_type,
                    row.get("claim_text") or "",
                    row.get("chunk_id"),
                    row.get("ref_num"),
                    1 if row.get("verified") else 0,
                    row.get("verifier_score"),
                    row.get("status") or "insufficient",
                    now,
                ),
            )


def list_answer_citations(answer_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, answer_id, source_type, claim_text, chunk_id, ref_num,
                   verified, verifier_score, status, created_at
            FROM answer_citations
            WHERE answer_id = ?
            ORDER BY created_at ASC
            """,
            (answer_id,),
        ).fetchall()
    return [dict(r) for r in rows]
