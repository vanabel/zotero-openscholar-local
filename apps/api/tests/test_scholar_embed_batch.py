import json
from unittest.mock import patch

from app.config import settings
from app.db import get_db, init_db
from app.services.scholar_embed_batch import (
    embed_scholar_for_paper,
    list_paper_ids_for_scholar_embed,
    run_scholar_embed_batch,
)


def _seed_paper_with_chunks(tmp_path, monkeypatch, *, scholar: bool) -> str:
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "openscholar_retriever_enabled", True)
    init_db()
    pid = "b" * 32
    cid = "c" * 32
    now = "2026-01-01T00:00:00+00:00"
    vec = [0.5, 0.5]
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO papers(
              id, pdf_path, file_name, file_size, mtime, sha256,
              parse_status, index_status, deleted, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (pid, "/y.pdf", "y.pdf", 1, 1.0, "sha", "parsed", "indexed", 0, now, now),
        )
        conn.execute(
            """
            INSERT INTO chunks(
              id, paper_id, chunk_index, text, token_count,
              embedding_json, scholar_embedding_json, created_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                cid,
                pid,
                0,
                "chunk text",
                2,
                json.dumps([0.1, 0.2]),
                json.dumps(vec) if scholar else None,
                now,
            ),
        )
    return pid


@patch("app.services.scholar_embed_batch.encode_passages", return_value=[[1.0, 0.0]])
def test_embed_scholar_updates_sqlite_only(mock_encode, tmp_path, monkeypatch):
    pid = _seed_paper_with_chunks(tmp_path, monkeypatch, scholar=False)
    with patch("app.services.scholar_embed_batch.openscholar_retriever_enabled", return_value=True):
        res = embed_scholar_for_paper(pid, sync_lance=False)
    assert res["ok"] is True
    assert res["updated"] == 1
    mock_encode.assert_called_once()
    with get_db() as conn:
        row = conn.execute(
            "SELECT embedding_json, scholar_embedding_json FROM chunks WHERE id = ?",
            ("c" * 32,),
        ).fetchone()
    assert json.loads(row["embedding_json"]) == [0.1, 0.2]
    assert json.loads(row["scholar_embedding_json"]) == [1.0, 0.0]


@patch("app.services.scholar_embed_batch.encode_passages", return_value=[[1.0, 0.0]])
def test_embed_scholar_skips_when_complete(mock_encode, tmp_path, monkeypatch):
    pid = _seed_paper_with_chunks(tmp_path, monkeypatch, scholar=True)
    with patch("app.services.scholar_embed_batch.openscholar_retriever_enabled", return_value=True):
        res = embed_scholar_for_paper(pid, force=False, sync_lance=False)
    assert res["ok"] is True
    assert res.get("skipped") is True
    mock_encode.assert_not_called()


def test_list_missing_only(tmp_path, monkeypatch):
    pid_missing = _seed_paper_with_chunks(tmp_path, monkeypatch, scholar=False)
    pid_done = "d" * 32
    now = "2026-01-01T00:00:00+00:00"
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO papers(
              id, pdf_path, file_name, file_size, mtime, sha256,
              parse_status, index_status, deleted, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (pid_done, "/z.pdf", "z.pdf", 1, 1.0, "sha2", "parsed", "indexed", 0, now, now),
        )
        conn.execute(
            """
            INSERT INTO chunks(
              id, paper_id, chunk_index, text, token_count,
              embedding_json, scholar_embedding_json, created_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            ("e" * 32, pid_done, 0, "t", 1, None, json.dumps([0.1]), now),
        )
    ids = list_paper_ids_for_scholar_embed(missing_only=True)
    assert pid_missing in ids
    assert pid_done not in ids


@patch("app.services.scholar_embed_batch.embed_scholar_for_paper")
def test_run_batch_aggregates(mock_embed, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    mock_embed.side_effect = [
        {"ok": True, "paper_id": "1", "updated": 1},
        {"ok": False, "paper_id": "2", "error": "x"},
    ]
    out = run_scholar_embed_batch(["1", "2"], sync_lance=False)
    assert out["succeeded"] == 1
    assert out["failed"] == 1
