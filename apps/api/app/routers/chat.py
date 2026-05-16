import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.services.chat_cache import clear_cached_translation, get_cached_answer, list_recent_questions
from app.services.rag import answer_with_citations, answer_with_citations_stream
from app.services.translation import (
    stream_translate_sse_events,
    translate_answer_to,
    translation_model_configured,
)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=8000)
    lang: str = "zh"
    use_cache: bool = True
    paper_ids: list[str] | None = Field(None, max_length=50)
    tags: list[str] | None = Field(None, max_length=30, description="Zotero 标签，命中任一即纳入")
    collections: list[str] | None = Field(None, max_length=30, description="Zotero 集合名，命中任一即纳入")
    years_min: int | None = Field(None, ge=1900, le=2100)
    years_max: int | None = Field(None, ge=1900, le=2100)


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=120000)
    target_lang: str = Field(..., pattern="^(zh|en)$")


class ClearTranslationCacheRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=8000)
    lang: str = Field(default="zh", pattern="^(zh|en)$")


@router.get("/recent")
def chat_recent(
    lang: str = Query("zh", pattern="^(zh|en)$"),
    limit: int = Query(10, ge=1, le=30),
):
    """近期提问（随机顺序），供问答页快捷填入。"""
    items = list_recent_questions(lang, limit=limit)
    return {
        "items": items,
        "cache_enabled": settings.chat_cache_enabled,
        "lang": lang,
    }


@router.post("/cache/clear-translation")
def chat_clear_translation_cache(req: ClearTranslationCacheRequest):
    """清除当前问题在问答缓存中的译文（主答与引用保留）。"""
    if not settings.chat_cache_enabled:
        return {"cleared": False, "cache_enabled": False}
    cleared = clear_cached_translation(req.question, req.lang)
    return {"cleared": cleared, "cache_enabled": True}


@router.get("/cache")
def chat_cache_lookup(
    question: str = Query(..., min_length=1, max_length=8000),
    lang: str = Query("zh", pattern="^(zh|en)$"),
):
    """按问题与语言读取有效缓存（索引/模型配置未变）。"""
    hit = get_cached_answer(question, lang)
    if hit is None:
        raise HTTPException(status_code=404, detail="无有效缓存")
    return hit


@router.post("")
async def chat(req: ChatRequest):
    return await answer_with_citations(
        req.question,
        lang=req.lang,
        use_cache=req.use_cache,
        paper_ids=req.paper_ids,
        tags=req.tags,
        collections=req.collections,
        years_min=req.years_min,
        years_max=req.years_max,
    )


@router.post("/translate")
async def chat_translate(req: TranslateRequest):
    """按需将已有回答译为 zh 或 en（不重新检索/生成）。"""
    if not translation_model_configured():
        raise HTTPException(
            status_code=503,
            detail="未配置翻译模型。请在 apps/api/.env 设置 TRANSLATION_OLLAMA_MODEL（并确保 Ollama 已加载该模型）。",
        )
    target = req.target_lang  # zh | en
    out = await translate_answer_to(req.text, target)  # type: ignore[arg-type]
    if not out:
        raise HTTPException(status_code=502, detail="翻译失败或返回为空，请查看 API 日志（PIPELINE_LOG=1 LOG_STAGES=translate）。")
    return {"text": out, "target_lang": target}


@router.post("/translate/stream")
async def chat_translate_stream(req: TranslateRequest):
    """SSE 流式翻译：bilingual_start → bilingual_token* → bilingual → done。"""

    if not translation_model_configured():
        raise HTTPException(
            status_code=503,
            detail="未配置翻译模型。请在 apps/api/.env 设置 TRANSLATION_OLLAMA_MODEL。",
        )

    async def gen():
        target = req.target_lang
        async for ev in stream_translate_sse_events(req.text, target):  # type: ignore[arg-type]
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """Server-Sent Events：citations | token | bilingual_* | done | error。"""

    async def gen():
        async for ev in answer_with_citations_stream(
            req.question,
            lang=req.lang,
            use_cache=req.use_cache,
            paper_ids=req.paper_ids,
            tags=req.tags,
            collections=req.collections,
            years_min=req.years_min,
            years_max=req.years_max,
        ):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
