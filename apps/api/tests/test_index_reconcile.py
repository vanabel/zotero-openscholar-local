from datetime import datetime, timezone

from app.config import settings
from app.db import get_db, init_db
from app.services.index_reconcile import (
    prune_orphan_chunks_fts,
    reconcile_database_on_startup,
    reconcile_papers_with_disk,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_paper(conn, pid: str, *, parse_status: str, index_status: str) -> None:
    now = _utc_now()
    conn.execute(
        """
        INSERT INTO papers(
          id, pdf_path, file_name, file_size, mtime, sha256,
          parse_status, index_status, deleted, created_at, updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (pid, f"/{pid}.pdf", "x.pdf", 1, 1.0, "sha", parse_status, index_status, 0, now, now),
    )


def test_prune_orphan_fts_globally(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    pid = "a" * 32
    now = _utc_now()
    with get_db() as conn:
        _insert_paper(conn, pid, parse_status="parsed", index_status="pending")
        conn.execute(
            "INSERT INTO chunks_fts(chunk_id, paper_id, body) VALUES(?,?,?)",
            ("orphan", pid, "ghost"),
        )
        n = prune_orphan_chunks_fts(conn)
        left = conn.execute("SELECT COUNT(*) AS c FROM chunks_fts").fetchone()["c"]
    assert n == 1
    assert left == 0


def test_reconcile_promotes_indexed_and_parsed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    pid = "b" * 32
    out_dir = settings.parsed_dir / pid
    out_dir.mkdir(parents=True)
    (out_dir / "document.md").write_text("# T\n\n" + ("x\n" * 50), encoding="utf-8")
    now = _utc_now()
    with get_db() as conn:
        _insert_paper(conn, pid, parse_status="pending", index_status="pending")
        conn.execute(
            """
            INSERT INTO chunks(
              id, paper_id, section_title, section_path, page_start, page_end,
              chunk_index, text, token_count, embedding_json, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (f"{pid}_c0", pid, "", "/", None, None, 0, "body", 1, "[0.1]", now),
        )
        item = dict(conn.execute("SELECT * FROM papers WHERE id = ?", (pid,)).fetchone())
        reconcile_papers_with_disk(conn, [item])
        row = conn.execute(
            "SELECT parse_status, index_status FROM papers WHERE id = ?", (pid,)
        ).fetchone()
    assert row["parse_status"] == "parsed"
    assert row["index_status"] == "indexed"
    assert item["index_status"] == "indexed"


def test_reconcile_demotes_false_indexed_and_cleans_fts(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    pid = "c" * 32
    with get_db() as conn:
        _insert_paper(conn, pid, parse_status="parsed", index_status="indexed")
        conn.execute(
            "INSERT INTO chunks_fts(chunk_id, paper_id, body) VALUES(?,?,?)",
            ("ghost", pid, "only fts"),
        )
        item = dict(conn.execute("SELECT * FROM papers WHERE id = ?", (pid,)).fetchone())
        reconcile_papers_with_disk(conn, [item])
        row = conn.execute(
            "SELECT index_status FROM papers WHERE id = ?", (pid,)
        ).fetchone()
        fts = conn.execute("SELECT COUNT(*) AS c FROM chunks_fts WHERE paper_id = ?", (pid,)).fetchone()["c"]
    assert row["index_status"] == "pending"
    assert fts == 0


def test_startup_reconcile_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    pid = "d" * 32
    out_dir = settings.parsed_dir / pid
    out_dir.mkdir(parents=True)
    (out_dir / "document.md").write_text("# T\n\n" + ("y\n" * 50), encoding="utf-8")
    with get_db() as conn:
        _insert_paper(conn, pid, parse_status="pending", index_status="indexed")
        conn.execute(
            "INSERT INTO chunks_fts(chunk_id, paper_id, body) VALUES(?,?,?)",
            ("z", pid, "orphan"),
        )
    stats = reconcile_database_on_startup()
    assert stats["fts_orphans_removed"] >= 1
    assert stats["index_status_demoted"] >= 1
    assert stats["parse_status_fixed"] >= 1
    with get_db() as conn:
        row = conn.execute(
            "SELECT parse_status, index_status FROM papers WHERE id = ?", (pid,)
        ).fetchone()
    assert row["parse_status"] == "parsed"
    assert row["index_status"] == "pending"
