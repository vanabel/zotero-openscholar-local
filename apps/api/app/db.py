import json
from contextlib import contextmanager

try:
    import pysqlite3 as sqlite3  # type: ignore[no-redef]  # 超算系统 sqlite 3.7 无法读 FTS5
except ImportError:
    import sqlite3
from pathlib import Path

from app.config import settings


def _connect() -> sqlite3.Connection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def get_db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS papers (
              id TEXT PRIMARY KEY,
              zotero_key TEXT,
              title TEXT,
              authors TEXT,
              year INTEGER,
              venue TEXT,
              doi TEXT,
              pdf_path TEXT NOT NULL UNIQUE,
              file_name TEXT,
              file_size INTEGER,
              mtime REAL,
              sha256 TEXT NOT NULL,
              md_sha256 TEXT,
              parse_status TEXT DEFAULT 'pending',
              index_status TEXT DEFAULT 'pending',
              deleted INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chunks (
              id TEXT PRIMARY KEY,
              paper_id TEXT NOT NULL,
              section_title TEXT,
              section_path TEXT,
              page_start INTEGER,
              page_end INTEGER,
              chunk_index INTEGER NOT NULL,
              text TEXT NOT NULL,
              token_count INTEGER,
              embedding_json TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
              chunk_id UNINDEXED,
              paper_id UNINDEXED,
              body,
              tokenize = 'unicode61'
            );

            CREATE TABLE IF NOT EXISTS summaries (
              id TEXT PRIMARY KEY,
              paper_id TEXT NOT NULL,
              summary_type TEXT NOT NULL,
              content TEXT NOT NULL,
              model TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS tasks (
              id TEXT PRIMARY KEY,
              task_type TEXT NOT NULL,
              paper_id TEXT,
              status TEXT NOT NULL,
              error TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chat_cache (
              cache_key TEXT PRIMARY KEY,
              question_norm TEXT NOT NULL,
              lang TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS review_cache (
              cache_key TEXT PRIMARY KEY,
              topic_norm TEXT NOT NULL,
              focus_norm TEXT NOT NULL,
              lang TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS parse_reports (
              id TEXT PRIMARY KEY,
              paper_id TEXT NOT NULL,
              parser TEXT,
              parser_mode TEXT,
              parse_quality_score REAL,
              text_length INTEGER,
              page_count INTEGER,
              detected_sections INTEGER,
              formula_blocks INTEGER,
              table_blocks INTEGER,
              image_blocks INTEGER,
              ocr_ratio REAL,
              suspicious_garbled_ratio REAL,
              references_detected INTEGER,
              warnings TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS answer_citations (
              id TEXT PRIMARY KEY,
              answer_id TEXT NOT NULL,
              source_type TEXT NOT NULL,
              claim_text TEXT,
              chunk_id TEXT,
              ref_num INTEGER,
              verified INTEGER NOT NULL DEFAULT 0,
              verifier_score REAL,
              status TEXT,
              created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_chunks_paper ON chunks(paper_id);
            CREATE INDEX IF NOT EXISTS idx_papers_deleted ON papers(deleted);
            CREATE INDEX IF NOT EXISTS idx_parse_reports_paper ON parse_reports(paper_id);
            CREATE INDEX IF NOT EXISTS idx_answer_citations_answer ON answer_citations(answer_id);
            CREATE INDEX IF NOT EXISTS idx_summaries_paper ON summaries(paper_id);
            """
        )
        _migrate_schema(conn)


def _migrate_schema(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(chunks)").fetchall()}
    if "scholar_embedding_json" not in cols:
        conn.execute("ALTER TABLE chunks ADD COLUMN scholar_embedding_json TEXT")

    paper_cols = {row[1] for row in conn.execute("PRAGMA table_info(papers)").fetchall()}
    if "zotero_tags" not in paper_cols:
        conn.execute("ALTER TABLE papers ADD COLUMN zotero_tags TEXT")
    if "zotero_collections" not in paper_cols:
        conn.execute("ALTER TABLE papers ADD COLUMN zotero_collections TEXT")
    if "status_message" not in paper_cols:
        conn.execute("ALTER TABLE papers ADD COLUMN status_message TEXT")
    if "parse_quality_score" not in paper_cols:
        conn.execute("ALTER TABLE papers ADD COLUMN parse_quality_score REAL")

    chunk_cols = {row[1] for row in conn.execute("PRAGMA table_info(chunks)").fetchall()}
    if "chunk_type" not in chunk_cols:
        conn.execute("ALTER TABLE chunks ADD COLUMN chunk_type TEXT DEFAULT 'unknown'")
    if "chunk_quality_score" not in chunk_cols:
        conn.execute("ALTER TABLE chunks ADD COLUMN chunk_quality_score REAL")
    if "content_hash" not in chunk_cols:
        conn.execute("ALTER TABLE chunks ADD COLUMN content_hash TEXT")
    if "section_path_json" not in chunk_cols:
        conn.execute("ALTER TABLE chunks ADD COLUMN section_path_json TEXT")

    task_cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    if "payload_json" not in task_cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN payload_json TEXT")
    if "progress_json" not in task_cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN progress_json TEXT")
    if "result_json" not in task_cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN result_json TEXT")


def load_kv(key: str, default: str | None = None) -> str | None:
    with get_db() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        if row:
            return row["value"]
    return default


def save_kv(key: str, value: str) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO app_settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_zotero_storage_path() -> Path:
    raw = load_kv("zotero_storage_path")
    if raw:
        return Path(raw).expanduser()
    return Path(settings.zotero_storage_path).expanduser()


def set_zotero_storage_path(p: Path) -> None:
    save_kv("zotero_storage_path", str(p.expanduser()))


def row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


def json_dumps_safe(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
