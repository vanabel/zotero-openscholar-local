"""MinerU 云端 zip 已生成但 CDN 下载失败时，仅重试下载（不重传 PDF）。"""

from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.pipeline_logging import plog_info
from app.services.mineru_cloud import (
    MINERU_PENDING_FILENAME,
    MinerUCloudError,
    _prefix_relative_asset_urls,
    finish_mineru_download_from_pending,
    load_mineru_download_pending,
)


def mineru_pending_path(out_dir: Path) -> Path:
    return out_dir / MINERU_PENDING_FILENAME


def has_mineru_download_pending(out_dir: Path) -> bool:
    return load_mineru_download_pending(out_dir) is not None


def list_mineru_download_pending_out_dirs(paper_out_dir: Path) -> list[Path]:
    """根目录或 _mineru_cloud_chunks/NNN/ 下存在 mineru_pending.json 的目录。"""
    found: list[Path] = []
    if has_mineru_download_pending(paper_out_dir):
        found.append(paper_out_dir)
    chunks_root = paper_out_dir / "_mineru_cloud_chunks"
    if chunks_root.is_dir():
        for sub in sorted(chunks_root.iterdir()):
            if sub.is_dir() and has_mineru_download_pending(sub):
                found.append(sub)
    return found


def paper_has_mineru_download_pending(paper_id: str) -> bool:
    out_dir = settings.parsed_dir / paper_id
    return bool(list_mineru_download_pending_out_dirs(out_dir))


def list_mineru_download_pending_paper_ids(*, limit: int | None = None) -> list[str]:
    root = settings.parsed_dir
    if not root.is_dir():
        return []
    out: list[str] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if list_mineru_download_pending_out_dirs(child):
            out.append(child.name)
            if limit is not None and len(out) >= limit:
                break
    return out


def _merge_chunked_markdown(paper_out_dir: Path) -> tuple[str, dict]:
    chunks_root = paper_out_dir / "_mineru_cloud_chunks"
    chunk_dirs = sorted(
        [p for p in chunks_root.iterdir() if p.is_dir() and (p / "document.md").is_file()],
        key=lambda p: p.name,
    )
    if not chunk_dirs:
        raise MinerUCloudError("分段目录无可用 document.md，无法合并")
    md_parts: list[str] = []
    meta: dict = {"mode": "mineru_cloud_chunked", "mineru": True, "mineru_chunked": True}
    for sub in chunk_dirs:
        ci = sub.name
        try:
            idx = int(ci)
        except ValueError:
            idx = len(md_parts)
        rel_prefix = f"_mineru_cloud_chunks/{sub.name}/"
        md_i = (sub / "document.md").read_text(encoding="utf-8", errors="replace")
        md_parts.append(
            f"## 分段 {idx + 1}\n\n" + _prefix_relative_asset_urls(md_i, rel_prefix)
        )
        pending = load_mineru_download_pending(sub)
        if pending and pending.get("batch_id"):
            meta[f"mineru_batch_id_{ci}"] = pending["batch_id"]

    full_md = "\n\n---\n\n".join(md_parts)
    (paper_out_dir / "document.md").write_text(full_md, encoding="utf-8")
    plog_info(
        "parse",
        "MinerU 云端分段合并完成 chunks=%s md_chars=%s",
        len(chunk_dirs),
        len(full_md),
    )
    return full_md, meta


def retry_mineru_cloud_download(paper_id: str) -> tuple[str, dict]:
    """
    对 paper 下所有 mineru_pending.json 仅重试 CDN 下载；分段模式在全部切片完成后合并。
    返回 (markdown, meta)。
    """
    paper_out_dir = settings.parsed_dir / paper_id
    pending_dirs = list_mineru_download_pending_out_dirs(paper_out_dir)
    if not pending_dirs:
        raise MinerUCloudError(
            "无待重试的 MinerU 下载记录（mineru_pending.json）。"
            "若此前版本失败，请使用「重试解析」重新提交云端任务。"
        )

    chunks_root = paper_out_dir / "_mineru_cloud_chunks"
    is_chunked = chunks_root.is_dir() and any(
        p.parent == chunks_root for p in pending_dirs if p != paper_out_dir
    )

    for d in pending_dirs:
        plog_info("parse", "MinerU 仅重试下载 paper_id=%s dir=%s", paper_id, d)
        finish_mineru_download_from_pending(d)

    if is_chunked or (chunks_root.is_dir() and any((chunks_root / s).is_dir() for s in ("000", "001"))):
        return _merge_chunked_markdown(paper_out_dir)

    md = (paper_out_dir / "document.md").read_text(encoding="utf-8", errors="replace")
    meta_path = paper_out_dir / "meta.json"
    meta: dict = {"mode": "mineru_cloud", "mineru": True, "mineru_download_retried": True}
    if meta_path.is_file():
        try:
            prev = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(prev, dict):
                meta = {**prev, **meta}
        except (OSError, json.JSONDecodeError):
            pass
    return md, meta
