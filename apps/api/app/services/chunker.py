from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

from app.services.section_path import (
    dumps_section_path_json,
    section_path_display,
    split_markdown_sections_structured,
)


def estimate_tokens(text: str) -> int:
    # 粗略：中英混合文献用字符/4 近似 token
    return max(1, int(len(text) / 4))


def split_markdown_sections(md: str) -> list[tuple[str, str]]:
    """按标题切分为 (section_path 显示串, body)。兼容旧测试与 stable_chunk_id。"""
    return [
        (section_path_display(None, dumps_section_path_json(parts)), body)
        for parts, body in split_markdown_sections_structured(md)
    ]


@dataclass
class ChunkDraft:
    section_title: str
    section_path: str
    section_path_json: str
    chunk_index: int
    text: str
    page_start: int | None
    page_end: int | None


def _page_hints_from_text(text: str) -> tuple[int | None, int | None]:
    pages = [int(x) for x in re.findall(r"\bpage\s*[:#]?\s*(\d+)\b", text, flags=re.I)]
    if not pages:
        return None, None
    return min(pages), max(pages)


def chunk_markdown(md: str, max_chars: int = 3500, overlap: int = 400) -> list[ChunkDraft]:
    """结构优先 + 长度上限：先按标题分块，再按字符切分并重叠。"""
    out: list[ChunkDraft] = []
    idx = 0
    for path_parts, body in split_markdown_sections_structured(md):
        path_json = dumps_section_path_json(path_parts)
        section_path = section_path_display(None, path_json)
        section_title = path_parts[-1] if path_parts else "全文"
        if len(body) <= max_chars:
            ps, pe = _page_hints_from_text(body)
            out.append(
                ChunkDraft(
                    section_title=section_title,
                    section_path=section_path,
                    section_path_json=path_json,
                    chunk_index=idx,
                    text=body,
                    page_start=ps,
                    page_end=pe,
                )
            )
            idx += 1
            continue
        start = 0
        while start < len(body):
            end = min(len(body), start + max_chars)
            piece = body[start:end]
            ps, pe = _page_hints_from_text(piece)
            out.append(
                ChunkDraft(
                    section_title=section_title,
                    section_path=section_path,
                    section_path_json=path_json,
                    chunk_index=idx,
                    text=piece.strip(),
                    page_start=ps,
                    page_end=pe,
                )
            )
            idx += 1
            if end >= len(body):
                break
            start = max(0, end - overlap)
    return out


def cosine_sim(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def stable_chunk_id(paper_id: str, section_path: str, chunk_index: int) -> str:
    raw = f"{paper_id}|{section_path}|{chunk_index}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
