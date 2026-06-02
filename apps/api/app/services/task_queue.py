from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from app.db import get_db, json_dumps_safe, row_to_dict
from app.services.zotero_scanner import get_paper
from app.config import settings
from app.pipeline_logging import log_context, plog_info

_worker_task: asyncio.Task | None = None
_queue: asyncio.Queue[str] = asyncio.Queue()
ACTIVE_STATUSES = ("queued", "running")

_TASK_KIND_SQL = """
  CASE
    WHEN task_type = 'summarize' THEN 'summarize'
    WHEN task_type = 'index' AND COALESCE(json_extract(payload_json, '$.parse_only'), 0) THEN 'parse'
    WHEN task_type = 'index' AND COALESCE(json_extract(payload_json, '$.reindex_only'), 0) THEN 'reindex'
    WHEN task_type = 'index' AND COALESCE(json_extract(payload_json, '$.mineru_download_only'), 0) THEN 'mineru_download'
    WHEN task_type = 'index' THEN 'index'
    ELSE task_type
  END
"""

_ORPHAN_PENDING_WHERE = """
    t.status IN ('queued', 'running')
    AND t.paper_id IS NOT NULL
    AND NOT EXISTS (
        SELECT 1 FROM papers p WHERE p.id = t.paper_id AND p.deleted = 0
    )
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_duration_sec(started_at: str, ended_at: str) -> float:
    try:
        a = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        b = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
        return max(0.0, (b - a).total_seconds())
    except (TypeError, ValueError, OSError):
        return 0.0


def _phase_history_entry(
    phase: str,
    started_at: str,
    ended_at: str,
    done: int,
    total: int,
) -> dict:
    return {
        "phase": phase,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_sec": round(_iso_duration_sec(started_at, ended_at), 2),
        "done": done,
        "total": total,
    }


class TaskProgress:
    """向 tasks 表写入阶段进度（供前端轮询）。"""

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id

    def _load_progress(self) -> dict | None:
        row = _task_row(self.task_id)
        if not row:
            return None
        return _parse_json_field(row.get("progress_json"))

    def _save_progress(self, payload: dict) -> None:
        now = _utc_now()
        with get_db() as conn:
            conn.execute(
                "UPDATE tasks SET progress_json = ?, updated_at = ? WHERE id = ?",
                (json_dumps_safe(payload), now, self.task_id),
            )
        row = _task_row(self.task_id)
        if row:
            from app.services.task_events import publish_task_event
            from app.services.task_kind import task_kind

            pl = _parse_json_field(row.get("payload_json"))
            publish_task_event(
                {
                    "type": "task_progress",
                    "task_id": self.task_id,
                    "paper_id": row.get("paper_id"),
                    "task_type": row.get("task_type"),
                    "kind": task_kind(task_type=row.get("task_type") or "index", payload=pl),
                    "status": row.get("status"),
                    "progress": payload,
                    "payload": pl,
                }
            )

    def update(self, phase: str, done: int, total: int, message: str = "") -> None:
        now = _utc_now()
        prev = self._load_progress()
        history = list((prev or {}).get("phase_history") or [])
        prev_phase = (prev or {}).get("phase") if prev else None
        if prev_phase is not None and prev_phase != phase:
            history.append(
                _phase_history_entry(
                    str(prev_phase),
                    str((prev or {}).get("phase_started_at") or now),
                    now,
                    int((prev or {}).get("done") or 0),
                    int((prev or {}).get("total") or 0),
                )
            )
        phase_started_at = (
            (prev or {}).get("phase_started_at") or now if prev_phase == phase else now
        )
        task_started_at = (prev or {}).get("task_started_at") or now
        payload = {
            "phase": phase,
            "done": done,
            "total": total,
            "message": message or _default_message(phase, done, total),
            "phase_started_at": phase_started_at,
            "task_started_at": task_started_at,
            "phase_history": history,
        }
        self._save_progress(payload)

    def finalize_phase(self) -> dict:
        """将当前阶段写入 phase_history（任务完成前调用）。"""
        prev = self._load_progress() or {}
        now = _utc_now()
        history = list(prev.get("phase_history") or [])
        phase = prev.get("phase")
        if phase and phase not in ("done",):
            history.append(
                _phase_history_entry(
                    str(phase),
                    str(prev.get("phase_started_at") or now),
                    now,
                    int(prev.get("done") or 0),
                    int(prev.get("total") or 0),
                )
            )
        return {**prev, "phase_history": history}


def _default_message(phase: str, done: int, total: int) -> str:
    labels = {
        "queued": "排队中",
        "parse": "PDF 解析",
        "chunk": "分块",
        "embed": "向量嵌入",
        "scholar_embed": "OpenScholar Retriever 嵌入",
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
    from app.services.task_kind import task_kind

    progress = _parse_json_field(row.get("progress_json"))
    payload = _parse_json_field(row.get("payload_json"))
    result = _parse_json_field(row.get("result_json"))
    tt = row["task_type"]
    out = {
        "id": row["id"],
        "task_type": tt,
        "kind": task_kind(task_type=tt, payload=payload),
        "paper_id": row.get("paper_id"),
        "paper_title": row.get("paper_title"),
        "status": row["status"],
        "error": row.get("error"),
        "progress": progress,
        "payload": payload,
        "result": result,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    return out


def get_task(task_id: str) -> dict | None:
    row = _task_row(task_id)
    return task_to_api(row) if row else None


def compute_queue_throughput(conn) -> dict | None:
    """当前待处理批次：统计同批已完成数与真实耗时均值（恢复旧队列时不用过期入队时间）。"""
    pr = conn.execute(
        """
        SELECT MIN(created_at) AS oldest, MAX(created_at) AS newest
        FROM tasks
        WHERE status IN ('queued', 'running')
        """
    ).fetchone()
    if not pr or not pr["oldest"]:
        return None

    batch_start = pr["oldest"]
    batch_end = pr["newest"]
    # 同批入队窗口；恢复队列时 pending 为新 created_at，已完成项用 updated_at 纳入统计
    batch_where = """
      status = 'completed'
      AND (
        (created_at >= ? AND created_at <= ?)
        OR updated_at >= ?
      )
    """
    batch_args = (batch_start, batch_end, batch_start)

    completed_count = conn.execute(
        f"SELECT COUNT(*) AS c FROM tasks WHERE {batch_where}",
        batch_args,
    ).fetchone()["c"]

    throughput_started_at = conn.execute(
        f"SELECT MIN(updated_at) AS first_at FROM tasks WHERE {batch_where}",
        batch_args,
    ).fetchone()["first_at"]

    duration_sec_expr = """
      CASE
        WHEN json_extract(progress_json, '$.task_started_at') IS NOT NULL
        THEN MAX(
          0.0,
          (julianday(updated_at) - julianday(json_extract(progress_json, '$.task_started_at'))) * 86400.0
        )
        ELSE MAX(0.0, (julianday(updated_at) - julianday(created_at)) * 86400.0)
      END
    """

    avg_row = conn.execute(
        f"SELECT AVG({duration_sec_expr}) AS avg_sec FROM tasks WHERE {batch_where}",
        batch_args,
    ).fetchone()
    avg_duration_sec = (
        round(float(avg_row["avg_sec"]), 2)
        if avg_row and avg_row["avg_sec"] is not None
        else None
    )

    by_kind_rows = conn.execute(
        f"""
        SELECT {_TASK_KIND_SQL} AS kind, COUNT(*) AS c
        FROM tasks
        WHERE {batch_where}
        GROUP BY kind
        """,
        batch_args,
    ).fetchall()
    kind_first_rows = conn.execute(
        f"""
        SELECT {_TASK_KIND_SQL} AS kind, MIN(updated_at) AS first_at
        FROM tasks
        WHERE {batch_where}
        GROUP BY kind
        """,
        batch_args,
    ).fetchall()
    kind_avg_rows = conn.execute(
        f"""
        SELECT {_TASK_KIND_SQL} AS kind, AVG({duration_sec_expr}) AS avg_sec
        FROM tasks
        WHERE {batch_where}
        GROUP BY kind
        """,
        batch_args,
    ).fetchall()

    return {
        "batch_started_at": batch_start,
        "batch_ended_at": batch_end,
        "throughput_started_at": throughput_started_at,
        "completed_count": int(completed_count),
        "completed_by_kind": {r["kind"]: int(r["c"]) for r in by_kind_rows},
        "kind_first_completed_at": {r["kind"]: r["first_at"] for r in kind_first_rows},
        "avg_duration_sec": avg_duration_sec,
        "avg_duration_sec_by_kind": {
            r["kind"]: round(float(r["avg_sec"]), 2)
            for r in kind_avg_rows
            if r["avg_sec"] is not None
        },
    }


def get_task_stats(*, failed_limit: int = 10) -> dict:
    """全表任务统计（按状态 / 类型 / kind），供管理面板展示。"""
    from app.services.task_kind import task_kind

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
        by_kind = [
            {"kind": r["kind"], "count": r["c"]}
            for r in conn.execute(
                """
                SELECT
                  CASE
                    WHEN task_type = 'summarize' THEN 'summarize'
                    WHEN task_type = 'index' AND COALESCE(json_extract(payload_json, '$.parse_only'), 0) THEN 'parse'
                    WHEN task_type = 'index' AND COALESCE(json_extract(payload_json, '$.reindex_only'), 0) THEN 'reindex'
                    WHEN task_type = 'index' THEN 'index'
                    ELSE task_type
                  END AS kind,
                  COUNT(*) AS c
                FROM tasks
                GROUP BY kind
                ORDER BY c DESC, kind
                """
            ).fetchall()
        ]
        by_kind_status = [
            {"kind": r["kind"], "status": r["status"], "count": r["c"]}
            for r in conn.execute(
                """
                SELECT
                  CASE
                    WHEN task_type = 'summarize' THEN 'summarize'
                    WHEN task_type = 'index' AND COALESCE(json_extract(payload_json, '$.parse_only'), 0) THEN 'parse'
                    WHEN task_type = 'index' AND COALESCE(json_extract(payload_json, '$.reindex_only'), 0) THEN 'reindex'
                    WHEN task_type = 'index' THEN 'index'
                    ELSE task_type
                  END AS kind,
                  status,
                  COUNT(*) AS c
                FROM tasks
                GROUP BY kind, status
                ORDER BY kind, status
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
        queue_throughput = compute_queue_throughput(conn)
        failed_rows = []
        if failed_limit:
            failed_rows = conn.execute(
                """
                SELECT id, task_type, paper_id, error, updated_at, payload_json
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
        "index_embed_concurrency": max(1, int(settings.index_embed_concurrency)),
        "mineru_parse_concurrency": max(1, int(settings.mineru_parse_concurrency)),
        "by_status": by_status,
        "by_type": by_type,
        "by_type_status": by_type_status,
        "by_kind": by_kind,
        "by_kind_status": by_kind_status,
        "pending_range": (
            {"oldest": pr["oldest"], "newest": pr["newest"]}
            if pending and pr and pr["oldest"]
            else None
        ),
        "orphan_pending": orphan_pending,
        "queue_throughput": queue_throughput,
        "failed_samples": [
            {
                "id": r["id"],
                "task_type": r["task_type"],
                "kind": task_kind(task_type=r["task_type"], payload_json=r["payload_json"]),
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


def purge_terminal_tasks(*, statuses: tuple[str, ...] = ("failed", "cancelled")) -> dict:
    """删除终态任务记录（默认 failed / cancelled），减轻 tasks 表体积与统计查询开销。"""
    if not statuses:
        return {"deleted": 0, "failed": 0, "cancelled": 0}
    ph = ",".join("?" * len(statuses))
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT status, COUNT(*) AS c FROM tasks WHERE status IN ({ph}) GROUP BY status",
            list(statuses),
        ).fetchall()
        cur = conn.execute(f"DELETE FROM tasks WHERE status IN ({ph})", list(statuses))
        deleted = int(cur.rowcount)
    by_status = {str(r["status"]): int(r["c"]) for r in rows}
    plog_info("task", "清理终态任务 deleted=%s breakdown=%s", deleted, by_status)
    return {
        "deleted": deleted,
        "failed": by_status.get("failed", 0),
        "cancelled": by_status.get("cancelled", 0),
    }


_ACTIVE_TASKS_SQL = """
    SELECT t.*, p.title AS paper_title
    FROM tasks t
    LEFT JOIN papers p ON p.id = t.paper_id AND p.deleted = 0
    WHERE t.status IN ('queued', 'running')
"""


def list_active_tasks(*, paper_ids: list[str] | None = None) -> list[dict]:
    with get_db() as conn:
        if paper_ids:
            placeholders = ",".join("?" * len(paper_ids))
            rows = conn.execute(
                f"""
                {_ACTIVE_TASKS_SQL}
                  AND t.paper_id IN ({placeholders})
                ORDER BY CASE t.status WHEN 'running' THEN 0 ELSE 1 END, t.created_at ASC
                """,
                paper_ids,
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                {_ACTIVE_TASKS_SQL}
                ORDER BY CASE t.status WHEN 'running' THEN 0 ELSE 1 END, t.created_at ASC
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


def _index_enqueue_intent(
    *,
    force: bool,
    reindex_only: bool,
    parse_only: bool,
    mineru_download_only: bool,
) -> tuple[bool, bool, bool, bool]:
    """与 payload 一致的四元组，用于判断是否与已有排队任务相同。"""
    return (bool(force), bool(reindex_only), bool(parse_only), bool(mineru_download_only))


def _intent_from_index_payload(pl: dict | None) -> tuple[bool, bool, bool, bool]:
    if not pl:
        return (False, False, False, False)
    return (
        bool(pl.get("force")),
        bool(pl.get("reindex_only")),
        bool(pl.get("parse_only")),
        bool(pl.get("mineru_download_only")),
    )


def enqueue_index_task(
    paper_id: str,
    *,
    force: bool = False,
    reindex_only: bool = False,
    parse_only: bool = False,
    mineru_download_only: bool = False,
) -> dict:
    paper = get_paper(paper_id)
    if not paper or paper.get("deleted"):
        return {"ok": False, "error": "文献不存在或已归档"}
    existing = _find_active_index_task(paper_id)
    if existing:
        row = _task_row(existing)
        if row:
            pl = _parse_json_field(row.get("payload_json"))
            old_intent = _intent_from_index_payload(pl)
            new_intent = _index_enqueue_intent(
                force=force,
                reindex_only=reindex_only,
                parse_only=parse_only,
                mineru_download_only=mineru_download_only,
            )
            if old_intent == new_intent:
                t = get_task(existing)
                return {"task_id": existing, "status": t["status"] if t else "queued", "deduped": True}
            if row.get("status") == "running":
                return {
                    "ok": False,
                    "error": "该文献已有进行中的后台任务，请等待完成后再提交。",
                    "deduped": False,
                }
            # 排队中但意图不同：取消旧排队，下面重新 INSERT
            if row.get("status") == "queued":
                now = _utc_now()
                with get_db() as conn:
                    conn.execute(
                        """
                        UPDATE tasks SET status = 'cancelled', error = ?, updated_at = ?
                        WHERE id = ? AND status = 'queued'
                        """,
                        ("已由同文献的新入队请求替换", now, existing),
                    )
                _publish_task_status(
                    existing, status="cancelled", error="已由同文献的新入队请求替换"
                )
                plog_info(
                    "task",
                    "取消旧排队 index 任务以替换入队 old_task_id=%s paper_id=%s",
                    existing,
                    paper_id,
                )
            else:
                plog_info(
                    "task",
                    "活动 index 任务状态异常 task_id=%s status=%s，将重新入队",
                    existing,
                    row.get("status"),
                )

    task_id = uuid.uuid4().hex
    now = _utc_now()
    payload = {
        "force": force,
        "reindex_only": reindex_only,
        "parse_only": parse_only,
        "mineru_download_only": mineru_download_only,
    }
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
        if parse_only or mineru_download_only:
            msg = "MinerU 下载重试排队中" if mineru_download_only else "解析任务排队中"
            conn.execute(
                """
                UPDATE papers SET status_message = ?, updated_at = ?
                WHERE id = ? AND deleted = 0
                """,
                (msg, now, paper_id),
            )
        else:
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
    mineru_download_only: bool = False,
) -> list[dict]:
    return [
        enqueue_index_task(
            pid,
            force=force,
            reindex_only=reindex_only,
            parse_only=parse_only,
            mineru_download_only=mineru_download_only,
        )
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
    progress.update("summarize", 0, 1, "开始生成摘要…")
    try:
        result = await generate_paper_summary(paper_id, lang=lang)
        if result.get("ok"):
            done_progress = {
                **progress.finalize_phase(),
                "phase": "done",
                "done": 1,
                "total": 1,
                "message": "完成",
            }
            with get_db() as conn:
                conn.execute(
                    """
                    UPDATE tasks SET status = 'completed', result_json = ?, error = NULL,
                      progress_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        json_dumps_safe(result),
                        json_dumps_safe(done_progress),
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
    mineru_download_only = bool(payload.get("mineru_download_only"))
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
            mineru_download_only=mineru_download_only,
            progress=progress,
        )
        if result.get("ok"):
            done_msg = "解析完成" if parse_only else "完成"
            done_progress = {
                **progress.finalize_phase(),
                "phase": "done",
                "done": 1,
                "total": 1,
                "message": done_msg,
            }
            with get_db() as conn:
                conn.execute(
                    """
                    UPDATE tasks SET status = 'completed', result_json = ?, error = NULL,
                      progress_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        json_dumps_safe(result),
                        json_dumps_safe(done_progress),
                        _utc_now(),
                        task_id,
                    ),
                )
            plog_info(
                "task",
                "完成 index task_id=%s paper_id=%s parse_only=%s",
                task_id,
                paper_id,
                parse_only,
            )
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
    from app.services.task_kind import task_kind

    now = _utc_now()
    row = _task_row(task_id)
    with get_db() as conn:
        conn.execute(
            """
            UPDATE tasks SET status = 'failed', error = ?, result_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (error, json_dumps_safe(result) if result else None, now, task_id),
        )
    if touch_index_status and row:
        pl = _parse_json_field(row.get("payload_json"))
        kind = task_kind(task_type=row.get("task_type") or "index", payload=pl)
        if kind == "parse":
            set_paper_status(
                paper_id,
                parse_status="failed",
                status_message=error[:2000],
            )
        else:
            set_paper_status(paper_id, index_status="failed", status_message=error[:2000])


def _publish_task_status(task_id: str, *, status: str, error: str | None = None) -> None:
    row = _task_row(task_id)
    if not row:
        return
    from app.services.task_events import publish_task_event
    from app.services.task_kind import task_kind

    pl = _parse_json_field(row.get("payload_json"))
    publish_task_event(
        {
            "type": "task_status",
            "task_id": task_id,
            "paper_id": row.get("paper_id"),
            "task_type": row.get("task_type"),
            "kind": task_kind(task_type=row.get("task_type") or "index", payload=pl),
            "status": status,
            "error": error,
            "progress": _parse_json_field(row.get("progress_json")),
            "payload": pl,
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
                row = _task_row(task_id)
                paper_id = (row or {}).get("paper_id") if row else None
                with log_context(task_id=task_id, paper_id=paper_id or None):
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
        if settings.resolved_chat_provider() == "transformers":
            plog_info(
                "task",
                "Transformers 对话：任务并发=%s（GPU 推理串行，勿靠提高 TASK_WORKER_CONCURRENCY 加速）",
                n,
            )
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
