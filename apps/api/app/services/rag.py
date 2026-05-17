from __future__ import annotations

import time
from collections.abc import AsyncIterator

from app.pipeline_logging import clip, plog_debug, plog_info
from app.services.chat_cache import (
    get_cached_answer,
    put_cached_answer,
    stream_events_from_payload,
)
from app.services.review_cache import (
    get_cached_review,
    put_cached_review,
    stream_events_from_payload as stream_review_events_from_payload,
)
from app.services.citation_verifier import (
    enrich_citations_payload,
    no_evidence_answer,
    verify_citations,
)
from app.services.llm import LLMClient, build_citation_prompt, try_embed_one
from app.services.retrieval_scope import RetrievalScope, scope_from_request
from app.services.retriever import retrieve_for_query, retrieve_limits
from app.services.review_templates import ReviewTemplate, build_review_messages, review_to_markdown
from app.services.summaries import retrieve_summaries_for_query, summaries_to_pseudo_contexts
from app.services.query_synonyms import expand_query_with_synonyms
from app.services.section_path import format_chunk_source
from app.services.translation import (
    expand_query_for_retrieval,
    stream_translate_sse_events,
    translate_answer_to,
    translation_for_answer_enabled,
    translation_for_retrieval_enabled,
)


def _citations_payload(contexts: list[dict]) -> list[dict]:
    out: list[dict] = []
    for i, c in enumerate(contexts):
        source = format_chunk_source(
            title=c.get("title"),
            section_title=c.get("section_title"),
            section_path=c.get("section_path"),
            section_path_json=c.get("section_path_json"),
            page_start=c.get("page_start"),
            page_end=c.get("page_end"),
        )
        out.append(
            {
                "ref": i + 1,
                "chunk_id": c["chunk_id"],
                "paper_id": c["paper_id"],
                "title": c.get("title"),
                "section_title": c.get("section_title"),
                "section_path": c.get("section_path"),
                "section_path_json": c.get("section_path_json"),
                "page_start": c.get("page_start"),
                "page_end": c.get("page_end"),
                "source": source,
                "chunk_type": c.get("chunk_type"),
                "preview": (c["text"][:280] + "…") if len(c["text"]) > 280 else c["text"],
            }
        )
    return out


async def _retrieve_contexts(
    question: str,
    *,
    scope: RetrievalScope | None,
    use_summaries: bool = False,
    include_references: bool = False,
) -> list[dict]:
    qvec = await try_embed_one(question)
    extra_q = await _extra_retrieval_queries(question)
    k_fts, k_final = retrieve_limits()
    summary_ctx: list[dict] = []
    if use_summaries:
        sums = retrieve_summaries_for_query(question, limit=max(3, k_final // 2), scope=scope)
        summary_ctx = summaries_to_pseudo_contexts(sums)
        if summary_ctx:
            plog_info("rag", "summaries 命中=%s", len(summary_ctx))
    chunk_k = k_final if not summary_ctx else max(k_final, k_final + len(summary_ctx))
    chunks = await retrieve_for_query(
        question,
        top_k_fts=k_fts,
        top_k_final=chunk_k,
        query_vec=qvec,
        extra_queries=extra_q,
        scope=scope,
        include_references=include_references,
    )
    if summary_ctx:
        # summaries 编号在前，chunks 续编
        n = len(summary_ctx)
        renumbered: list[dict] = []
        for i, c in enumerate(chunks, start=n + 1):
            row = dict(c)
            row["_orig_ref"] = i
            renumbered.append(row)
        return summary_ctx + renumbered[:k_final]
    return chunks[:k_final]


async def _extra_retrieval_queries(question: str) -> list[str] | None:
    extra: list[str] = []
    seen = {question.strip().lower()}
    for s in expand_query_with_synonyms(question):
        key = s.lower()
        if key not in seen:
            seen.add(key)
            extra.append(s)
    if translation_for_retrieval_enabled():
        zh, en = await expand_query_for_retrieval(question)
        for s in (zh, en):
            if s and s.strip():
                key = s.strip().lower()
                if key not in seen:
                    seen.add(key)
                    extra.append(s.strip())
    return extra or None


def _build_scope(
    *,
    paper_ids: list[str] | None,
    tags: list[str] | None,
    collections: list[str] | None,
    years_min: int | None,
    years_max: int | None,
    include_references: bool,
) -> RetrievalScope | None:
    return scope_from_request(
        paper_ids=paper_ids,
        tags=tags,
        collections=collections,
        years_min=years_min,
        years_max=years_max,
        include_references=include_references,
    )


async def answer_with_citations(
    question: str,
    lang: str = "zh",
    *,
    use_cache: bool = True,
    paper_ids: list[str] | None = None,
    tags: list[str] | None = None,
    collections: list[str] | None = None,
    years_min: int | None = None,
    years_max: int | None = None,
) -> dict:
    if use_cache:
        hit = get_cached_answer(question, lang)
        if hit is not None:
            return hit
    t0 = time.monotonic()
    plog_info("rag", "answer 开始 lang=%s 问题预览=%s", lang, clip(question, 160))
    scope = _build_scope(
        paper_ids=paper_ids,
        tags=tags,
        collections=collections,
        years_min=years_min,
        years_max=years_max,
        include_references=False,
    )
    contexts = await _retrieve_contexts(question, scope=scope)
    plog_info("rag", "retrieve 完成 候选片段=%s 耗时=%.2fs", len(contexts), time.monotonic() - t0)
    if not contexts:
        plog_info("rag", "answer 中止：无检索片段")
        return {
            "answer": no_evidence_answer(lang),
            "citations": [],
            "citation_check": {"ok": False, "reason": "no_contexts"},
            "claims": [],
        }

    for i, c in enumerate(contexts[:8], start=1):
        plog_debug("rag", "  context[%s] paper=%s chunk=%s title=%s", i, c.get("paper_id"), c.get("chunk_id"), clip(str(c.get("title") or ""), 80))

    llm = LLMClient()
    messages = build_citation_prompt(question, contexts, lang=lang)
    t1 = time.monotonic()
    answer = await llm.chat(messages, temperature=0.2)
    plog_info("rag", "answer LLM 完成 耗时=%.2fs", time.monotonic() - t1)
    answer, citation_check = verify_citations(answer, contexts, lang=lang, persist=True, source_type="chat")
    citations = enrich_citations_payload(_citations_payload(contexts), citation_check)
    answer_other: str | None = None
    answer_other_lang: str | None = None
    if translation_for_answer_enabled():
        alt: str = "en" if lang == "zh" else "zh"
        plog_info("rag", "自动翻译 开始 target=%s", alt)
        answer_other = await translate_answer_to(answer, alt)  # type: ignore[arg-type]
        answer_other_lang = alt if answer_other else None
        plog_info("rag", "自动翻译 结束 target=%s ok=%s", alt, bool(answer_other))
    plog_info("rag", "answer 总耗时=%.2fs 引用条数=%s", time.monotonic() - t0, len(citations))
    out: dict = {
        "answer": answer,
        "citations": citations,
        "contexts_used": len(contexts),
        "citation_check": citation_check,
        "claims": citation_check.get("claims") or [],
        "answer_id": citation_check.get("answer_id"),
    }
    if answer_other:
        out["answer_other"] = answer_other
        out["answer_other_lang"] = answer_other_lang
    if use_cache:
        put_cached_answer(question, lang, out)
    return out


async def answer_with_citations_stream(
    question: str,
    lang: str = "zh",
    *,
    use_cache: bool = True,
    paper_ids: list[str] | None = None,
    tags: list[str] | None = None,
    collections: list[str] | None = None,
    years_min: int | None = None,
    years_max: int | None = None,
) -> AsyncIterator[dict]:
    """先推送 citations，再逐段 token，最后 done。"""
    if use_cache:
        hit = get_cached_answer(question, lang)
        if hit is not None:
            for ev in stream_events_from_payload(hit):
                yield ev
            return
    t0 = time.monotonic()
    plog_info("rag", "answer_stream 开始 lang=%s 问题预览=%s", lang, clip(question, 160))
    scope = _build_scope(
        paper_ids=paper_ids,
        tags=tags,
        collections=collections,
        years_min=years_min,
        years_max=years_max,
        include_references=False,
    )
    contexts = await _retrieve_contexts(question, scope=scope)
    plog_info("rag", "answer_stream retrieve 完成 片段=%s 耗时=%.2fs", len(contexts), time.monotonic() - t0)
    if not contexts:
        plog_info("rag", "answer_stream 中止：无检索片段")
        yield {
            "type": "error",
            "message": no_evidence_answer(lang),
            "code": "no_evidence",
        }
        return

    citations = enrich_citations_payload(_citations_payload(contexts), {"citation_status": []})
    yield {
        "type": "citations",
        "citations": citations,
        "contexts_used": len(contexts),
    }
    llm = LLMClient()
    messages = build_citation_prompt(question, contexts, lang=lang)
    t1 = time.monotonic()
    buf: list[str] = []
    async for piece in llm.chat_stream(messages, temperature=0.2):
        buf.append(piece)
        yield {"type": "token", "t": piece}
    plog_info("rag", "answer_stream LLM 流结束 耗时=%.2fs", time.monotonic() - t1)
    full = "".join(buf)
    full, citation_check = verify_citations(full, contexts, lang=lang, persist=True, source_type="chat")
    citations = enrich_citations_payload(_citations_payload(contexts), citation_check)
    yield {"type": "citations", "citations": citations, "contexts_used": len(contexts)}
    yield {"type": "citation_check", "citation_check": citation_check}
    yield {"type": "claims", "claims": citation_check.get("claims") or []}
    answer_other: str | None = None
    answer_other_lang: str | None = None
    if translation_for_answer_enabled() and full.strip():
        alt: str = "en" if lang == "zh" else "zh"
        plog_info("rag", "answer_stream 自动翻译流式 开始 target=%s", alt)
        answer_other = None
        answer_other_lang = alt
        async for ev in stream_translate_sse_events(full, alt):  # type: ignore[arg-type]
            if ev.get("type") == "bilingual" and ev.get("text"):
                answer_other = str(ev["text"])
            yield ev
        plog_info("rag", "answer_stream 自动翻译流式 结束 ok=%s", bool(answer_other))
    yield {"type": "done"}
    if use_cache:
        cached: dict = {
            "answer": full,
            "citations": citations,
            "contexts_used": len(contexts),
            "citation_check": citation_check,
            "claims": citation_check.get("claims") or [],
            "answer_id": citation_check.get("answer_id"),
        }
        if answer_other and answer_other_lang:
            cached["answer_other"] = answer_other
            cached["answer_other_lang"] = answer_other_lang
        put_cached_answer(question, lang, cached)


def _review_query(topic: str, focus: str | None) -> str:
    return topic if not focus else f"{topic}。重点：{focus}"


async def write_literature_review(
    topic: str,
    focus: str | None = None,
    lang: str = "zh",
    *,
    use_cache: bool = True,
    template: ReviewTemplate = "literature_review",
    paper_ids: list[str] | None = None,
    tags: list[str] | None = None,
    collections: list[str] | None = None,
    years_min: int | None = None,
    years_max: int | None = None,
) -> dict:
    if use_cache:
        hit = get_cached_review(topic, focus, lang, template=template)
        if hit is not None:
            return hit
    q = _review_query(topic, focus)
    t0 = time.monotonic()
    plog_info("review", "review 开始 lang=%s 主题=%s", lang, clip(q, 200))
    scope = _build_scope(
        paper_ids=paper_ids,
        tags=tags,
        collections=collections,
        years_min=years_min,
        years_max=years_max,
        include_references=True,
    )
    contexts = await _retrieve_contexts(q, scope=scope, use_summaries=True, include_references=True)
    plog_info("review", "retrieve 完成 片段=%s 耗时=%.2fs", len(contexts), time.monotonic() - t0)
    if not contexts:
        return {
            "review": no_evidence_answer(lang),
            "citations": [],
            "citation_check": {"ok": False, "reason": "no_contexts"},
            "claims": [],
        }

    llm = LLMClient()
    messages = build_review_messages(topic, focus, contexts, lang, template=template)
    t1 = time.monotonic()
    review = await llm.chat(messages, temperature=0.35)
    plog_info("review", "review LLM 完成 耗时=%.2fs 输出字符=%s", time.monotonic() - t1, len(review or ""))
    review, citation_check = verify_citations(review, contexts, lang=lang, persist=True, source_type="review")
    citations = enrich_citations_payload(_citations_payload(contexts), citation_check)
    out = {
        "review": review,
        "citations": citations,
        "contexts_used": len(contexts),
        "citation_check": citation_check,
        "template": template,
        "claims": citation_check.get("claims") or [],
        "answer_id": citation_check.get("answer_id"),
    }
    if use_cache:
        put_cached_review(topic, focus, lang, out, template=template)
    return out


async def write_literature_review_stream(
    topic: str,
    focus: str | None = None,
    lang: str = "zh",
    *,
    use_cache: bool = True,
    template: ReviewTemplate = "literature_review",
    paper_ids: list[str] | None = None,
    tags: list[str] | None = None,
    collections: list[str] | None = None,
    years_min: int | None = None,
    years_max: int | None = None,
) -> AsyncIterator[dict]:
    if use_cache:
        hit = get_cached_review(topic, focus, lang, template=template)
        if hit is not None:
            for ev in stream_review_events_from_payload(hit):
                yield ev
            return
    q = _review_query(topic, focus)
    t0 = time.monotonic()
    plog_info("review", "review_stream 开始 lang=%s 主题=%s", lang, clip(q, 200))
    scope = _build_scope(
        paper_ids=paper_ids,
        tags=tags,
        collections=collections,
        years_min=years_min,
        years_max=years_max,
        include_references=True,
    )
    contexts = await _retrieve_contexts(q, scope=scope, use_summaries=True, include_references=True)
    plog_info("review", "review_stream retrieve 完成 片段=%s 耗时=%.2fs", len(contexts), time.monotonic() - t0)
    if not contexts:
        yield {
            "type": "error",
            "message": no_evidence_answer(lang),
            "code": "no_evidence",
        }
        return

    yield {
        "type": "citations",
        "citations": _citations_payload(contexts),
        "contexts_used": len(contexts),
    }
    llm = LLMClient()
    messages = build_review_messages(topic, focus, contexts, lang, template=template)
    t1 = time.monotonic()
    buf: list[str] = []
    async for piece in llm.chat_stream(messages, temperature=0.35):
        buf.append(piece)
        yield {"type": "token", "t": piece}
    plog_info("review", "review_stream LLM 结束 耗时=%.2fs", time.monotonic() - t1)
    full = "".join(buf)
    full, citation_check = verify_citations(full, contexts, lang=lang, persist=True, source_type="review")
    citations = enrich_citations_payload(_citations_payload(contexts), citation_check)
    yield {"type": "citation_check", "citation_check": citation_check}
    yield {"type": "claims", "claims": citation_check.get("claims") or []}
    yield {"type": "citations", "citations": citations, "contexts_used": len(contexts)}
    yield {"type": "done"}
    if use_cache and full.strip():
        put_cached_review(
            topic,
            focus,
            lang,
            {
                "review": full,
                "citations": citations,
                "contexts_used": len(contexts),
                "citation_check": citation_check,
                "template": template,
                "claims": citation_check.get("claims") or [],
                "answer_id": citation_check.get("answer_id"),
            },
            template=template,
        )


async def export_review_markdown(
    topic: str,
    focus: str | None = None,
    lang: str = "zh",
    *,
    template: ReviewTemplate = "literature_review",
    use_cache: bool = True,
    paper_ids: list[str] | None = None,
    tags: list[str] | None = None,
    collections: list[str] | None = None,
    years_min: int | None = None,
    years_max: int | None = None,
) -> str:
    data = await write_literature_review(
        topic,
        focus=focus,
        lang=lang,
        use_cache=use_cache,
        template=template,
        paper_ids=paper_ids,
        tags=tags,
        collections=collections,
        years_min=years_min,
        years_max=years_max,
    )
    return review_to_markdown(
        data.get("review") or "",
        topic,
        data.get("citations") or [],
        template=template,
        lang=lang,
    )


async def export_review_docx(
    topic: str,
    focus: str | None = None,
    lang: str = "zh",
    *,
    template: ReviewTemplate = "literature_review",
    use_cache: bool = True,
    paper_ids: list[str] | None = None,
    tags: list[str] | None = None,
    collections: list[str] | None = None,
    years_min: int | None = None,
    years_max: int | None = None,
) -> bytes:
    from app.services.export_docx import review_to_docx_bytes

    data = await write_literature_review(
        topic,
        focus=focus,
        lang=lang,
        use_cache=use_cache,
        template=template,
        paper_ids=paper_ids,
        tags=tags,
        collections=collections,
        years_min=years_min,
        years_max=years_max,
    )
    return review_to_docx_bytes(
        data.get("review") or "",
        topic,
        data.get("citations") or [],
        template=template,
        lang=lang,
    )
