from pathlib import Path

from app.config import settings
from app.db import get_db
from app.services.paper_batch import (
    list_index_missing_ids,
    list_parse_missing_ids,
    list_summarize_missing_ids,
)


def _insert_paper(conn, pid: str, *, index_status: str = "pending", parse_status: str = "pending"):
    now = "2020-01-01T00:00:00+00:00"
    conn.execute(
        """
        INSERT INTO papers(
          id, title, pdf_path, file_name, file_size, mtime, sha256,
          parse_status, index_status, deleted, created_at, updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            pid,
            pid,
            f"/tmp/{pid}.pdf",
            f"{pid}.pdf",
            1,
            1.0,
            "sha",
            parse_status,
            index_status,
            0,
            now,
            now,
        ),
    )


def test_list_parse_missing_without_document(isolated_test_data_dir):
    pid = "parse-miss-1"
    with get_db() as conn:
        _insert_paper(conn, pid)
    assert pid in list_parse_missing_ids()
    parsed = settings.parsed_dir / pid
    parsed.mkdir(parents=True, exist_ok=True)
    (parsed / "document.md").write_text("# Hi\n\n" + ("Body paragraph. " * 20), encoding="utf-8")
    assert pid not in list_parse_missing_ids()


def test_list_index_missing(isolated_test_data_dir):
    a, b = "idx-miss-a", "idx-miss-b"
    with get_db() as conn:
        _insert_paper(conn, a, index_status="pending")
        _insert_paper(conn, b, index_status="indexed")
    missing = list_index_missing_ids()
    assert a in missing
    assert b not in missing


def test_list_summarize_missing(isolated_test_data_dir):
    pid = "sum-miss-1"
    with get_db() as conn:
        _insert_paper(conn, pid, index_status="indexed", parse_status="parsed")
    assert pid in list_summarize_missing_ids()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO summaries(id, paper_id, summary_type, content, model, created_at)
            VALUES('s1', ?, 'paper_summary', '已有摘要', 'test', '2020-01-01T00:00:00+00:00')
            """,
            (pid,),
        )
    assert pid not in list_summarize_missing_ids()
