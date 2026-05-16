"""MinerU / pypdf 产出 Markdown 的轻量清洗（页眉页脚、断行、参考文献区）。"""

from __future__ import annotations

import re
from collections import Counter

_REF_HEADING = re.compile(
    r"^(#+\s*)?(references|bibliography|works\s+cited|参考文献|引用文献|文献目录)\s*$",
    re.I,
)
_PAGE_NUM_ONLY = re.compile(r"^\s*\d{1,4}\s*$")
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")


def _normalize_line(line: str) -> str:
    s = line.strip()
    s = re.sub(r"\s+", " ", s)
    return s


def strip_repeated_header_footer_lines(md: str, *, min_repeats: int = 4) -> str:
    """删除在文中重复出现多次的短行（常见页眉/页脚）。"""
    lines = md.splitlines()
    if len(lines) < min_repeats * 3:
        return md
    normed = [_normalize_line(ln) for ln in lines]
    counts: Counter[str] = Counter(n for n in normed if 8 <= len(n) <= 80)
    repeated = {k for k, c in counts.items() if c >= min_repeats}
    if not repeated:
        return md
    out: list[str] = []
    for ln, n in zip(lines, normed, strict=True):
        if n in repeated and len(n) <= 80:
            continue
        out.append(ln)
    return "\n".join(out)


def fix_hyphenation_line_breaks(md: str) -> str:
    """合并英文连字符断行：inter-\n national → international。"""
    return _HYPHEN_BREAK.sub(r"\1\2", md)


def drop_isolated_page_numbers(md: str) -> str:
    lines = md.splitlines()
    out = [ln for ln in lines if not _PAGE_NUM_ONLY.match(ln)]
    return "\n".join(out)


def trim_references_section(md: str, *, keep: bool = False) -> str:
    """默认保留参考文献区（供 references chunk）；keep=False 时截断其后内容。"""
    if keep:
        return md
    lines = md.splitlines()
    cut: int | None = None
    for i, ln in enumerate(lines):
        if _REF_HEADING.match(ln.strip()):
            cut = i
            break
    if cut is None:
        return md
    return "\n".join(lines[:cut]).rstrip() + "\n"


def clean_markdown(md: str, *, keep_references: bool = True) -> str:
    text = md or ""
    if not text.strip():
        return text
    text = fix_hyphenation_line_breaks(text)
    text = drop_isolated_page_numbers(text)
    text = strip_repeated_header_footer_lines(text)
    text = trim_references_section(text, keep=keep_references)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip() + ("\n" if text.strip() else "")
