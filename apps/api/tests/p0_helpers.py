"""P0 最小回归集：加载 fixture、写入 DB、mock 嵌入。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.db import get_db, init_db
from app.services.chunker import chunk_markdown
from app.services.indexing import index_paper

FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures" / "papers"
MANIFEST_PATH = FIXTURES_ROOT / "manifest.json"


def fixture_paper_id(fixture_id: str) -> str:
    return hashlib.sha256(fixture_id.encode("utf-8")).hexdigest()[:32]


def load_manifest() -> list[dict]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_fixture_paper(fixture_id: str, tmp_data_dir: Path) -> str:
    """将 fixture 的 document.md 写入 parsed 目录并在 papers 表建行。"""
    paper_id = fixture_paper_id(fixture_id)
    md_path = FIXTURES_ROOT / fixture_id / "document.md"
    if not md_path.is_file():
        raise FileNotFoundError(md_path)

    out_dir = tmp_data_dir / "parsed" / paper_id
    out_dir.mkdir(parents=True, exist_ok=True)
    md = md_path.read_text(encoding="utf-8")
    (out_dir / "document.md").write_text(md, encoding="utf-8")
    meta_src = FIXTURES_ROOT / fixture_id / "metadata.json"
    if meta_src.is_file():
        meta = json.loads(meta_src.read_text(encoding="utf-8"))
        meta["fixture_id"] = fixture_id
        meta["mode"] = "p0_fixture"
        (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    pdf = tmp_data_dir / f"{fixture_id}.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    if not pdf.is_file():
        pdf.write_bytes(b"%PDF-1.4 p0-fixture")

    now = _utc_now()
    title = fixture_id
    first = md.splitlines()[0] if md else ""
    if first.startswith("# "):
        title = first[2:].strip()
    elif first.startswith("## ") and not first.startswith("## Page"):
        title = first[3:].strip()

    with get_db() as conn:
        conn.execute("DELETE FROM chunks_fts WHERE paper_id = ?", (paper_id,))
        conn.execute("DELETE FROM chunks WHERE paper_id = ?", (paper_id,))
        conn.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
        conn.execute(
            """
            INSERT INTO papers(
              id, title, pdf_path, file_name, file_size, mtime, sha256,
              parse_status, index_status, deleted, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                paper_id,
                title,
                str(pdf),
                pdf.name,
                pdf.stat().st_size,
                1.0,
                hashlib.sha256(fixture_id.encode()).hexdigest(),
                "parsed",
                "pending",
                0,
                now,
                now,
            ),
        )
    return paper_id


async def index_fixture(fixture_id: str, tmp_data_dir: Path) -> dict:
    paper_id = seed_fixture_paper(fixture_id, tmp_data_dir)
    return await index_paper(paper_id, force=False, reindex_only=True)


def chunk_drafts_for(fixture_id: str) -> list:
    md = (FIXTURES_ROOT / fixture_id / "document.md").read_text(encoding="utf-8")
    return chunk_markdown(md)
