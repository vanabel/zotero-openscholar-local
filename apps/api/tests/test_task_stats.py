from datetime import datetime, timezone

from app.config import settings
from app.db import get_db, init_db
from app.services.task_queue import (
    cancel_all_queued_tasks,
    cancel_orphan_pending_tasks,
    enqueue_index_task,
    get_task,
    get_task_stats,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_get_task_stats_aggregates(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    now = _utc_now()
    with get_db() as conn:
        conn.execute("DELETE FROM tasks")
        conn.execute(
            """
            INSERT INTO tasks(id, task_type, paper_id, status, error, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            ("t1", "index", "p1", "queued", None, now, now),
        )
        conn.execute(
            """
            INSERT INTO tasks(id, task_type, paper_id, status, error, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            ("t2", "summarize", "p2", "completed", None, now, now),
        )
        conn.execute(
            """
            INSERT INTO tasks(id, task_type, paper_id, status, error, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            ("t3", "index", "missing", "failed", "文献不存在", now, now),
        )

    stats = get_task_stats(failed_limit=5)
    assert stats["total"] == 3
    assert stats["pending"] == 1
    assert stats["by_status"] == [
        {"status": "completed", "count": 1},
        {"status": "failed", "count": 1},
        {"status": "queued", "count": 1},
    ]
    assert {r["task_type"]: r["count"] for r in stats["by_type"]} == {"index": 2, "summarize": 1}
    assert len(stats["by_type_status"]) == 3
    assert stats["failed_samples"][0]["error"] == "文献不存在"


def test_cancel_all_queued_reverts_indexing_paper(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    pid = "a" * 32
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF")
    now = _utc_now()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO papers(
              id, pdf_path, file_name, file_size, mtime, sha256,
              parse_status, index_status, deleted, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (pid, str(pdf), "paper.pdf", 10, 1.0, "sha", "pending", "pending", 0, now, now),
        )
    info = enqueue_index_task(pid, force=False)
    with get_db() as conn:
        row = conn.execute("SELECT index_status FROM papers WHERE id = ?", (pid,)).fetchone()
    assert row["index_status"] == "indexing"

    out = cancel_all_queued_tasks()
    assert out["cancelled"] == 1
    assert out["papers_reverted"] == 1
    t = get_task(info["task_id"])
    assert t["status"] == "cancelled"
    with get_db() as conn:
        row = conn.execute("SELECT index_status FROM papers WHERE id = ?", (pid,)).fetchone()
    assert row["index_status"] == "pending"


def test_cancel_orphan_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    now = _utc_now()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO tasks(id, task_type, paper_id, status, error, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            ("orphan-q", "index", "deadbeef", "queued", None, now, now),
        )
    out = cancel_orphan_pending_tasks()
    assert out["cancelled"] == 1
    assert out["failed"] == 0
    t = get_task("orphan-q")
    assert t["status"] == "cancelled"


def test_task_stats_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    client = TestClient(app)
    pid = "a" * 32
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF")
    now = _utc_now()
    with get_db() as conn:
        conn.execute("DELETE FROM tasks")
        conn.execute(
            """
            INSERT INTO papers(
              id, pdf_path, file_name, file_size, mtime, sha256,
              parse_status, index_status, deleted, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (pid, str(pdf), "paper.pdf", 10, 1.0, "sha", "pending", "pending", 0, now, now),
        )
    enqueue_index_task(pid, force=False)

    res = client.get("/tasks/stats")
    assert res.status_code == 200
    body = res.json()
    assert body["pending"] >= 1
    assert any(r["task_type"] == "index" for r in body["by_type"])
