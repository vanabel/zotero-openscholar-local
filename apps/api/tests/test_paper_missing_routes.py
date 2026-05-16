from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app

client = TestClient(app)


def _insert(pid: str, *, index_status: str = "pending"):
    now = "2020-01-01T00:00:00+00:00"
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO papers(
              id, title, pdf_path, file_name, file_size, mtime, sha256,
              parse_status, index_status, deleted, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                pid,
                pid,
                f"/tmp/{pid}.pdf",
                f"{pid}.pdf",
                1,
                1.0,
                "sha",
                "pending",
                index_status,
                0,
                now,
                now,
            ),
        )


def test_index_missing_queues():
    _insert("route-miss-1")
    r = client.post("/papers/index-missing", json={"limit": 10})
    assert r.status_code == 202
    data = r.json()
    assert data["matched"] >= 1
    assert data["queued"] >= 1
