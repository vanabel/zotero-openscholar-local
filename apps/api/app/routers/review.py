import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.services.rag import (
    export_review_docx,
    export_review_markdown,
    write_literature_review,
    write_literature_review_stream,
)
from app.services.review_cache import get_cached_review, list_recent_reviews
from app.services.review_templates import ReviewTemplate

router = APIRouter(prefix="/review", tags=["review"])


class ReviewRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=2000)
    focus: str | None = Field(None, max_length=4000)
    lang: str = Field(default="zh", pattern="^(zh|en)$")
    use_cache: bool = True
    template: ReviewTemplate = "literature_review"
    paper_ids: list[str] | None = Field(None, max_length=50)
    tags: list[str] | None = Field(None, max_length=30)
    collections: list[str] | None = Field(None, max_length=30)
    years_min: int | None = Field(None, ge=1900, le=2100)
    years_max: int | None = Field(None, ge=1900, le=2100)


@router.get("/recent")
def review_recent(
    lang: str = Query("zh", pattern="^(zh|en)$"),
    limit: int = Query(10, ge=1, le=30),
):
    """近期综述主题（随机顺序），供综述页快捷填入。"""
    items = list_recent_reviews(lang, limit=limit)
    return {
        "items": items,
        "cache_enabled": settings.chat_cache_enabled,
        "lang": lang,
    }


@router.get("/cache")
def review_cache_lookup(
    topic: str = Query(..., min_length=1, max_length=2000),
    lang: str = Query("zh", pattern="^(zh|en)$"),
    focus: str = Query(""),
    template: ReviewTemplate = Query("literature_review"),
):
    hit = get_cached_review(topic, focus or None, lang, template=template)
    if hit is None:
        raise HTTPException(status_code=404, detail="无有效缓存")
    return hit


def _scope_kwargs(req: ReviewRequest) -> dict:
    return {
        "paper_ids": req.paper_ids,
        "tags": req.tags,
        "collections": req.collections,
        "years_min": req.years_min,
        "years_max": req.years_max,
    }


@router.post("")
async def review(req: ReviewRequest):
    return await write_literature_review(
        req.topic,
        focus=req.focus,
        lang=req.lang,
        use_cache=req.use_cache,
        template=req.template,
        **_scope_kwargs(req),
    )


@router.post("/export-markdown")
async def review_export_markdown(req: ReviewRequest):
    """生成综述/申请书草稿并返回 Markdown 文件内容。"""
    md = await export_review_markdown(
        req.topic,
        focus=req.focus,
        lang=req.lang,
        template=req.template,
        use_cache=req.use_cache,
        **_scope_kwargs(req),
    )
    safe = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in req.topic[:40]).strip() or "review"
    filename = f"{safe}.md"
    return PlainTextResponse(
        md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export-docx")
async def review_export_docx(req: ReviewRequest):
    """生成综述/申请书草稿并返回 DOCX（需 python-docx）。"""
    try:
        blob = await export_review_docx(
            req.topic,
            focus=req.focus,
            lang=req.lang,
            template=req.template,
            use_cache=req.use_cache,
            **_scope_kwargs(req),
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    safe = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in req.topic[:40]).strip() or "review"
    filename = f"{safe}.docx"
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/stream")
async def review_stream(req: ReviewRequest):
    """SSE：citations | token | done | error。"""

    async def gen():
        async for ev in write_literature_review_stream(
            req.topic,
            focus=req.focus,
            lang=req.lang,
            use_cache=req.use_cache,
            template=req.template,
            **_scope_kwargs(req),
        ):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
