import json

from app.config import settings
from app.db import get_db, init_db
from app.services.paper_batch import get_batch_work_summary
from app.services.lance_store import (
    _TABLE,
    backfill_lance_batch,
    backfill_paper_vectors_from_db,
    lancedb_enabled,
    search_scholar,
)


def test_backfill_writes_lance_from_sqlite(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    if not lancedb_enabled():
        return
    init_db()
    pid = "a" * 32
    cid = "c" * 32
    vec = [0.1, 0.2, 0.3, 0.4]
    now = "2026-01-01T00:00:00+00:00"
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
        conn.execute(
            """
            INSERT INTO chunks(
              id, paper_id, chunk_index, text, token_count,
              embedding_json, scholar_embedding_json, created_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (cid, pid, 0, "t", 1, None, json.dumps(vec), now),
        )

    s0 = get_batch_work_summary()
    assert s0["lance_scholar_sqlite_with_vectors"] >= 1
    assert s0["lance_scholar_in_lance"] == 0
    assert s0["lance_scholar_papers"] >= 1

    res = backfill_paper_vectors_from_db(pid)
    assert res["ok"] is True
    assert res["rows"] == 1

    hits = search_scholar(vec, limit=5, allowed_paper_ids={pid})
    assert hits is not None
    assert cid in hits

    s1 = get_batch_work_summary()
    assert s1["lance_scholar_papers"] == 0
    assert s1["lance_scholar_sqlite_with_vectors"] >= 1
    assert s1["lance_scholar_in_lance"] >= 1


def test_backfill_batch_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    if not lancedb_enabled():
        return
    init_db()
    out = backfill_lance_batch([])
    assert out["matched"] == 0
    assert out["synced"] == 0
