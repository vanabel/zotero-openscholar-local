import asyncio
import time
from datetime import datetime, timezone

from app.config import settings
from app.db import get_db, init_db
from app.services.indexing import index_paper
from app.services.llm import EmbeddingClient
from app.services.task_queue import enqueue_index_task, get_task, list_active_tasks, start_worker, stop_worker


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_paper(tmp_path, pid: str) -> None:
    pdf = tmp_path / f"{pid}.pdf"
    pdf.write_bytes(b"%PDF-1.4 minimal")
    out_dir = settings.parsed_dir / pid
    out_dir.mkdir(parents=True)
    (out_dir / "document.md").write_text("# T\n\n" + ("paragraph.\n" * 30), encoding="utf-8")
    now = _utc_now()
    with get_db() as conn:
        conn.execute("DELETE FROM papers")
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


def test_enqueue_dedupes_active_task(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    pid = "a" * 32
    _insert_paper(tmp_path, pid)

    a = enqueue_index_task(pid, force=False)
    b = enqueue_index_task(pid, force=False)
    assert a["task_id"] == b["task_id"]
    assert b.get("deduped") is True
    assert len(list_active_tasks()) == 1


async def _fake_embed(self, texts: list[str]) -> list[list[float]]:
    return [[0.1] * 8 for _ in texts]


async def _run_worker_until_idle(timeout: float = 30.0) -> None:
    start_worker()
    try:
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if not list_active_tasks():
                return
            await asyncio.sleep(0.2)
        raise AssertionError("tasks did not finish in time")
    finally:
        await stop_worker()


def test_worker_completes_index_task(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(EmbeddingClient, "embed", _fake_embed)
    init_db()
    pid = "b" * 32
    _insert_paper(tmp_path, pid)

    info = enqueue_index_task(pid, force=False)
    asyncio.run(_run_worker_until_idle())

    t = get_task(info["task_id"])
    assert t is not None
    assert t["status"] == "completed"
    assert t["result"] and t["result"].get("ok") is True

    with get_db() as conn:
        row = conn.execute("SELECT index_status FROM papers WHERE id = ?", (pid,)).fetchone()
    assert row["index_status"] == "indexed"


def test_index_paper_still_sync_without_queue(tmp_path, monkeypatch):
    """脚本与单测仍可直接 await index_paper。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(EmbeddingClient, "embed", _fake_embed)
    init_db()
    pid = "c" * 32
    _insert_paper(tmp_path, pid)
    res = asyncio.run(index_paper(pid, force=False))
    assert res["ok"] is True
