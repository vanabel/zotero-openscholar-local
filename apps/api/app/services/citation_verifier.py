from __future__ import annotations

import re

_CITE_NUM_RE = re.compile(r"\[(\d+)\]")

NO_EVIDENCE_ANSWER_ZH = (
    "当前知识库中未检索到足够证据支持该结论。请尝试换一个问题，或先完成文献扫描与「建立索引」。"
)
NO_EVIDENCE_ANSWER_EN = (
    "The knowledge base does not contain sufficient evidence to support an answer. "
    "Try rephrasing your question, or scan and index your library first."
)


def no_evidence_answer(lang: str) -> str:
    return NO_EVIDENCE_ANSWER_EN if lang == "en" else NO_EVIDENCE_ANSWER_ZH


def extract_citation_refs(text: str) -> list[int]:
    return [int(m) for m in _CITE_NUM_RE.findall(text or "")]


def verify_citations(
    answer: str,
    contexts: list[dict],
    *,
    lang: str = "zh",
) -> tuple[str, dict]:
    """
    校验 [n] 是否落在 1..len(contexts)；移除越界引用并附简短说明。
    若完全无引用且正文较长，追加提示（最小版，不拆 claim）。
    """
    n_ctx = len(contexts)
    if n_ctx == 0:
        return no_evidence_answer(lang), {"ok": False, "reason": "no_contexts", "invalid_refs": [], "valid_refs": []}

    refs = extract_citation_refs(answer)
    valid = sorted({r for r in refs if 1 <= r <= n_ctx})
    invalid = sorted({r for r in refs if r < 1 or r > n_ctx})

    cleaned = answer
    for bad in invalid:
        cleaned = cleaned.replace(f"[{bad}]", "")

    note = ""
    if invalid:
        if lang == "zh":
            note = f"\n\n（注：已移除无效引用编号 {invalid}，有效证据编号为 1–{n_ctx}。）"
        else:
            note = f"\n\n(Note: removed invalid citation(s) {invalid}; valid refs are 1–{n_ctx}.)"
        cleaned = (cleaned.rstrip() + note).strip()

    if not valid and len((cleaned or "").strip()) > 80:
        if lang == "zh":
            tail = "\n\n（提示：上文部分论断未标注 [n] 引用，请结合下方证据片段核对。）"
        else:
            tail = "\n\n(Note: some statements above lack [n] citations; verify against the evidence list.)"
        if tail not in cleaned:
            cleaned = cleaned.rstrip() + tail

    meta = {
        "ok": len(invalid) == 0,
        "valid_refs": valid,
        "invalid_refs": invalid,
        "context_count": n_ctx,
    }
    return cleaned, meta
