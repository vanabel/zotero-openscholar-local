from fastapi import APIRouter

from app.db import get_db

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("")
def stats():
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM papers WHERE deleted=0").fetchone()["c"]
        indexed = conn.execute(
            "SELECT COUNT(*) AS c FROM papers WHERE deleted=0 AND index_status='indexed'"
        ).fetchone()["c"]
        chunks = conn.execute("SELECT COUNT(*) AS c FROM chunks").fetchone()["c"]
    return {"papers": total, "indexed_papers": indexed, "chunks": chunks}
