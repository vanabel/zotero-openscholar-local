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
from app.services.llm import LLMClient, build_citation_prompt, try_embed_one
from app.services.retriever import retrieve_for_query, retrieve_limits
from app.services.translation import (
    expand_query_for_retrieval,
    stream_translate_sse_events,
    translate_answer_to,
    translation_for_answer_enabled,
    translation_for_retrieval_enabled,
)


def _citations_payload(contexts: list[dict]) -> list[dict]:
    return [
        {
            "ref": i + 1,
            "chunk_id": c["chunk_id"],
            "paper_id": c["paper_id"],
            "title": c.get("title"),
            "section_path": c.get("section_path"),
            "preview": (c["text"][:280] + "…") if len(c["text"]) > 280 else c["text"],
        }
        for i, c in enumerate(contexts)
    ]


async def _extra_retrieval_queries(question: str) -> list[str] | None:
    if not translation_for_retrieval_enabled():
        return None
    zh, en = await expand_query_for_retrieval(question)
    extra: list[str] = []
    for s in (zh, en):
        if s and s.strip():
            extra.append(s.strip())
    return extra or None


async def answer_with_citations(question: str, lang: str = "zh", *, use_cache: bool = True) -> dict:
    if use_cache:
        hit = get_cached_answer(question, lang)
        if hit is not None:
            return hit
    t0 = time.monotonic()
    plog_info("rag", "answer 开始 lang=%s 问题预览=%s", lang, clip(question, 160))
    qvec = await try_embed_one(question)
    plog_info("rag", "query 嵌入: %s", "有" if qvec else "无")
    extra_q = await _extra_retrieval_queries(question)
    if extra_q:
        plog_info("rag", "双语检索扩展 queries=%s", len(extra_q) + 1)
    k_fts, k_final = retrieve_limits()
    contexts = await retrieve_for_query(
        question, top_k_fts=k_fts, top_k_final=k_final, query_vec=qvec, extra_queries=extra_q
    )
    plog_info("rag", "retrieve 完成 候选片段=%s 耗时=%.2fs", len(contexts), time.monotonic() - t0)
    if not contexts:
        plog_info("rag", "answer 中止：无检索片段")
        return {
            "answer": "知识库中暂无匹配片段。请先「扫描」Zotero 目录，并对文献执行「建立索引」。",
            "citations": [],
        }

    for i, c in enumerate(contexts[:8], start=1):
        plog_debug("rag", "  context[%s] paper=%s chunk=%s title=%s", i, c.get("paper_id"), c.get("chunk_id"), clip(str(c.get("title") or ""), 80))

    llm = LLMClient()
    messages = build_citation_prompt(question, contexts, lang=lang)
    t1 = time.monotonic()
    answer = await llm.chat(messages, temperature=0.2)
    plog_info("rag", "answer LLM 完成 耗时=%.2fs", time.monotonic() - t1)
    citations = _citations_payload(contexts)
    answer_other: str | None = None
    answer_other_lang: str | None = None
    if translation_for_answer_enabled():
        alt: str = "en" if lang == "zh" else "zh"
        plog_info("rag", "自动翻译 开始 target=%s", alt)
        answer_other = await translate_answer_to(answer, alt)  # type: ignore[arg-type]
        answer_other_lang = alt if answer_other else None
        plog_info("rag", "自动翻译 结束 target=%s ok=%s", alt, bool(answer_other))
    plog_info("rag", "answer 总耗时=%.2fs 引用条数=%s", time.monotonic() - t0, len(citations))
    out: dict = {"answer": answer, "citations": citations, "contexts_used": len(contexts)}
    if answer_other:
        out["answer_other"] = answer_other
        out["answer_other_lang"] = answer_other_lang
    if use_cache:
        put_cached_answer(question, lang, out)
    return out


async def answer_with_citations_stream(
    question: str, lang: str = "zh", *, use_cache: bool = True
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
    qvec = await try_embed_one(question)
    extra_q = await _extra_retrieval_queries(question)
    if extra_q:
        plog_info("rag", "answer_stream 双语检索扩展 queries=%s", len(extra_q) + 1)
    k_fts, k_final = retrieve_limits()
    contexts = await retrieve_for_query(
        question, top_k_fts=k_fts, top_k_final=k_final, query_vec=qvec, extra_queries=extra_q
    )
    plog_info("rag", "answer_stream retrieve 完成 片段=%s 耗时=%.2fs", len(contexts), time.monotonic() - t0)
    if not contexts:
        plog_info("rag", "answer_stream 中止：无检索片段")
        yield {
            "type": "error",
            "message": "知识库中暂无匹配片段。请先「扫描」Zotero 目录，并对文献执行「建立索引」。",
        }
        return

    yield {
        "type": "citations",
        "citations": _citations_payload(contexts),
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
            "citations": _citations_payload(contexts),
            "contexts_used": len(contexts),
        }
        if answer_other and answer_other_lang:
            cached["answer_other"] = answer_other
            cached["answer_other_lang"] = answer_other_lang
        put_cached_answer(question, lang, cached)


def _review_query(topic: str, focus: str | None) -> str:
    return topic if not focus else f"{topic}。重点：{focus}"


def _build_review_messages(
    topic: str, focus: str | None, contexts: list[dict], lang: str
) -> list[dict[str, str]]:
    blocks = []
    for i, c in enumerate(contexts, start=1):
        blocks.append(
            f"[{i}] paper_id={c['paper_id']} chunk_id={c['chunk_id']}\n"
            f"标题: {c.get('title') or '未知'}\n"
            f"章节: {c.get('section_path') or ''}\n"
            f"片段:\n{c['text']}\n"
        )
    ctx = "\n\n".join(blocks)
    if lang == "zh":
        sys = (
            "你是资深综述作者。请基于证据撰写结构化中文文献综述，"
            "包含：背景与问题、主要方法与结果脉络、异同与争议、开放问题。"
            "每个关键论断末尾用 [n] 引用编号。不要编造证据之外的内容。"
        )
        user = f"综述主题：{topic}\n补充说明：{focus or '无'}\n\n证据片段：\n{ctx}"
    else:
        sys = "Write a structured mini literature review with citations [n] only from evidence."
        user = f"Topic: {topic}\nNotes: {focus or ''}\n\nEvidence:\n{ctx}"
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


async def write_literature_review(
    topic: str,
    focus: str | None = None,
    lang: str = "zh",
    *,
    use_cache: bool = True,
) -> dict:
    if use_cache:
        hit = get_cached_review(topic, focus, lang)
        if hit is not None:
            return hit
    q = _review_query(topic, focus)
    t0 = time.monotonic()
    plog_info("review", "review 开始 lang=%s 主题=%s", lang, clip(q, 200))
    qvec = await try_embed_one(q)
    extra_q = await _extra_retrieval_queries(q)
    k_fts, k_final = retrieve_limits()
    contexts = await retrieve_for_query(
        q, top_k_fts=k_fts, top_k_final=k_final, query_vec=qvec, extra_queries=extra_q
    )
    plog_info("review", "retrieve 完成 片段=%s 耗时=%.2fs", len(contexts), time.monotonic() - t0)
    if not contexts:
        return {
            "review": "未检索到相关文献片段。请先完成扫描与索引。",
            "citations": [],
        }

    llm = LLMClient()
    messages = _build_review_messages(topic, focus, contexts, lang)
    t1 = time.monotonic()
    review = await llm.chat(messages, temperature=0.35)
    plog_info("review", "review LLM 完成 耗时=%.2fs 输出字符=%s", time.monotonic() - t1, len(review or ""))
    citations = _citations_payload(contexts)
    out = {"review": review, "citations": citations, "contexts_used": len(contexts)}
    if use_cache:
        put_cached_review(topic, focus, lang, out)
    return out


async def write_literature_review_stream(
    topic: str,
    focus: str | None = None,
    lang: str = "zh",
    *,
    use_cache: bool = True,
) -> AsyncIterator[dict]:
    if use_cache:
        hit = get_cached_review(topic, focus, lang)
        if hit is not None:
            for ev in stream_review_events_from_payload(hit):
                yield ev
            return
    q = _review_query(topic, focus)
    t0 = time.monotonic()
    plog_info("review", "review_stream 开始 lang=%s 主题=%s", lang, clip(q, 200))
    qvec = await try_embed_one(q)
    extra_q = await _extra_retrieval_queries(q)
    k_fts, k_final = retrieve_limits()
    contexts = await retrieve_for_query(
        q, top_k_fts=k_fts, top_k_final=k_final, query_vec=qvec, extra_queries=extra_q
    )
    plog_info("review", "review_stream retrieve 完成 片段=%s 耗时=%.2fs", len(contexts), time.monotonic() - t0)
    if not contexts:
        yield {
            "type": "error",
            "message": "未检索到相关文献片段。请先完成扫描与索引。",
        }
        return

    yield {
        "type": "citations",
        "citations": _citations_payload(contexts),
        "contexts_used": len(contexts),
    }
    llm = LLMClient()
    messages = _build_review_messages(topic, focus, contexts, lang)
    t1 = time.monotonic()
    buf: list[str] = []
    async for piece in llm.chat_stream(messages, temperature=0.35):
        buf.append(piece)
        yield {"type": "token", "t": piece}
    plog_info("review", "review_stream LLM 结束 耗时=%.2fs", time.monotonic() - t1)
    full = "".join(buf)
    yield {"type": "done"}
    if use_cache and full.strip():
        put_cached_review(
            topic,
            focus,
            lang,
            {
                "review": full,
                "citations": _citations_payload(contexts),
                "contexts_used": len(contexts),
            },
        )
