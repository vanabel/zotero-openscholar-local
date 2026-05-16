from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/active")
def list_active(
    paper_ids: str | None = Query(
        None,
        description="逗号分隔的 paper_id，仅返回这些文献上的活动任务",
    ),
):
    from app.services.task_queue import list_active_tasks

    ids = [x.strip() for x in paper_ids.split(",") if x.strip()] if paper_ids else None
    items = list_active_tasks(paper_ids=ids)
    return {"items": items}


@router.get("/active/stream")
async def stream_active_tasks():
    """SSE：推送活动任务进度与状态变更（替代高频轮询 /tasks/active）。"""
    from app.services.task_events import sse_stream
    from app.services.task_queue import list_active_tasks

    initial = {"type": "snapshot", "items": list_active_tasks()}
    return StreamingResponse(
        sse_stream(initial=initial),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{task_id}")
def get_task_status(task_id: str):
    from app.services.task_queue import get_task

    t = get_task(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    return t
