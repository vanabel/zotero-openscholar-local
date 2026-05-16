from __future__ import annotations

import hashlib
import re
from typing import Literal

ChunkType = Literal[
    "abstract",
    "introduction",
    "definition",
    "theorem",
    "proof",
    "method",
    "experiment",
    "discussion",
    "conclusion",
    "references",
    "unknown",
]

_REF_SECTION = re.compile(
    r"\b(references|bibliography|参考文献|引用文献|works cited)\b", flags=re.I
)
_ABSTRACT = re.compile(r"\b(abstract|摘要)\b", flags=re.I)
_INTRO = re.compile(r"\b(introduction|引言|前言)\b", flags=re.I)
_CONCLUSION = re.compile(r"\b(conclusion|conclusions|结论)\b", flags=re.I)
_MATH_BLOCK = re.compile(
    r"\b(definition|lemma|proposition|theorem|corollary|remark|proof|example)\b", flags=re.I
)
_METHOD = re.compile(r"\b(method|methods|methodology|方法)\b", flags=re.I)
_EXPERIMENT = re.compile(r"\b(experiment|experiments|实验|数值)\b", flags=re.I)
_DISCUSSION = re.compile(r"\b(discussion|讨论)\b", flags=re.I)


def content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def classify_chunk_type(section_path: str, text: str) -> ChunkType:
    path = section_path or ""
    head = path.split(" / ")[-1] if path else ""
    probe = f"{path} {head} {(text or '')[:400]}"
    if _REF_SECTION.search(probe):
        return "references"
    if _ABSTRACT.search(probe):
        return "abstract"
    if _INTRO.search(probe):
        return "introduction"
    if _CONCLUSION.search(probe):
        return "conclusion"
    if _METHOD.search(probe):
        return "method"
    if _EXPERIMENT.search(probe):
        return "experiment"
    if _DISCUSSION.search(probe):
        return "discussion"
    m = _MATH_BLOCK.search(probe)
    if m:
        word = m.group(1).lower()
        if word == "proof":
            return "proof"
        if word == "definition":
            return "definition"
        return "theorem"
    return "unknown"


def score_chunk(text: str, chunk_type: str) -> float:
    t = (text or "").strip()
    n = len(t)
    if n < 40:
        return 0.2
    score = 0.55
    if re.search(r"[。．.!?？]", t):
        score += 0.15
    if chunk_type == "references" and n > 200:
        score -= 0.25
    if chunk_type in ("theorem", "definition", "proof") and ("$" in t or "\\" in t):
        score += 0.1
    if n > 8000:
        score -= 0.1
    return max(0.0, min(1.0, round(score, 4)))


def dedupe_chunk_drafts(drafts: list) -> list:
    """索引级去重：相同 content_hash 只保留首个。"""
    seen: set[str] = set()
    out: list = []
    for d in drafts:
        h = content_hash(d.text)
        if h in seen:
            continue
        seen.add(h)
        out.append(d)
    return out
