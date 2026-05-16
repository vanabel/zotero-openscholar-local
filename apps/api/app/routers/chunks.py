from fastapi import APIRouter, HTTPException

from app.db import get_db, row_to_dict

router = APIRouter(prefix="/chunks", tags=["chunks"])


@router.get("/{chunk_id}")
def get_chunk(chunk_id: str):
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT ch.*, p.title AS paper_title, p.pdf_path
            FROM chunks ch
            JOIN papers p ON p.id = ch.paper_id
            WHERE ch.id = ?
            """,
            (chunk_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="未找到片段")
    return row_to_dict(row)
