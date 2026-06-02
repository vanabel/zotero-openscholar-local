"""GET /papers?work_queue= 与 zotero_scanner 筛选一致。"""

from app.db import get_db
from app.services.zotero_scanner import count_papers, list_papers


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


def test_work_queue_index_missing(isolated_test_data_dir):
    pid_a = "a" * 32
    pid_b = "b" * 32
    with get_db() as conn:
        _insert_paper(conn, pid_a, index_status="pending")
        _insert_paper(conn, pid_b, index_status="indexed")
    assert count_papers(work_queue="index_missing") == 1
    rows = list_papers(work_queue="index_missing", limit=10)
    assert len(rows) == 1
    assert rows[0]["id"] == pid_a


def test_work_queue_summarize_missing(isolated_test_data_dir):
    pid = "c" * 32
    with get_db() as conn:
        _insert_paper(conn, pid, index_status="indexed", parse_status="parsed")
    assert count_papers(work_queue="summarize_missing") == 1
    assert list_papers(work_queue="summarize_missing", limit=5)[0]["id"] == pid
