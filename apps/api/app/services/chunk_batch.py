"""从 data/parsed 下 Markdown 分块写入 chunks，不计算嵌入（供超算后续 embed_batch / scholar_embed_batch）。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.db import get_db
from app.pipeline_logging import plog_info
from app.services.chunk_quality import dedupe_chunk_drafts
from app.services.chunker import chunk_markdown
from app.services.indexing import _chunk_count, save_paper_chunks
from app.services.pdf_parse import load_parsed_markdown, sha256_text
from app.services.zotero_scanner import get_paper


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_paper_ids_for_chunk(*, missing_only: bool) -> list[str]:
    with get_db() as conn:
        rows = conn.execute("SELECT id FROM papers WHERE deleted = 0 ORDER BY id").fetchall()
    out: list[str] = []
    for r in rows:
        pid = str(r["id"])
        if load_parsed_markdown(settings.parsed_dir / pid) is None:
            continue
        if missing_only and _chunk_count(pid) > 0:
            continue
        out.append(pid)
    return out


def chunk_paper_from_parsed(
    paper_id: str,
    *,
    force: bool = False,
) -> dict:
    paper = get_paper(paper_id)
    if not paper or paper.get("deleted"):
        return {"ok": False, "paper_id": paper_id, "error": "文献不存在或已归档"}

    out_dir = settings.parsed_dir / paper_id
    loaded = load_parsed_markdown(out_dir)
    if loaded is None:
        return {
            "ok": False,
            "paper_id": paper_id,
            "error": "无本地 Markdown，请先在 Mac 完成解析并同步 parsed/",
        }

    if not force and _chunk_count(paper_id) > 0:
        return {
            "ok": True,
            "paper_id": paper_id,
            "chunks": _chunk_count(paper_id),
            "updated": 0,
            "skipped": True,
            "message": "已有 chunk（使用 --force 可强制重新分块）",
        }

    md, _path = loaded
    md_hash = sha256_text(md)
    drafts = dedupe_chunk_drafts(chunk_markdown(md))
    if not drafts:
        return {"ok": False, "paper_id": paper_id, "error": "Markdown 分块结果为空"}

    n = len(drafts)
    null_emb: list[None] = [None] * n
    with get_db() as conn:
        chunk_ids = save_paper_chunks(
            conn,
            paper_id,
            drafts,
            null_emb,
            null_emb,
            md_hash=md_hash,
            prune_stale=force,
        )

    pdf_path = Path(str(paper.get("pdf_path") or ""))
    plog_info(
        "index",
        "chunk_batch paper_id=%s chunks=%s pdf_local=%s",
        paper_id,
        len(chunk_ids),
        pdf_path.is_file(),
    )
    return {
        "ok": True,
        "paper_id": paper_id,
        "chunks": len(chunk_ids),
        "updated": len(chunk_ids),
        "markdown_hash": md_hash,
    }


def run_chunk_batch(paper_ids: list[str], *, force: bool = False) -> dict:
    ok = fail = skip = 0
    errors: list[dict] = []
    for pid in paper_ids:
        res = chunk_paper_from_parsed(pid, force=force)
        if res.get("ok") and res.get("skipped"):
            skip += 1
        elif res.get("ok"):
            ok += 1
        else:
            fail += 1
            errors.append({"paper_id": pid, "error": res.get("error") or "失败"})
    return {
        "ok": fail == 0,
        "total": len(paper_ids),
        "succeeded": ok,
        "skipped": skip,
        "failed": fail,
        "errors": errors[:50],
    }
