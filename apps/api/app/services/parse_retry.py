"""解析质量过低时自动用 MinerU 云端 / 备用 model 重试。"""

from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.pipeline_logging import plog_info
from app.services.pdf_parse import clear_parsed_output_dir
from app.services.task_runtime import mineru_parse_semaphore


def _cloud_token_ready() -> bool:
    return bool((settings.mineru_api_token or "").strip())


def _retry_model_for_mode(mode: str) -> str | None:
    primary = (settings.mineru_cloud_model_version or "vlm").strip() or "vlm"
    retry = (settings.mineru_cloud_model_version_retry or "pipeline").strip() or "pipeline"
    if mode.startswith("mineru_cloud"):
        return retry if retry != primary else None
    return primary


async def maybe_retry_low_quality_parse(
    paper_id: str,
    pdf_path: Path,
    out_dir: Path,
    md: str,
    meta: dict,
    report: dict,
    *,
    force: bool,
) -> tuple[str, dict, dict]:
    """
    若质量分低于阈值且尚未重试，尝试 MinerU 云端（或云端备用 model）。
    返回 (md, meta, report)。
    """
    if not settings.parse_quality_retry_enabled:
        return md, meta, report
    if meta.get("low_quality_retried"):
        return md, meta, report

    score = float(report.get("parse_quality_score") or 0)
    threshold = float(settings.parse_quality_retry_threshold)
    if score >= threshold:
        return md, meta, report

    mode = str(meta.get("mode") or "")
    warnings = report.get("warnings") or []
    ocr_bad = "high_ocr_fragment_ratio" in warnings or mode.startswith("pypdf")
    if not ocr_bad and score >= threshold * 0.85:
        return md, meta, report

    if not _cloud_token_ready():
        plog_info(
            "parse",
            "质量分 %.3f < %.3f 但未配置 MINERU_API_TOKEN，跳过低分重试 paper_id=%s",
            score,
            threshold,
            paper_id,
        )
        return md, meta, report

    retry_model = _retry_model_for_mode(mode)
    if not retry_model and not ocr_bad:
        return md, meta, report

    plog_info(
        "parse",
        "低分重试 paper_id=%s score=%.3f mode=%s → cloud model=%s",
        paper_id,
        score,
        mode,
        retry_model or settings.mineru_cloud_model_version,
    )

    import asyncio

    cleared = clear_parsed_output_dir(out_dir)
    plog_info("parse", "低分重试已清空解析目录 %s（%s 项）", out_dir, cleared)

    try:
        async with mineru_parse_semaphore():
            new_md, new_meta = await asyncio.to_thread(
                _parse_cloud_retry,
                paper_id,
                pdf_path,
                out_dir,
                model_version=retry_model,
            )
    except Exception as e:
        plog_info("parse", "低分重试失败，保留首次解析: %s", e)
        return md, meta, report

    from app.services.clean_markdown import clean_markdown
    from app.services.parse_quality import analyze_markdown

    new_md = clean_markdown(new_md)
    (out_dir / "document.md").write_text(new_md, encoding="utf-8")
    new_meta["low_quality_retried"] = True
    new_meta["low_quality_retry_from_score"] = score
    new_meta["low_quality_retry_from_mode"] = mode
    (out_dir / "meta.json").write_text(json.dumps(new_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    new_report = analyze_markdown(
        new_md,
        parser=str(new_meta.get("mode") or "mineru_cloud"),
        parser_mode=new_meta.get("parser_mode"),
    )
    plog_info(
        "parse",
        "低分重试完成 paper_id=%s 新分=%.3f",
        paper_id,
        new_report.get("parse_quality_score"),
    )
    return new_md, new_meta, new_report


def _parse_cloud_retry(
    paper_id: str,
    pdf_path: Path,
    out_dir: Path,
    *,
    model_version: str | None,
) -> tuple[str, dict]:
    from app.services.mineru_cloud import MinerUCloudError, parse_pdf_via_cloud_with_splitting

    try:
        md, meta = parse_pdf_via_cloud_with_splitting(
            pdf_path,
            paper_id,
            out_dir,
            force_reparse=True,
            model_version=model_version,
        )
        meta["mode"] = "mineru_cloud_retry"
        return md, meta
    except MinerUCloudError as e:
        plog_info("parse", "低分云端重试失败，保留首次解析结果: %s", e)
        raise
    except Exception:
        raise
