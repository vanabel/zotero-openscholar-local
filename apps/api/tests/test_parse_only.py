import asyncio
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_db, init_db
from app.main import app
from app.services.indexing import index_paper
from app.services.pdf_parse import load_parsed_markdown

client = TestClient(app)


def test_parse_only_writes_markdown_no_chunks(isolated_test_data_dir, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    pid = "p" * 32
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 minimal")
    now = "2026-01-01T00:00:00+00:00"
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO papers(
              id, pdf_path, file_name, file_size, mtime, sha256,
              parse_status, index_status, deleted, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (pid, str(pdf), "paper.pdf", 1, 1.0, "sha", "pending", "pending", 0, now, now),
        )

    md_text = "# T\n\n" + ("Content for parse only. " * 12)
    meta = {"mode": "test"}

    def fake_parse(*_a, **_k):
        return md_text, meta

    async def no_retry(_pid, _pdf, _out, md, m, report, force=False):
        return md, m, report

    with (
        patch("app.services.indexing.parse_one", side_effect=fake_parse),
        patch("app.services.indexing.maybe_retry_low_quality_parse", side_effect=no_retry),
    ):
        res = asyncio.run(index_paper(pid, parse_only=True))

    assert res["ok"] is True
    assert res.get("parse_only") is True
    loaded = load_parsed_markdown(settings.parsed_dir / pid)
    assert loaded is not None
    with get_db() as conn:
        n = conn.execute("SELECT COUNT(*) AS c FROM chunks WHERE paper_id = ?", (pid,)).fetchone()["c"]
        row = conn.execute("SELECT index_status, parse_status FROM papers WHERE id = ?", (pid,)).fetchone()
    assert int(n) == 0
    assert row["index_status"] == "pending"
    assert row["parse_status"] == "parsed"


def test_parse_missing_enqueues_parse_only(isolated_test_data_dir, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", isolated_test_data_dir)
    init_db()
    pid = "q" * 32
    now = "2026-01-01T00:00:00+00:00"
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO papers(
              id, title, pdf_path, file_name, file_size, mtime, sha256,
              parse_status, index_status, deleted, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (pid, "t", f"/tmp/{pid}.pdf", f"{pid}.pdf", 1, 1.0, "sha", "pending", "pending", 0, now, now),
        )

    with patch("app.services.task_queue.enqueue_index_batch") as mock_batch:
        mock_batch.return_value = [{"task_id": "t1", "status": "queued"}]
        r = client.post("/papers/parse-missing", json={"limit": 5})
    assert r.status_code == 202
    mock_batch.assert_called_once()
    assert mock_batch.call_args.kwargs.get("parse_only") is True


def test_parse_route_rejects_with_reindex_only():
    r = client.post("/papers/" + "a" * 32 + "/index?parse_only=true&reindex_only=true")
    assert r.status_code == 400
