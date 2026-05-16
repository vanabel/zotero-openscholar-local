"""SQLite 启动维护：按配置或 freelist 比例执行 VACUUM 回收空洞。"""

from __future__ import annotations

import sqlite3

from app.config import settings
from app.pipeline_logging import plog_info


def vacuum_needed(*, force: bool, freelist_ratio: float, threshold: float) -> bool:
    if force:
        return True
    if threshold <= 0:
        return False
    return freelist_ratio >= threshold


def _read_db_stats(conn: sqlite3.Connection) -> tuple[int, int, float]:
    page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
    freelist = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
    ratio = (freelist / page_count) if page_count else 0.0
    return page_count, freelist, ratio


def maybe_vacuum_database_on_startup() -> dict:
    """
    启动时回收 SQLite 空闲页。
    - DB_VACUUM_ON_STARTUP=1：每次启动都 VACUUM
    - DB_VACUUM_FREELIST_RATIO（默认 0.25）：freelist/page_count ≥ 阈值时自动 VACUUM；0 表示关闭比例触发
    """
    db_path = settings.db_path
    if not db_path.is_file():
        return {"vacuumed": False, "skipped": "no_database"}

    force = settings.db_vacuum_on_startup
    threshold = settings.db_vacuum_freelist_ratio

    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        page_count, freelist, ratio = _read_db_stats(conn)
        if not vacuum_needed(force=force, freelist_ratio=ratio, threshold=threshold):
            return {
                "vacuumed": False,
                "skipped": "below_threshold",
                "page_count": page_count,
                "freelist_count": freelist,
                "freelist_ratio": round(ratio, 4),
                "threshold": threshold,
                "forced": force,
            }

        size_before = db_path.stat().st_size
        conn.execute("VACUUM")
        page_after, freelist_after, _ = _read_db_stats(conn)
        size_after = db_path.stat().st_size
        out = {
            "vacuumed": True,
            "forced": force,
            "freelist_ratio_before": round(ratio, 4),
            "threshold": threshold,
            "page_count_before": page_count,
            "freelist_count_before": freelist,
            "page_count_after": page_after,
            "freelist_count_after": freelist_after,
            "size_before": size_before,
            "size_after": size_after,
            "bytes_reclaimed": max(0, size_before - size_after),
        }
        plog_info(
            "db",
            "SQLite VACUUM 完成 ratio_before=%.2f pages %s→%s size %s→%s (回收 %s 字节)",
            ratio,
            page_count,
            page_after,
            size_before,
            size_after,
            out["bytes_reclaimed"],
        )
        return out
    finally:
        conn.close()
