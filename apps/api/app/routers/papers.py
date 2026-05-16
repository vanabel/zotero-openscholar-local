from pathlib import Path

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

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


@router.get("")
def list_papers(
    limit: int = Query(200, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, max_length=500, description="按标题、文件名、路径、作者、标签、集合模糊搜索"),
):
    from app.services.zotero_scanner import count_papers, list_papers as lp

    items = lp(limit=limit, offset=offset, q=q)
    return {"items": items, "total": count_papers(q=q), "q": (q or "").strip() or None}


@router.post("/index-batch")
async def index_batch(body: BatchIndexBody):
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


@router.get("/{paper_id}")
def get_paper_detail(paper_id: str):
    from app.services.zotero_scanner import get_paper

    p = get_paper(paper_id)
    if not p:
        raise HTTPException(status_code=404, detail="未找到文献")
    return p


@router.post("/{paper_id}/index")
async def index_one(
    paper_id: str,
    force: bool = Query(False),
    reindex_only: bool = Query(False, description="仅重建分块/FTS/嵌入，复用 data/parsed 下 Markdown，不跑 MinerU"),
):
    from app.services.indexing import index_paper

    res = await index_paper(paper_id, force=force, reindex_only=reindex_only)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "索引失败"))
    return res
