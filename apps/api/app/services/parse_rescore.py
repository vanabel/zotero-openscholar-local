"""基于已有 document.md 补写解析质量分（不跑 MinerU、不重建索引）。"""

from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.pipeline_logging import plog_info
from app.services.parse_quality import analyze_markdown, save_parse_report
from app.services.pdf_parse import load_parsed_markdown
from app.services.zotero_scanner import get_paper


def list_unscored_with_markdown_ids(*, limit: int | None = None) -> list[str]:
    """parse_quality_score 为 NULL 且存在可读的 document.md。"""
    from app.db import get_db

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id FROM papers
            WHERE deleted = 0 AND parse_quality_score IS NULL
            ORDER BY updated_at DESC
            """
        ).fetchall()
    out: list[str] = []
    for r in rows:
        pid = str(r["id"])
        if load_parsed_markdown(settings.parsed_dir / pid) is None:
            continue
        out.append(pid)
        if limit is not None and len(out) >= limit:
            break
    return out


def _parser_from_meta(out_dir: Path) -> tuple[str, str | None]:
    meta_path = out_dir / "meta.json"
    if not meta_path.is_file():
        return "cached_markdown", None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if isinstance(meta, dict):
            return str(meta.get("mode") or "cached_markdown"), meta.get("parser_mode")
    except (OSError, json.JSONDecodeError):
        pass
    return "cached_markdown", None


def rescore_paper_parse_quality(paper_id: str) -> dict:
    """
    读取本地 Markdown，运行 analyze_markdown 并写入 parse_reports + papers.parse_quality_score。
    不调用 MinerU，不修改 chunks / 嵌入。
    """
    paper = get_paper(paper_id)
    if not paper or paper.get("deleted"):
        return {"ok": False, "error": "文献不存在或已归档"}

    out_dir = settings.parsed_dir / paper_id
    loaded = load_parsed_markdown(out_dir)
    if loaded is None:
        return {
            "ok": False,
            "error": "无 document.md，请先建立索引或解析；不能仅补评分",
        }

    md, _path = loaded
    parser, parser_mode = _parser_from_meta(out_dir)
    report = analyze_markdown(md, parser=parser, parser_mode=parser_mode)
    report_id = save_parse_report(paper_id, report)
    plog_info(
        "parse",
        "补写质量分 paper_id=%s score=%.3f parser=%s",
        paper_id,
        report.get("parse_quality_score") or 0,
        parser,
    )
    return {
        "ok": True,
        "paper_id": paper_id,
        "parse_quality_score": report.get("parse_quality_score"),
        "report_id": report_id,
        "parser": parser,
    }


def rescore_batch(paper_ids: list[str]) -> dict:
    results: list[dict] = []
    ok = fail = 0
    for pid in paper_ids:
        res = rescore_paper_parse_quality(pid)
        results.append(res)
        if res.get("ok"):
            ok += 1
        else:
            fail += 1
    body: dict = {
        "ok": fail == 0,
        "matched": len(paper_ids),
        "scored": ok,
        "failed": fail,
    }
    if len(results) <= 50:
        body["results"] = results
    else:
        body["results_sample"] = results[:5]
        errs = [r for r in results if not r.get("ok")]
        if errs:
            body["error_sample"] = errs[:3]
    return body
