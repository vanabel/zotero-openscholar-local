from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone

from app.db import get_db
from app.services.chunker import split_markdown_sections


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _garbled_ratio(text: str) -> float:
    if not text:
        return 0.0
    bad = sum(1 for c in text if ord(c) < 9 or (0xE000 <= ord(c) <= 0xF8FF))
    return bad / max(len(text), 1)


def _ocr_heuristic_ratio(text: str) -> float:
    """孤立单字符行占比，粗略表示 OCR 碎片。"""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return 0.0
    singles = sum(1 for ln in lines if len(ln) <= 2 and not ln.isdigit())
    return singles / len(lines)


def analyze_markdown(md: str, *, parser: str = "unknown", parser_mode: str | None = None) -> dict:
    text = md or ""
    sections = split_markdown_sections(text)
    page_nums = [int(x) for x in re.findall(r"\bpage\s*[:#]?\s*(\d+)\b", text, flags=re.I)]
    formula_blocks = len(re.findall(r"\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]", text))
    table_blocks = len(re.findall(r"^\|.+\|$", text, flags=re.M))
    image_blocks = len(re.findall(r"!\[[^\]]*\]\([^)]+\)", text))
    garbled = _garbled_ratio(text)
    ocr_ratio = _ocr_heuristic_ratio(text)
    refs_detected = any(
        re.search(r"\b(references|bibliography|参考文献|引用文献)\b", t, flags=re.I) for t, _ in sections
    )
    text_len = len(text)
    section_n = len(sections)

    warnings: list[str] = []
    if text_len < 800:
        warnings.append("markdown_too_short")
    if garbled > 0.02:
        warnings.append("high_garbled_ratio")
    if ocr_ratio > 0.25:
        warnings.append("high_ocr_fragment_ratio")
    if section_n < 2 and text_len > 5000:
        warnings.append("few_sections")

    # 0–1 质量分：长度、结构、公式/表、乱码与 OCR 惩罚
    len_score = min(1.0, text_len / 12000.0)
    struct_score = min(1.0, section_n / 8.0)
    rich_score = min(1.0, (formula_blocks + table_blocks + image_blocks) / 20.0)
    penalty = min(0.5, garbled * 8 + ocr_ratio * 0.8)
    score = max(0.0, min(1.0, 0.35 * len_score + 0.35 * struct_score + 0.2 * rich_score + 0.1 - penalty))
    if refs_detected:
        score = min(1.0, score + 0.03)

    return {
        "parse_quality_score": round(score, 4),
        "text_length": text_len,
        "page_count": max(page_nums) if page_nums else None,
        "detected_sections": section_n,
        "formula_blocks": formula_blocks,
        "table_blocks": table_blocks,
        "image_blocks": image_blocks,
        "ocr_ratio": round(ocr_ratio, 4),
        "suspicious_garbled_ratio": round(garbled, 4),
        "references_detected": refs_detected,
        "warnings": warnings,
        "parser": parser,
        "parser_mode": parser_mode,
    }


def latest_parse_report(paper_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT * FROM parse_reports
            WHERE paper_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (paper_id,),
        ).fetchone()
    if not row:
        return None
    out = dict(row)
    try:
        out["warnings"] = json.loads(out.get("warnings") or "[]")
    except json.JSONDecodeError:
        out["warnings"] = []
    return out


def save_parse_report(paper_id: str, report: dict) -> str:
    rid = uuid.uuid4().hex
    now = _utc_now()
    warnings_json = json.dumps(report.get("warnings") or [], ensure_ascii=False)
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO parse_reports(
              id, paper_id, parser, parser_mode, parse_quality_score,
              text_length, page_count, detected_sections, formula_blocks,
              table_blocks, image_blocks, ocr_ratio, suspicious_garbled_ratio,
              references_detected, warnings, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                rid,
                paper_id,
                report.get("parser") or "unknown",
                report.get("parser_mode"),
                report.get("parse_quality_score"),
                report.get("text_length"),
                report.get("page_count"),
                report.get("detected_sections"),
                report.get("formula_blocks"),
                report.get("table_blocks"),
                report.get("image_blocks"),
                report.get("ocr_ratio"),
                report.get("suspicious_garbled_ratio"),
                1 if report.get("references_detected") else 0,
                warnings_json,
                now,
            ),
        )
        conn.execute(
            "UPDATE papers SET parse_quality_score = ?, updated_at = ? WHERE id = ?",
            (report.get("parse_quality_score"), now, paper_id),
        )
    return rid


def report_id_for_paper(paper_id: str) -> str:
    return hashlib.sha256(f"parse:{paper_id}".encode()).hexdigest()[:32]
