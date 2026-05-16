import asyncio
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.db import get_db, init_db
from app.services.chunker import ChunkDraft, stable_chunk_id
from app.services.indexing import index_paper, save_paper_chunks
from app.services.pdf_parse import load_parsed_markdown


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_reuse_local_markdown_without_mineru(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    pid = "c" * 32
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 minimal")
    out_dir = settings.parsed_dir / pid
    out_dir.mkdir(parents=True)
    (out_dir / "document.md").write_text("# Cached Title\n\nBody from prior MinerU run.\n" * 20, encoding="utf-8")
    now = _utc_now()
    with get_db() as conn:
        conn.execute("DELETE FROM papers")
        conn.execute(
            """
            INSERT INTO papers(
              id, pdf_path, file_name, file_size, mtime, sha256,
              parse_status, index_status, deleted, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (pid, str(pdf), "paper.pdf", 10, 1.0, "sha", "pending", "pending", 0, now, now),
        )

    loaded = load_parsed_markdown(out_dir)
    assert loaded is not None
    assert "Cached Title" in loaded[0]

    res = asyncio.run(index_paper(pid, force=False))
    assert res["ok"] is True
    assert res.get("reused_parse") is True


def test_reuse_index_when_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    pid = "d" * 32
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 minimal")
    md = "# T\n\n" + ("paragraph.\n" * 30)
    md_hash = __import__("hashlib").sha256(md.encode()).hexdigest()
    out_dir = settings.parsed_dir / pid
    out_dir.mkdir(parents=True)
    (out_dir / "document.md").write_text(md, encoding="utf-8")
    now = _utc_now()
    with get_db() as conn:
        conn.execute("DELETE FROM papers")
        conn.execute(
            """
            INSERT INTO papers(
              id, pdf_path, file_name, file_size, mtime, sha256, md_sha256,
              parse_status, index_status, deleted, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (pid, str(pdf), "paper.pdf", 10, 1.0, "sha", md_hash, "parsed", "indexed", 0, now, now),
        )
        conn.execute(
            """
            INSERT INTO chunks(id, paper_id, section_title, section_path, page_start, page_end,
              chunk_index, text, token_count, embedding_json, created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (pid + "_c0", pid, "", "/", None, None, 0, "x", 1, "[0.1]", now),
        )

    res = asyncio.run(index_paper(pid, force=False))
    assert res["ok"] is True
    assert res.get("reused_index") is True


def test_save_paper_chunks_upsert_before_prune(tmp_path, monkeypatch):
    """先写新 chunk、再删旧行：未 prune 时旧数据仍可用于检索。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    pid = "e" * 32
    now = _utc_now()
    stale_id = f"{pid}_stale"
    with get_db() as conn:
        conn.execute("DELETE FROM papers")
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
              id, paper_id, section_title, section_path, page_start, page_end,
              chunk_index, text, token_count, embedding_json, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (stale_id, pid, "", "/", None, None, 0, "old body", 1, "[0.0]", now),
        )
        conn.execute(
            "INSERT INTO chunks_fts(chunk_id, paper_id, body) VALUES(?,?,?)",
            (stale_id, pid, "old body"),
        )

    draft = ChunkDraft(
        section_title="",
        section_path="/intro",
        page_start=None,
        page_end=None,
        chunk_index=0,
        text="new body",
    )
    new_cid = stable_chunk_id(pid, draft.section_path, draft.chunk_index)

    with get_db() as conn:
        save_paper_chunks(
            conn,
            pid,
            [draft],
            [[0.2]],
            [None],
            md_hash="mdhash",
            prune_stale=False,
        )
        n = conn.execute("SELECT COUNT(*) AS c FROM chunks WHERE paper_id = ?", (pid,)).fetchone()["c"]
        assert n == 2
        save_paper_chunks(
            conn,
            pid,
            [draft],
            [[0.2]],
            [None],
            md_hash="mdhash",
            prune_stale=True,
        )
        rows = conn.execute("SELECT id FROM chunks WHERE paper_id = ?", (pid,)).fetchall()
    assert {r["id"] for r in rows} == {new_cid}
    with get_db() as conn:
        fts = conn.execute("SELECT chunk_id FROM chunks_fts WHERE paper_id = ?", (pid,)).fetchall()
    assert {r["chunk_id"] for r in fts} == {new_cid}
