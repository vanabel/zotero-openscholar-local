"""确保 pytest 不会连到开发用 app.sqlite。"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.db import get_db, init_db

_DEV_DB = Path(__file__).resolve().parents[1] / "data" / "app.sqlite"


def test_settings_data_dir_is_isolated_tmp(isolated_test_data_dir):
    assert settings.data_dir.resolve() == isolated_test_data_dir
    assert settings.db_path == isolated_test_data_dir / "app.sqlite"
    if _DEV_DB.is_file():
        assert settings.db_path.resolve() != _DEV_DB.resolve()


def test_destructive_paper_ops_do_not_touch_dev_db(isolated_test_data_dir):
    """回归：test_papers_search 曾 DELETE FROM papers 清空开发库。"""
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    marker_id = "c" * 32
    with get_db() as conn:
        conn.execute("DELETE FROM papers")
        conn.execute(
            """
            INSERT INTO papers(
              id, pdf_path, file_name, file_size, mtime, sha256,
              parse_status, index_status, deleted, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                marker_id,
                "/tmp/isolation-marker.pdf",
                "isolation-marker.pdf",
                1,
                1.0,
                "sha-isolation",
                "pending",
                "pending",
                0,
                now,
                now,
            ),
        )

    assert settings.db_path.parent == isolated_test_data_dir
    if not _DEV_DB.is_file():
        return
    conn = sqlite3.connect(_DEV_DB)
    try:
        n = conn.execute("SELECT COUNT(*) FROM papers WHERE id = ?", (marker_id,)).fetchone()[0]
    finally:
        conn.close()
    assert n == 0
