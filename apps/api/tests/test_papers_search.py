from datetime import datetime, timezone

from app.db import get_db, init_db
from app.services.zotero_scanner import count_papers, list_papers


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_papers_title_search():
    init_db()
    now = _utc_now()
    with get_db() as conn:
        conn.execute("DELETE FROM papers")
        conn.execute(
            """
            INSERT INTO papers(
              id, pdf_path, file_name, title, authors, file_size, mtime, sha256,
              parse_status, index_status, deleted, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "a" * 32,
                "/tmp/alpha.pdf",
                "alpha.pdf",
                "Deep Learning for Science",
                "Alice",
                1,
                1.0,
                "sha1",
                "pending",
                "pending",
                0,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO papers(
              id, pdf_path, file_name, title, authors, file_size, mtime, sha256,
              parse_status, index_status, deleted, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "b" * 32,
                "/tmp/beta-notes.pdf",
                "beta-notes.pdf",
                None,
                "Bob Beta",
                1,
                1.0,
                "sha2",
                "pending",
                "pending",
                0,
                now,
                now,
            ),
        )

    assert count_papers(q="Deep") == 1
    assert count_papers(q="beta") == 1
    assert count_papers(q="gamma") == 0
    hits = list_papers(q="Learning", limit=10)
    assert len(hits) == 1
    assert hits[0]["title"] == "Deep Learning for Science"
