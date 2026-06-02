from datetime import datetime, timezone

from app.config import settings
from app.db import get_db, init_db
from app.services.task_queue import (
    cancel_all_queued_tasks,
    cancel_orphan_pending_tasks,
    compute_queue_throughput,
    enqueue_index_task,
    get_task,
    get_task_stats,
    purge_terminal_tasks,
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


def test_get_task_stats_by_kind_parse_only(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    now = _utc_now()
    with get_db() as conn:
        conn.execute("DELETE FROM tasks")
        conn.execute(
            """
            INSERT INTO tasks(
              id, task_type, paper_id, status, payload_json, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            ("tp1", "index", "p1", "queued", '{"parse_only": true}', now, now),
        )
        conn.execute(
            """
            INSERT INTO tasks(
              id, task_type, paper_id, status, payload_json, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            ("ti1", "index", "p2", "completed", '{"force": false}', now, now),
        )
    stats = get_task_stats(failed_limit=0)
    assert {r["kind"]: r["count"] for r in stats["by_kind"]} == {"parse": 1, "index": 1}


def test_compute_queue_throughput_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    t0 = "2026-05-01T10:00:00+00:00"
    t1 = "2026-05-01T10:00:01+00:00"
    t_task_start = "2026-06-01T07:00:00+00:00"
    t_done = "2026-06-01T07:02:12+00:00"
    progress = (
        '{"phase":"done","task_started_at":"'
        + t_task_start
        + '","phase_started_at":"'
        + t_task_start
        + '"}'
    )
    with get_db() as conn:
        conn.execute("DELETE FROM tasks")
        conn.execute(
            """
            INSERT INTO tasks(id, task_type, paper_id, status, created_at, updated_at)
            VALUES (?,?,?,?,?,?)
            """,
            ("q1", "summarize", "p1", "queued", t0, t0),
        )
        conn.execute(
            """
            INSERT INTO tasks(id, task_type, paper_id, status, created_at, updated_at)
            VALUES (?,?,?,?,?,?)
            """,
            ("q2", "summarize", "p2", "running", t1, t1),
        )
        conn.execute(
            """
            INSERT INTO tasks(id, task_type, paper_id, status, progress_json, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            ("c1", "summarize", "p0", "completed", progress, t0, t_done),
        )
        conn.execute(
            """
            INSERT INTO tasks(id, task_type, paper_id, status, created_at, updated_at)
            VALUES (?,?,?,?,?,?)
            """,
            ("old", "summarize", "p9", "completed", "2026-04-01T10:00:00+00:00", "2026-04-01T11:00:00+00:00"),
        )
        qt = compute_queue_throughput(conn)

    assert qt is not None
    assert qt["batch_started_at"] == t0
    assert qt["batch_ended_at"] == t1
    assert qt["completed_count"] == 1
    assert qt["completed_by_kind"] == {"summarize": 1}
    assert qt["kind_first_completed_at"] == {"summarize": t_done}
    assert qt["throughput_started_at"] == t_done
    assert qt["avg_duration_sec"] == 132.0

    stats = get_task_stats(failed_limit=0)
    assert stats["queue_throughput"] == qt


def test_compute_queue_throughput_restored_queue(tmp_path, monkeypatch):
    """恢复队列后 pending 为新 created_at，已完成项 created_at 更早，应靠 updated_at 计入。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    t_old = "2026-04-01T10:00:00+00:00"
    t_restore = "2026-06-01T06:00:00+00:00"
    t_task_start = "2026-06-01T07:00:00+00:00"
    t_done = "2026-06-01T07:02:12+00:00"
    progress = (
        '{"phase":"done","task_started_at":"'
        + t_task_start
        + '","phase_started_at":"'
        + t_task_start
        + '"}'
    )
    with get_db() as conn:
        conn.execute("DELETE FROM tasks")
        conn.execute(
            """
            INSERT INTO tasks(id, task_type, paper_id, status, created_at, updated_at)
            VALUES (?,?,?,?,?,?)
            """,
            ("q1", "summarize", "p1", "queued", t_restore, t_restore),
        )
        conn.execute(
            """
            INSERT INTO tasks(id, task_type, paper_id, status, progress_json, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            ("c1", "summarize", "p0", "completed", progress, t_old, t_done),
        )
        qt = compute_queue_throughput(conn)

    assert qt is not None
    assert qt["completed_count"] == 1
    assert qt["avg_duration_sec"] == 132.0


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


def test_purge_terminal_tasks(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    now = _utc_now()
    with get_db() as conn:
        conn.execute("DELETE FROM tasks")
        for tid, st in (("f1", "failed"), ("c1", "cancelled"), ("q1", "queued")):
            conn.execute(
                """
                INSERT INTO tasks(id, task_type, paper_id, status, error, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (tid, "index", "p1", st, "err" if st == "failed" else None, now, now),
            )
    out = purge_terminal_tasks()
    assert out["deleted"] == 2
    assert out["failed"] == 1
    assert out["cancelled"] == 1
    stats = get_task_stats(failed_limit=5)
    assert stats["total"] == 1
    assert stats["pending"] == 1


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
