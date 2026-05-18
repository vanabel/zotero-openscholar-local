"""超算批处理：MinerU/pypdf 解析 PDF → parsed/document.md（不写入 chunk/嵌入）。"""

from __future__ import annotations

import asyncio

from app.config import settings
from app.db import get_db
from app.pipeline_logging import plog_info
from app.services.hpc_pdf_path import resolve_pdf_path
from app.services.indexing import index_paper
from app.services.pdf_parse import load_parsed_markdown, parsed_pdf_sha256
from app.services.zotero_scanner import get_paper


def _paper_needs_parse(paper_id: str, *, force: bool) -> bool:
    if force:
        return True
    paper = get_paper(paper_id)
    if not paper:
        return False
    out_dir = settings.parsed_dir / paper_id
    loaded = load_parsed_markdown(out_dir)
    if loaded is None:
        return True
    pdf_sha = (paper.get("sha256") or "").strip()
    stored_sha = parsed_pdf_sha256(out_dir)
    if pdf_sha and stored_sha and stored_sha != pdf_sha:
        return True
    return False


def list_paper_ids_for_parse(*, missing_only: bool) -> list[str]:
    with get_db() as conn:
        rows = conn.execute("SELECT id FROM papers WHERE deleted = 0 ORDER BY id").fetchall()
    out: list[str] = []
    for r in rows:
        pid = str(r["id"])
        paper = get_paper(pid)
        if not paper:
            continue
        if resolve_pdf_path(str(paper.get("pdf_path") or "")) is None:
            continue
        if missing_only and not _paper_needs_parse(pid, force=False):
            continue
        out.append(pid)
    return out


async def parse_paper(paper_id: str, *, force: bool = False) -> dict:
    paper = get_paper(paper_id)
    if not paper or paper.get("deleted"):
        return {"ok": False, "paper_id": paper_id, "error": "文献不存在或已归档"}

    stored = str(paper.get("pdf_path") or "")
    pdf_path = resolve_pdf_path(stored)
    if pdf_path is None:
        return {
            "ok": False,
            "paper_id": paper_id,
            "error": (
                "PDF 文件不存在。请 rsync Zotero storage 并在 .env.hpc 设置 ZOTERO_STORAGE_PATH；"
                f"库内路径={stored}"
            ),
        }

    if not force and not _paper_needs_parse(paper_id, force=False):
        loaded = load_parsed_markdown(settings.parsed_dir / paper_id)
        return {
            "ok": True,
            "paper_id": paper_id,
            "skipped": True,
            "message": "已有 parsed/document.md 且 PDF 未变更",
            "pdf_path": str(pdf_path),
            "markdown_chars": len(loaded[0]) if loaded else 0,
        }

    plog_info("parse", "parse_batch paper_id=%s pdf=%s", paper_id, pdf_path)
    return await index_paper(paper_id, force=force, parse_only=True)


async def run_parse_batch(paper_ids: list[str], *, force: bool = False) -> dict:
    ok = fail = skip = 0
    errors: list[dict] = []
    for pid in paper_ids:
        res = await parse_paper(pid, force=force)
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
