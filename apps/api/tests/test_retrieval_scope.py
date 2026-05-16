from app.config import settings
from app.db import get_db, init_db
from app.services.retrieval_scope import RetrievalScope, resolve_paper_ids


def test_resolve_paper_ids_by_tag(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO papers(
              id, pdf_path, sha256, parse_status, index_status, deleted,
              created_at, updated_at, zotero_tags
            ) VALUES('p1', '/a.pdf', 'sha', 'parsed', 'indexed', 0, 't', 't', ?)
            """,
            ('["ml", "geometry"]',),
        )
        conn.execute(
            """
            INSERT INTO papers(
              id, pdf_path, sha256, parse_status, index_status, deleted,
              created_at, updated_at, zotero_tags
            ) VALUES('p2', '/b.pdf', 'shb', 'parsed', 'indexed', 0, 't', 't', ?)
            """,
            ('["biology"]',),
        )
    with get_db() as conn:
        allowed = resolve_paper_ids(conn, RetrievalScope(tags_any=["ml"]))
    assert allowed == {"p1"}
