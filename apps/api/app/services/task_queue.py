from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from app.db import get_db, json_dumps_safe, row_to_dict
from app.services.zotero_scanner import get_paper
from app.config import settings
from app.pipeline_logging import plog_info

_worker_task: asyncio.Task | None = None
_queue: asyncio.Queue[str] = asyncio.Queue()
ACTIVE_STATUSES = ("queued", "running")

_ORPHAN_PENDING_WHERE = """
    t.status IN ('queued', 'running')
    AND t.paper_id IS NOT NULL
    AND NOT EXISTS (
        SELECT 1 FROM papers p WHERE p.id = t.paper_id AND p.deleted = 0
    )
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskProgress:
    """向 tasks 表写入阶段进度（供前端轮询）。"""

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id

    def update(self, phase: str, done: int, total: int, message: str = "") -> None:
        payload = {
            "phase": phase,
            "done": done,
            "total": total,
            "message": message or _default_message(phase, done, total),
        }
        now = _utc_now()
        with get_db() as conn:
            conn.execute(
                "UPDATE tasks SET progress_json = ?, updated_at = ? WHERE id = ?",
                (json_dumps_safe(payload), now, self.task_id),
            )
        row = _task_row(self.task_id)
        if row:
            from app.services.task_events import publish_task_event

            publish_task_event(
                {
                    "type": "task_progress",
                    "task_id": self.task_id,
                    "paper_id": row.get("paper_id"),
                    "task_type": row.get("task_type"),
                    "status": row.get("status"),
                    "progress": payload,
                }
            )


def _default_message(phase: str, done: int, total: int) -> str:
    labels = {
        "queued": "排队中",
        "parse": "PDF 解析",
        "chunk": "分块",
        "embed": "向量嵌入",
        "scholar_embed": "OpenScholar 嵌入",
        "save": "写入索引",
        "summarize": "生成摘要",
        "done": "完成",
    }
    label = labels.get(phase, phase)
    if total > 0 and phase not in ("queued", "done"):
        return f"{label} {done}/{total}"
    return label


def _task_row(task_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return row_to_dict(row) if row else None


def _parse_json_field(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        v = json.loads(raw)
        return v if isinstance(v, dict) else None
    except json.JSONDecodeError:
        return None


def task_to_api(row: dict) -> dict:
    progress = _parse_json_field(row.get("progress_json"))
    payload = _parse_json_field(row.get("payload_json"))
    result = _parse_json_field(row.get("result_json"))
    return {
        "id": row["id"],
        "task_type": row["task_type"],
        "paper_id": row.get("paper_id"),
        "status": row["status"],
        "error": row.get("error"),
        "progress": progress,
        "payload": payload,
        "result": result,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_task(task_id: str) -> dict | None:
    row = _task_row(task_id)
    return task_to_api(row) if row else None


def get_task_stats(*, failed_limit: int = 10) -> dict:
    """全表任务统计（按状态 / 类型），供管理面板展示。"""
    failed_limit = max(0, min(int(failed_limit), 50))
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM tasks").fetchone()["c"]
        pending = conn.execute(
            "SELECT COUNT(*) AS c FROM tasks WHERE status IN ('queued', 'running')"
        ).fetchone()["c"]
        by_status = [
            {"status": r["status"], "count": r["c"]}
            for r in conn.execute(
                "SELECT status, COUNT(*) AS c FROM tasks GROUP BY status ORDER BY c DESC, status"
            ).fetchall()
        ]
        by_type = [
            {"task_type": r["task_type"], "count": r["c"]}
            for r in conn.execute(
                "SELECT task_type, COUNT(*) AS c FROM tasks GROUP BY task_type ORDER BY c DESC, task_type"
            ).fetchall()
        ]
        by_type_status = [
            {
                "task_type": r["task_type"],
                "status": r["status"],
                "count": r["c"],
            }
            for r in conn.execute(
                """
                SELECT task_type, status, COUNT(*) AS c
                FROM tasks
                GROUP BY task_type, status
                ORDER BY task_type, status
                """
            ).fetchall()
        ]
        pr = conn.execute(
            """
            SELECT MIN(created_at) AS oldest, MAX(created_at) AS newest
            FROM tasks
            WHERE status IN ('queued', 'running')
            """
        ).fetchone()
        orphan_pending = conn.execute(
            f"SELECT COUNT(*) AS c FROM tasks t WHERE {_ORPHAN_PENDING_WHERE}"
        ).fetchone()["c"]
        failed_rows = []
        if failed_limit:
            failed_rows = conn.execute(
                """
                SELECT id, task_type, paper_id, error, updated_at
                FROM tasks
                WHERE status = 'failed'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (failed_limit,),
            ).fetchall()
    return {
        "total": total,
        "pending": pending,
        "worker_concurrency": max(1, int(settings.task_worker_concurrency)),
        "by_status": by_status,
        "by_type": by_type,
        "by_type_status": by_type_status,
        "pending_range": (
            {"oldest": pr["oldest"], "newest": pr["newest"]}
            if pending and pr and pr["oldest"]
            else None
        ),
        "orphan_pending": orphan_pending,
        "failed_samples": [
            {
                "id": r["id"],
                "task_type": r["task_type"],
                "paper_id": r["paper_id"],
                "error": (r["error"] or "")[:500],
                "updated_at": r["updated_at"],
            }
            for r in failed_rows
        ],
    }


def _revert_paper_indexing_if_idle(conn, paper_id: str, now: str) -> bool:
    """取消索引排队后，若文献无其它活动 index 任务且仍为 indexing，则恢复 index_status。"""
    row = conn.execute(
        "SELECT index_status FROM papers WHERE id = ? AND deleted = 0",
        (paper_id,),
    ).fetchone()
    if not row or row["index_status"] != "indexing":
        return False
    active = conn.execute(
        """
        SELECT 1 FROM tasks
        WHERE paper_id = ? AND task_type = 'index' AND status IN ('queued', 'running')
        LIMIT 1
        """,
        (paper_id,),
    ).fetchone()
    if active:
        return False
    has_chunks = conn.execute(
        "SELECT 1 FROM chunks WHERE paper_id = ? LIMIT 1",
        (paper_id,),
    ).fetchone()
    new_status = "indexed" if has_chunks else "pending"
    conn.execute(
        """
        UPDATE papers SET index_status = ?, status_message = NULL, updated_at = ?
        WHERE id = ? AND deleted = 0
        """,
        (new_status, now, paper_id),
    )
    return True


def cancel_all_queued_tasks() -> dict:
    """将 status=queued 的任务标为 cancelled，并恢复仍卡在 indexing 的文献状态。"""
    now = _utc_now()
    reason = "用户取消排队"
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, paper_id, task_type FROM tasks WHERE status = 'queued'"
        ).fetchall()
        if not rows:
            return {"cancelled": 0, "papers_reverted": 0}
        conn.execute(
            "UPDATE tasks SET status = 'cancelled', error = ?, updated_at = ? WHERE status = 'queued'",
            (reason, now),
        )
        papers_reverted = 0
        for pid in {r["paper_id"] for r in rows if r["task_type"] == "index" and r["paper_id"]}:
            if _revert_paper_indexing_if_idle(conn, pid, now):
                papers_reverted += 1
    for row in rows:
        _publish_task_status(row["id"], status="cancelled", error=reason)
    plog_info("task", "取消排队 %s 条，恢复文献状态 %s 篇", len(rows), papers_reverted)
    return {"cancelled": len(rows), "papers_reverted": papers_reverted}


def cancel_orphan_pending_tasks() -> dict:
    """清理指向不存在/已删文献的 queued/running 任务。"""
    now = _utc_now()
    reason = "文献不存在或已删除，已清理"
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT id, status FROM tasks t WHERE {_ORPHAN_PENDING_WHERE}"
        ).fetchall()
        if not rows:
            return {"cancelled": 0, "failed": 0}
        conn.execute(
            f"""
            UPDATE tasks SET status = 'cancelled', error = ?, updated_at = ?
            WHERE status = 'queued' AND id IN (
                SELECT t.id FROM tasks t WHERE {_ORPHAN_PENDING_WHERE} AND t.status = 'queued'
            )
            """,
            (reason, now),
        )
        conn.execute(
            f"""
            UPDATE tasks SET status = 'failed', error = ?, updated_at = ?
            WHERE status = 'running' AND id IN (
                SELECT t.id FROM tasks t WHERE {_ORPHAN_PENDING_WHERE} AND t.status = 'running'
            )
            """,
            (reason, now),
        )
    cancelled = sum(1 for r in rows if r["status"] == "queued")
    failed = sum(1 for r in rows if r["status"] == "running")
    for row in rows:
        st = "cancelled" if row["status"] == "queued" else "failed"
        _publish_task_status(row["id"], status=st, error=reason)
    plog_info("task", "清理孤儿任务 cancelled=%s failed=%s", cancelled, failed)
    return {"cancelled": cancelled, "failed": failed}


def list_active_tasks(*, paper_ids: list[str] | None = None) -> list[dict]:
    with get_db() as conn:
        if paper_ids:
            placeholders = ",".join("?" * len(paper_ids))
            rows = conn.execute(
                f"""
                SELECT * FROM tasks
                WHERE status IN ('queued', 'running')
                  AND paper_id IN ({placeholders})
                ORDER BY created_at ASC
                """,
                paper_ids,
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status IN ('queued', 'running')
                ORDER BY created_at ASC
                """
            ).fetchall()
    return [task_to_api(row_to_dict(r)) for r in rows]


def _find_active_index_task(paper_id: str) -> str | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT id FROM tasks
            WHERE paper_id = ? AND task_type = 'index' AND status IN ('queued', 'running')
            ORDER BY created_at DESC LIMIT 1
            """,
            (paper_id,),
        ).fetchone()
    return row["id"] if row else None


def enqueue_index_task(
    paper_id: str,
    *,
    force: bool = False,
    reindex_only: bool = False,
    parse_only: bool = False,
) -> dict:
    paper = get_paper(paper_id)
    if not paper or paper.get("deleted"):
        return {"ok": False, "error": "文献不存在或已归档"}
    existing = _find_active_index_task(paper_id)
    if existing:
        t = get_task(existing)
        return {"task_id": existing, "status": t["status"] if t else "queued", "deduped": True}

    task_id = uuid.uuid4().hex
    now = _utc_now()
    payload = {"force": force, "reindex_only": reindex_only, "parse_only": parse_only}
    progress = {"phase": "queued", "done": 0, "total": 0, "message": "排队中"}
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO tasks(
              id, task_type, paper_id, status, error,
              payload_json, progress_json, result_json,
              created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                task_id,
                "index",
                paper_id,
                "queued",
                None,
                json_dumps_safe(payload),
                json_dumps_safe(progress),
                None,
                now,
                now,
            ),
        )
        conn.execute(
            "UPDATE papers SET index_status = 'indexing', updated_at = ? WHERE id = ? AND deleted = 0",
            (now, paper_id),
        )
    _queue.put_nowait(task_id)
    plog_info(
        "task",
        "入队 index task_id=%s paper_id=%s force=%s parse_only=%s",
        task_id,
        paper_id,
        force,
        parse_only,
    )
    return {"task_id": task_id, "status": "queued", "deduped": False}


def enqueue_index_batch(
    paper_ids: list[str],
    *,
    force: bool = False,
    reindex_only: bool = False,
    parse_only: bool = False,
) -> list[dict]:
    return [
        enqueue_index_task(pid, force=force, reindex_only=reindex_only, parse_only=parse_only)
        for pid in paper_ids
    ]


def _find_active_summarize_task(paper_id: str) -> str | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT id FROM tasks
            WHERE paper_id = ? AND task_type = 'summarize' AND status IN ('queued', 'running')
            ORDER BY created_at DESC LIMIT 1
            """,
            (paper_id,),
        ).fetchone()
    return row["id"] if row else None


def enqueue_summarize_task(paper_id: str, *, lang: str = "zh") -> dict:
    paper = get_paper(paper_id)
    if not paper or paper.get("deleted"):
        return {"ok": False, "error": "文献不存在或已归档"}
    if (paper.get("index_status") or "") != "indexed":
        return {"ok": False, "error": "文献尚未 indexed，无法生成摘要"}
    existing = _find_active_summarize_task(paper_id)
    if existing:
        t = get_task(existing)
        return {"task_id": existing, "status": t["status"] if t else "queued", "deduped": True}

    task_id = uuid.uuid4().hex
    now = _utc_now()
    payload = {"lang": lang}
    progress = {"phase": "queued", "done": 0, "total": 1, "message": "排队中"}
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO tasks(
              id, task_type, paper_id, status, error,
              payload_json, progress_json, result_json,
              created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                task_id,
                "summarize",
                paper_id,
                "queued",
                None,
                json_dumps_safe(payload),
                json_dumps_safe(progress),
                None,
                now,
                now,
            ),
        )
    _queue.put_nowait(task_id)
    plog_info("task", "入队 summarize task_id=%s paper_id=%s", task_id, paper_id)
    return {"task_id": task_id, "status": "queued", "deduped": False}


def enqueue_summarize_batch(paper_ids: list[str], *, lang: str = "zh") -> list[dict]:
    return [enqueue_summarize_task(pid, lang=lang) for pid in paper_ids]


async def _run_summarize_task(task_id: str) -> None:
    from app.services.paper_summary import generate_paper_summary

    row = _task_row(task_id)
    if not row or row["task_type"] != "summarize":
        return
    paper_id = row.get("paper_id") or ""
    payload = _parse_json_field(row.get("payload_json")) or {}
    lang = str(payload.get("lang") or "zh")
    progress = TaskProgress(task_id)
    now = _utc_now()
    with get_db() as conn:
        conn.execute(
            "UPDATE tasks SET status = 'running', updated_at = ? WHERE id = ?",
            (now, task_id),
        )
    progress.update("summarize", 0, 1, "生成摘要中…")
    try:
        result = await generate_paper_summary(paper_id, lang=lang)
        if result.get("ok"):
            with get_db() as conn:
                conn.execute(
                    """
                    UPDATE tasks SET status = 'completed', result_json = ?, error = NULL,
                      progress_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        json_dumps_safe(result),
                        json_dumps_safe({"phase": "done", "done": 1, "total": 1, "message": "完成"}),
                        _utc_now(),
                        task_id,
                    ),
                )
            plog_info("task", "完成 summarize task_id=%s paper_id=%s", task_id, paper_id)
            _publish_task_status(task_id, status="completed")
        else:
            err = result.get("error") or "摘要失败"
            _fail_task(task_id, paper_id, err, result, touch_index_status=False)
            _publish_task_status(task_id, status="failed", error=err)
    except Exception as e:
        plog_info("task", "异常 summarize task_id=%s: %s", task_id, e)
        _fail_task(task_id, paper_id, str(e), None, touch_index_status=False)
        _publish_task_status(task_id, status="failed", error=str(e))


async def _run_index_task(task_id: str) -> None:
    from app.services.indexing import index_paper

    row = _task_row(task_id)
    if not row or row["task_type"] != "index":
        return
    paper_id = row.get("paper_id") or ""
    payload = _parse_json_field(row.get("payload_json")) or {}
    force = bool(payload.get("force"))
    reindex_only = bool(payload.get("reindex_only"))
    parse_only = bool(payload.get("parse_only"))
    progress = TaskProgress(task_id)
    now = _utc_now()
    with get_db() as conn:
        conn.execute(
            "UPDATE tasks SET status = 'running', updated_at = ? WHERE id = ?",
            (now, task_id),
        )
    progress.update("queued", 0, 0, "开始处理")
    try:
        result = await index_paper(
            paper_id,
            force=force,
            reindex_only=reindex_only,
            parse_only=parse_only,
            progress=progress,
        )
        if result.get("ok"):
            with get_db() as conn:
                conn.execute(
                    """
                    UPDATE tasks SET status = 'completed', result_json = ?, error = NULL,
                      progress_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        json_dumps_safe(result),
                        json_dumps_safe({"phase": "done", "done": 1, "total": 1, "message": "完成"}),
                        _utc_now(),
                        task_id,
                    ),
                )
            plog_info("task", "完成 index task_id=%s paper_id=%s", task_id, paper_id)
            _publish_task_status(task_id, status="completed")
        else:
            err = result.get("error") or "索引失败"
            _fail_task(task_id, paper_id, err, result)
            _publish_task_status(task_id, status="failed", error=err)
    except Exception as e:
        plog_info("task", "异常 index task_id=%s: %s", task_id, e)
        _fail_task(task_id, paper_id, str(e), None)
        _publish_task_status(task_id, status="failed", error=str(e))


def _fail_task(
    task_id: str,
    paper_id: str,
    error: str,
    result: dict | None,
    *,
    touch_index_status: bool = True,
) -> None:
    from app.services.paper_status import set_paper_status

    now = _utc_now()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE tasks SET status = 'failed', error = ?, result_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (error, json_dumps_safe(result) if result else None, now, task_id),
        )
    if touch_index_status:
        set_paper_status(paper_id, index_status="failed", status_message=error[:2000])


def _publish_task_status(task_id: str, *, status: str, error: str | None = None) -> None:
    row = _task_row(task_id)
    if not row:
        return
    from app.services.task_events import publish_task_event

    publish_task_event(
        {
            "type": "task_status",
            "task_id": task_id,
            "paper_id": row.get("paper_id"),
            "task_type": row.get("task_type"),
            "status": status,
            "error": error,
            "progress": _parse_json_field(row.get("progress_json")),
        }
    )


async def _dispatch_task(task_id: str) -> None:
    row = _task_row(task_id)
    if not row:
        return
    if row["status"] == "cancelled":
        return
    if row["status"] not in ACTIVE_STATUSES:
        return
    if row.get("task_type") == "summarize":
        await _run_summarize_task(task_id)
    else:
        await _run_index_task(task_id)


async def _worker_loop() -> None:
    n = max(1, int(settings.task_worker_concurrency))

    async def _consumer() -> None:
        while True:
            task_id = await _queue.get()
            try:
                await _dispatch_task(task_id)
            finally:
                _queue.task_done()

    await asyncio.gather(*[_consumer() for _ in range(n)])


def _resume_queued_tasks() -> None:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id FROM tasks WHERE status IN ('queued', 'running') ORDER BY created_at ASC"
        ).fetchall()
        if rows:
            conn.execute(
                "UPDATE tasks SET status = 'queued', updated_at = ? WHERE status = 'running'",
                (_utc_now(),),
            )
    for row in rows:
        _queue.put_nowait(row["id"])
    if rows:
        plog_info("task", "恢复 %s 个未完成任务", len(rows))


def start_worker(*, standalone: bool = False) -> None:
    global _worker_task
    if not standalone and not settings.task_worker_embedded():
        plog_info("task", "TASK_WORKER_MODE=external，API 进程不启动 Worker")
        return
    _resume_queued_tasks()
    if _worker_task is None or _worker_task.done():
        n = max(1, int(settings.task_worker_concurrency))
        plog_info("task", "启动 embedded Worker concurrency=%s", n)
        _worker_task = asyncio.create_task(_worker_loop(), name="index-task-worker")


async def stop_worker() -> None:
    global _worker_task
    if _worker_task is None:
        return
    _worker_task.cancel()
    try:
        await _worker_task
    except asyncio.CancelledError:
        pass
    _worker_task = None
