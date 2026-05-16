from __future__ import annotations

import re

from app.services.answer_records import new_answer_id, save_answer_citations

_CITE_NUM_RE = re.compile(r"\[(\d+)\]")
_SENT_SPLIT = re.compile(r"(?<=[。！？.!?])\s*")

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


def split_claims(text: str) -> list[str]:
    """按句号等切分论断句，过滤过短片段。"""
    raw = (text or "").strip()
    if not raw:
        return []
    parts = _SENT_SPLIT.split(raw)
    claims: list[str] = []
    for p in parts:
        s = p.strip()
        if not s:
            continue
        if re.fullmatch(r"(\[\d+\])+", s) and claims:
            claims[-1] = f"{claims[-1]} {s}".strip()
            continue
        if len(s) < 8:
            continue
        if len(s) < 12 and not extract_citation_refs(s):
            continue
        if s.startswith("（注：") or s.startswith("(Note:"):
            continue
        claims.append(s)
    if not claims and len(raw) >= 12:
        claims = [raw]
    return claims


def _claim_keywords(claim: str) -> set[str]:
    words = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", (claim or "").lower()))
    for w in list(words):
        if w in ("the", "and", "that", "with", "this", "from", "have", "were", "which"):
            words.discard(w)
    return words


def _keyword_overlap(claim: str, evidence: str) -> float:
    words = _claim_keywords(claim)
    if not words:
        return 0.0
    ev = (evidence or "").lower()
    hits = sum(1 for w in words if w in ev)
    return hits / len(words)


def verify_claims(
    answer: str,
    contexts: list[dict],
    *,
    lang: str = "zh",
    min_overlap: float = 0.12,
) -> tuple[list[dict], dict]:
    """
    对每个 claim 检查 [n] 引用与证据关键词重叠。
    返回 claim 记录列表与汇总 meta。
    """
    n_ctx = len(contexts)
    records: list[dict] = []
    claims = split_claims(answer)

    verified_n = 0
    insufficient_n = 0
    invalid_n = 0

    for claim_text in claims:
        refs = extract_citation_refs(claim_text)
        if not refs:
            if len(claim_text) > 60:
                records.append(
                    {
                        "claim_text": claim_text,
                        "chunk_id": None,
                        "ref_num": None,
                        "verified": False,
                        "verifier_score": 0.0,
                        "status": "unreferenced",
                    }
                )
                insufficient_n += 1
            continue

        best_score = 0.0
        best_chunk: str | None = None
        best_ref: int | None = None
        status = "insufficient"

        for ref in refs:
            if ref < 1 or ref > n_ctx:
                invalid_n += 1
                records.append(
                    {
                        "claim_text": claim_text,
                        "chunk_id": None,
                        "ref_num": ref,
                        "verified": False,
                        "verifier_score": 0.0,
                        "status": "invalid_ref",
                    }
                )
                continue
            ctx = contexts[ref - 1]
            score = _keyword_overlap(claim_text, ctx.get("text") or "")
            if score > best_score:
                best_score = score
                best_chunk = str(ctx.get("chunk_id") or "")
                best_ref = ref

        if best_ref is not None:
            ok = best_score >= min_overlap
            status = "verified" if ok else "insufficient"
            if ok:
                verified_n += 1
            else:
                insufficient_n += 1
            records.append(
                {
                    "claim_text": claim_text,
                    "chunk_id": best_chunk,
                    "ref_num": best_ref,
                    "verified": ok,
                    "verifier_score": round(best_score, 4),
                    "status": status,
                }
            )

    meta = {
        "ok": invalid_n == 0 and insufficient_n == 0 and verified_n > 0,
        "claims_total": len(claims),
        "claims_verified": verified_n,
        "claims_insufficient": insufficient_n,
        "claims_invalid_ref": invalid_n,
        "context_count": n_ctx,
    }
    return records, meta


def verify_citations(
    answer: str,
    contexts: list[dict],
    *,
    lang: str = "zh",
    persist: bool = False,
    source_type: str = "chat",
) -> tuple[str, dict]:
    """
    校验 [n] 是否落在 1..len(contexts)；移除越界引用。
    完整版：claim 拆分 + 关键词重叠校验 + 可选写入 answer_citations。
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

    claim_records, claim_meta = verify_claims(cleaned, contexts, lang=lang)

    if not valid and len((cleaned or "").strip()) > 80:
        if lang == "zh":
            tail = "\n\n（提示：上文部分论断未标注 [n] 引用，请结合下方证据片段核对。）"
        else:
            tail = "\n\n(Note: some statements above lack [n] citations; verify against the evidence list.)"
        if tail not in cleaned:
            cleaned = cleaned.rstrip() + tail

    answer_id = new_answer_id() if persist else None
    if persist and answer_id and claim_records:
        save_answer_citations(answer_id, source_type, claim_records)

    enriched_citations = []
    for i, c in enumerate(contexts, start=1):
        related = [r for r in claim_records if r.get("ref_num") == i]
        verified_any = any(r.get("verified") for r in related)
        enriched_citations.append(
            {
                "ref": i,
                "chunk_id": c.get("chunk_id"),
                "paper_id": c.get("paper_id"),
                "verification_status": "verified" if verified_any else ("unused" if not related else "insufficient"),
            }
        )

    meta = {
        "ok": len(invalid) == 0 and claim_meta.get("claims_insufficient", 0) == 0,
        "valid_refs": valid,
        "invalid_refs": invalid,
        "context_count": n_ctx,
        "answer_id": answer_id,
        "claims": claim_records,
        "claim_summary": claim_meta,
        "citation_status": enriched_citations,
    }
    return cleaned, meta


def enrich_citations_payload(citations: list[dict], citation_check: dict) -> list[dict]:
    """将 verification_status 合并进 API citations 列表。"""
    status_by_ref = {
        int(s["ref"]): s.get("verification_status")
        for s in (citation_check.get("citation_status") or [])
        if s.get("ref") is not None
    }
    out = []
    for c in citations:
        row = dict(c)
        ref = row.get("ref")
        if ref in status_by_ref:
            row["verification_status"] = status_by_ref[ref]
        else:
            row["verification_status"] = "unused"
        out.append(row)
    return out
