from __future__ import annotations

from datetime import datetime, timezone

from app.db import get_db


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def set_paper_status(
    paper_id: str,
    *,
    parse_status: str | None = None,
    index_status: str | None = None,
    status_message: str | None = None,
    clear_message: bool = False,
) -> None:
    """更新文献状态；clear_message=True 时清空 status_message。"""
    sets: list[str] = ["updated_at = ?"]
    params: list[object] = [_utc_now()]
    if parse_status is not None:
        sets.append("parse_status = ?")
        params.append(parse_status)
    if index_status is not None:
        sets.append("index_status = ?")
        params.append(index_status)
    if clear_message:
        sets.append("status_message = NULL")
    elif status_message is not None:
        sets.append("status_message = ?")
        params.append(status_message)
    params.append(paper_id)
    with get_db() as conn:
        conn.execute(
            f"UPDATE papers SET {', '.join(sets)} WHERE id = ?",
            params,
        )
