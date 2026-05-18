import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.config import settings
from app.db import get_db, init_db
from app.services.chunk_batch import chunk_paper_from_parsed, list_paper_ids_for_chunk
from app.services.embed_batch import embed_vectors_for_paper, list_paper_ids_for_embed


def _seed_parsed_only(tmp_path, monkeypatch) -> str:
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    pid = "f" * 32
    now = "2026-01-01T00:00:00+00:00"
    parsed = settings.parsed_dir / pid
    parsed.mkdir(parents=True)
    body = "# Title\n\n" + ("Paragraph content for chunking. " * 8) + "\n\n" + ("Second section text. " * 8)
    (parsed / "document.md").write_text(body, encoding="utf-8")
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO papers(
              id, pdf_path, file_name, file_size, mtime, sha256,
              parse_status, index_status, deleted, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (pid, "/no/such/file.pdf", "x.pdf", 1, 1.0, "sha", "parsed", "pending", 0, now, now),
        )
    return pid


def test_chunk_batch_without_local_pdf(tmp_path, monkeypatch):
    pid = _seed_parsed_only(tmp_path, monkeypatch)
    res = chunk_paper_from_parsed(pid)
    assert res["ok"] is True
    assert res["chunks"] >= 1
    with get_db() as conn:
        n = conn.execute("SELECT COUNT(*) AS c FROM chunks WHERE paper_id = ?", (pid,)).fetchone()["c"]
    assert int(n) >= 1


def test_list_chunk_missing_only(tmp_path, monkeypatch):
    pid = _seed_parsed_only(tmp_path, monkeypatch)
    assert pid in list_paper_ids_for_chunk(missing_only=True)
    chunk_paper_from_parsed(pid)
    assert pid not in list_paper_ids_for_chunk(missing_only=True)


@patch("app.services.embed_batch.EmbeddingClient")
def test_embed_batch_updates_only_embedding(mock_cls, tmp_path, monkeypatch):
    import asyncio
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "embed_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_base", "https://api.example/v1")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    init_db()
    pid = "g" * 32
    cid = "h" * 32
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
            (cid, pid, 0, "text", 1, None, json.dumps([9.0]), now),
        )
    inst = mock_cls.return_value
    inst.embed = AsyncMock(return_value=[[0.3, 0.7]])
    res = asyncio.run(embed_vectors_for_paper(pid))
    assert res["ok"] is True
    assert res["updated"] == 1
    with get_db() as conn:
        row = conn.execute(
            "SELECT embedding_json, scholar_embedding_json FROM chunks WHERE id = ?",
            (cid,),
        ).fetchone()
    assert json.loads(row["embedding_json"]) == [0.3, 0.7]
    assert json.loads(row["scholar_embedding_json"]) == [9.0]
    assert pid in list_paper_ids_for_embed(missing_only=False)
    assert pid not in list_paper_ids_for_embed(missing_only=True)
