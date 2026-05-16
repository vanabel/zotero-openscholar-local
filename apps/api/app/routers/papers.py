from pathlib import Path

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(prefix="/papers", tags=["papers"])


class BatchIndexBody(BaseModel):
    paper_ids: list[str] = Field(..., min_length=1, max_length=100)
    force: bool = False
    reindex_only: bool = False


@router.post("/sync-zotero-metadata")
def sync_zotero_metadata(
    include_deleted: bool = Query(False, description="是否包含已标记 deleted 的文献"),
):
    """从只读 zotero.sqlite 同步题录、作者、标签、集合到 papers（按 storage 子目录 key 匹配）。"""
    from app.services.zotero_sqlite_sync import sync_zotero_metadata_to_papers

    return sync_zotero_metadata_to_papers(include_deleted=include_deleted)


@router.get("/quality-summary")
def papers_quality_summary():
    """解析质量分布（低质量阈值默认 0.65）。"""
    from app.services.zotero_scanner import parse_quality_summary

    return parse_quality_summary()


@router.get("")
def list_papers(
    limit: int = Query(200, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, max_length=500, description="按标题、文件名、路径、作者、标签、集合模糊搜索"),
    parse_quality_lte: float | None = Query(
        None, ge=0.0, le=1.0, description="仅返回质量分 ≤ 该值的文献（需已有评分）"
    ),
    parse_quality_gte: float | None = Query(
        None, ge=0.0, le=1.0, description="仅返回质量分 ≥ 该值的文献"
    ),
    parse_quality_missing: bool = Query(
        False, description="仅返回尚无 parse_quality_score 的文献"
    ),
    sort: str = Query(
        "updated",
        pattern="^(updated|quality_asc|quality_desc)$",
        description="排序：updated | quality_asc | quality_desc",
    ),
):
    from app.services.zotero_scanner import count_papers, list_papers as lp

    kw = {
        "parse_quality_lte": parse_quality_lte,
        "parse_quality_gte": parse_quality_gte,
        "parse_quality_missing": parse_quality_missing,
    }
    items = lp(limit=limit, offset=offset, q=q, sort=sort, **kw)
    return {
        "items": items,
        "total": count_papers(q=q, **kw),
        "q": (q or "").strip() or None,
        "filters": {**kw, "sort": sort},
    }


@router.post("/index-batch")
async def index_batch(
    body: BatchIndexBody,
    wait: bool = Query(False, description="为 true 时同步等待全部完成（脚本/调试）"),
):
    if wait:
        from app.services.indexing import index_paper

        results: list[dict] = []
        for paper_id in body.paper_ids:
            res = await index_paper(paper_id, force=body.force, reindex_only=body.reindex_only)
            results.append({"paper_id": paper_id, **res})
        ok_n = sum(1 for r in results if r.get("ok"))
        return {
            "ok": ok_n == len(results),
            "success": ok_n,
            "failed": len(results) - ok_n,
            "results": results,
        }

    from app.services.task_queue import enqueue_index_batch

    tasks = enqueue_index_batch(
        body.paper_ids,
        force=body.force,
        reindex_only=body.reindex_only,
    )
    errors = [t for t in tasks if t.get("error")]
    return JSONResponse(
        status_code=202,
        content={
            "ok": len(errors) == 0,
            "queued": len(tasks) - len(errors),
            "failed": len(errors),
            "tasks": tasks,
        },
    )


@router.get("/{paper_id}/pdf")
def get_paper_pdf(paper_id: str):
    """按 paper_id 返回磁盘上的原始 PDF（用于浏览器打开/下载）。"""
    from app.services.zotero_scanner import get_paper

    p = get_paper(paper_id)
    if not p:
        raise HTTPException(status_code=404, detail="未找到文献")
    raw = (p.get("pdf_path") or "").strip()
    if not raw:
        raise HTTPException(status_code=404, detail="无 PDF 路径")
    path = Path(raw).expanduser()
    try:
        path = path.resolve(strict=False)
    except OSError:
        raise HTTPException(status_code=404, detail="路径无效")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="PDF 文件不存在")
    if path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="非 PDF 文件")
    fname = path.name
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=fname,
        content_disposition_type="inline",
    )


_DOCUMENT_PREVIEW_MAX = 48_000


@router.get("/{paper_id}/document")
def get_paper_document(
    paper_id: str,
    max_chars: int = Query(12000, ge=500, le=_DOCUMENT_PREVIEW_MAX),
):
    """返回 data/parsed/{id}/document.md 预览（截断）。"""
    from app.config import settings
    from app.services.zotero_scanner import get_paper

    p = get_paper(paper_id)
    if not p:
        raise HTTPException(status_code=404, detail="未找到文献")
    path = settings.parsed_dir / paper_id / "document.md"
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="尚无 document.md，请先对该文献执行「建立索引」或解析。",
        )
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"读取 document.md 失败: {e}") from e
    total = len(text)
    truncated = total > max_chars
    body = text[:max_chars] if truncated else text
    return {
        "paper_id": paper_id,
        "markdown": body,
        "chars": total,
        "truncated": truncated,
        "path": str(path),
    }


@router.get("/{paper_id}/parse-report")
def get_parse_report(paper_id: str):
    from app.services.parse_quality import latest_parse_report
    from app.services.zotero_scanner import get_paper

    if not get_paper(paper_id):
        raise HTTPException(status_code=404, detail="未找到文献")
    report = latest_parse_report(paper_id)
    if not report:
        raise HTTPException(status_code=404, detail="尚无解析质量报告，请先建立索引")
    return report


@router.get("/{paper_id}/chunks")
def list_paper_chunks(
    paper_id: str,
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """列出该文献已索引的 chunk 预览。"""
    from app.db import get_db, row_to_dict
    from app.services.zotero_scanner import get_paper

    if not get_paper(paper_id):
        raise HTTPException(status_code=404, detail="未找到文献")
    with get_db() as conn:
        total_row = conn.execute(
            "SELECT COUNT(*) AS c FROM chunks WHERE paper_id = ?",
            (paper_id,),
        ).fetchone()
        rows = conn.execute(
            """
            SELECT id, paper_id, section_title, section_path, page_start, page_end,
                   chunk_index, chunk_type, chunk_quality_score, content_hash,
                   token_count, substr(text, 1, 400) AS text_preview
            FROM chunks
            WHERE paper_id = ?
            ORDER BY chunk_index ASC
            LIMIT ? OFFSET ?
            """,
            (paper_id, limit, offset),
        ).fetchall()
    items = [row_to_dict(r) for r in rows]
    return {"paper_id": paper_id, "items": items, "total": int(total_row["c"]) if total_row else 0}


@router.get("/{paper_id}")
def get_paper_detail(paper_id: str):
    from app.services.zotero_scanner import get_paper

    p = get_paper(paper_id)
    if not p:
        raise HTTPException(status_code=404, detail="未找到文献")
    return p


@router.post("/{paper_id}/reindex-only")
async def reindex_only_one(
    paper_id: str,
    wait: bool = Query(False),
):
    """仅重建分块/嵌入，复用已有 document.md。"""
    return await index_one(paper_id, force=False, reindex_only=True, wait=wait)


@router.post("/{paper_id}/index")
async def index_one(
    paper_id: str,
    force: bool = Query(False),
    reindex_only: bool = Query(False, description="仅重建分块/FTS/嵌入，复用 data/parsed 下 Markdown，不跑 MinerU"),
    wait: bool = Query(False, description="为 true 时同步等待完成（脚本/调试）"),
):
    if wait:
        from app.services.indexing import index_paper

        res = await index_paper(paper_id, force=force, reindex_only=reindex_only)
        if not res.get("ok"):
            raise HTTPException(status_code=400, detail=res.get("error", "索引失败"))
        return res

    from app.services.task_queue import enqueue_index_task

    info = enqueue_index_task(paper_id, force=force, reindex_only=reindex_only)
    if info.get("error"):
        raise HTTPException(status_code=400, detail=info["error"])
    return JSONResponse(
        status_code=202,
        content={
            "ok": True,
            "task_id": info["task_id"],
            "status": info["status"],
            "deduped": info.get("deduped", False),
            "paper_id": paper_id,
        },
    )
