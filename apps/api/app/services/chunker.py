from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass


def estimate_tokens(text: str) -> int:
    # 粗略：中英混合文献用字符/4 近似 token
    return max(1, int(len(text) / 4))


def split_markdown_sections(md: str) -> list[tuple[str, str]]:
    """按一级/二级标题切分为 (section_path, body)。"""
    lines = md.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_title = "全文"
    current: list[str] = []

    heading_re = re.compile(r"^(#{1,3})\s+(.+?)\s*$")

    def flush():
        nonlocal current
        if current:
            sections.append((current_title, current))
            current = []

    for line in lines:
        m = heading_re.match(line)
        if m:
            flush()
            level = len(m.group(1))
            title = m.group(2).strip()
            current_title = title if level <= 2 else f"{current_title} / {title}"
            current = []
            continue
        current.append(line)
    flush()

    if not sections:
        return [("全文", md.strip())]
    return [(t, "\n".join(body).strip()) for t, body in sections if "\n".join(body).strip()]


@dataclass
class ChunkDraft:
    section_title: str
    section_path: str
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
    for section_path, body in split_markdown_sections(md):
        if len(body) <= max_chars:
            ps, pe = _page_hints_from_text(body)
            out.append(
                ChunkDraft(
                    section_title=section_path.split(" / ")[-1],
                    section_path=section_path,
                    chunk_index=idx,
                    text=body,
                    page_start=ps,
                    page_end=pe,
                )
            )
            idx += 1
            continue
        start = 0
        sub = 0
        while start < len(body):
            end = min(len(body), start + max_chars)
            piece = body[start:end]
            ps, pe = _page_hints_from_text(piece)
            out.append(
                ChunkDraft(
                    section_title=section_path.split(" / ")[-1],
                    section_path=section_path,
                    chunk_index=idx,
                    text=piece.strip(),
                    page_start=ps,
                    page_end=pe,
                )
            )
            idx += 1
            sub += 1
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
