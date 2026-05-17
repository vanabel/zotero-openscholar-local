from pathlib import Path

from app.config import settings
from app.db import get_db
from app.services.parse_rescore import list_unscored_with_markdown_ids, rescore_paper_parse_quality


def _insert_paper(conn, pid: str, *, score: float | None = None):
    now = "2020-01-01T00:00:00+00:00"
    conn.execute(
        """
        INSERT INTO papers(
          id, title, pdf_path, file_name, file_size, mtime, sha256,
          parse_status, index_status, parse_quality_score, deleted, created_at, updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            pid,
            pid,
            f"/tmp/{pid}.pdf",
            f"{pid}.pdf",
            1,
            1.0,
            "sha",
            "parsed",
            "indexed",
            score,
            0,
            now,
            now,
        ),
    )


def test_rescore_unscored_with_markdown(isolated_test_data_dir):
    pid = "rescore-1"
    with get_db() as conn:
        _insert_paper(conn, pid, score=None)
    parsed = settings.parsed_dir / pid
    parsed.mkdir(parents=True, exist_ok=True)
    (parsed / "document.md").write_text("# Title\n\n" + ("Paragraph. " * 30), encoding="utf-8")
    (parsed / "meta.json").write_text('{"mode":"mineru"}', encoding="utf-8")

    assert pid in list_unscored_with_markdown_ids()
    res = rescore_paper_parse_quality(pid)
    assert res["ok"] is True
    assert res["parse_quality_score"] is not None

    with get_db() as conn:
        row = conn.execute(
            "SELECT parse_quality_score FROM papers WHERE id = ?", (pid,)
        ).fetchone()
    assert row["parse_quality_score"] is not None
    assert pid not in list_unscored_with_markdown_ids()


def test_rescore_fails_without_markdown(isolated_test_data_dir):
    pid = "rescore-no-md"
    with get_db() as conn:
        _insert_paper(conn, pid, score=None)
    res = rescore_paper_parse_quality(pid)
    assert res["ok"] is False
