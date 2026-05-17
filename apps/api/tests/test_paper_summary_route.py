from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db import get_db, init_db
from app.main import app
from app.services.summaries import upsert_paper_summary

client = TestClient(app)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_get_paper_summary_route(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    pid = "a" * 32
    now = _utc_now()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO papers(
              id, pdf_path, file_name, file_size, mtime, sha256,
              parse_status, index_status, deleted, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (pid, "/x.pdf", "x.pdf", 1, 1.0, "sha", "parsed", "indexed", 0, now, now),
        )
    upsert_paper_summary(pid, "paper_summary", "测试摘要正文", model="test-model")

    r = client.get(f"/papers/{pid}/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["content"] == "测试摘要正文"
    assert body["paper_id"] == pid

    r2 = client.get("/papers/" + "b" * 32 + "/summary")
    assert r2.status_code == 404
