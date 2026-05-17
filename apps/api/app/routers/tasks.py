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


@router.get("/stats")
def task_stats(failed_limit: int = Query(10, ge=0, le=50)):
    """全表任务状态统计（按 status / task_type 聚合）。"""
    from app.services.task_queue import get_task_stats

    return get_task_stats(failed_limit=failed_limit)


@router.post("/cancel-queued")
def cancel_queued_tasks():
    """取消全部排队中（status=queued）的任务，不中断正在 running 的任务。"""
    from app.services.task_queue import cancel_all_queued_tasks

    return cancel_all_queued_tasks()


@router.post("/cancel-orphans")
def cancel_orphan_tasks():
    """清理指向已删/不存在文献的 queued 与 running 任务。"""
    from app.services.task_queue import cancel_orphan_pending_tasks

    return cancel_orphan_pending_tasks()


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
