from app.config import settings
from app.db import get_db, init_db


def test_parse_quality_filters(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    with get_db() as conn:
        conn.execute("DELETE FROM papers")
        for pid, score in [("a" * 32, 0.5), ("b" * 32, 0.9), ("c" * 32, None)]:
            conn.execute(
                """
                INSERT INTO papers(
                  id, pdf_path, sha256, parse_status, index_status, deleted,
                  parse_quality_score, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (pid, f"/{pid}.pdf", "sha", "parsed", "indexed", 0, score, "t", "t"),
            )

    from app.services.zotero_scanner import count_papers, list_papers, parse_quality_summary

    low = list_papers(parse_quality_lte=0.65)
    assert len(low) == 1
    assert low[0]["parse_quality_score"] == 0.5

    high = list_papers(parse_quality_gte=0.85)
    assert len(high) == 1
    assert high[0]["parse_quality_score"] == 0.9

    missing = list_papers(parse_quality_missing=True)
    assert len(missing) == 1
    assert missing[0]["parse_quality_score"] is None

    summary = parse_quality_summary()
    assert summary["total"] == 3
    assert summary["low_quality"] == 1
    assert summary["unscored"] == 1
