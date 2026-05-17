from __future__ import annotations

import json
import re


def section_path_display(path: str | None, path_json: str | None = None) -> str:
    """人类可读章节路径（优先 JSON 数组，否则字符串）。"""
    parts = section_path_parts(path, path_json)
    if parts:
        return " › ".join(parts)
    return (path or "").strip()


def section_path_parts(path: str | None, path_json: str | None = None) -> list[str]:
    parsed = parse_section_path_json(path_json)
    if parsed:
        return parsed
    raw = (path or "").strip()
    if not raw:
        return []
    if " / " in raw:
        return [p.strip() for p in raw.split(" / ") if p.strip()]
    return [raw]


def parse_section_path_json(raw: str | None) -> list[str] | None:
    if not raw or not str(raw).strip():
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, list):
        return None
    out: list[str] = []
    for item in data:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out or None


def dumps_section_path_json(parts: list[str]) -> str:
    return json.dumps([p.strip() for p in parts if p and p.strip()], ensure_ascii=False)


def format_page_range(page_start: int | None, page_end: int | None) -> str:
    if page_start is None and page_end is None:
        return ""
    if page_start is not None and page_end is not None and page_end != page_start:
        return f"第 {page_start}–{page_end} 页"
    p = page_start if page_start is not None else page_end
    return f"第 {p} 页" if p is not None else ""


def format_chunk_source(
    *,
    title: str | None = None,
    section_title: str | None = None,
    section_path: str | None = None,
    section_path_json: str | None = None,
    page_start: int | None = None,
    page_end: int | None = None,
) -> str:
    """引用卡片一行来源描述。"""
    bits: list[str] = []
    sec = section_path_display(section_path, section_path_json)
    if not sec and section_title:
        sec = section_title.strip()
    if sec:
        bits.append(sec)
    page = format_page_range(page_start, page_end)
    if page:
        bits.append(page)
    if bits:
        return " · ".join(bits)
    return ""


def heading_stack_to_path(stack: list[tuple[int, str]]) -> list[str]:
    return [t for _, t in stack if t.strip()]


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def split_markdown_sections_structured(md: str) -> list[tuple[list[str], str]]:
    """按标题层级切分，返回 (section_path_parts, body)。"""
    lines = md.splitlines()
    sections: list[tuple[list[str], list[str]]] = []
    stack: list[tuple[int, str]] = []
    current: list[str] = []

    def flush():
        nonlocal current
        if current:
            path = heading_stack_to_path(stack) or ["全文"]
            sections.append((path, current))
            current = []

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            flush()
            level = len(m.group(1))
            title = m.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            continue
        current.append(line)
    flush()

    if not sections:
        body = md.strip()
        return [(["全文"], body)] if body else []
    return [
        (path, "\n".join(body).strip())
        for path, body in sections
        if "\n".join(body).strip()
    ]
