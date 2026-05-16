#!/usr/bin/env python3
"""独立任务 Worker：消费 index / summarize 队列（配合 TASK_WORKER_MODE=external）。"""

from __future__ import annotations

import asyncio
import signal

from app.config import settings
from app.db import init_db
from app.pipeline_logging import plog_info, setup_logging
from app.services.task_queue import start_worker, stop_worker


async def _main() -> None:
    setup_logging()
    if settings.task_worker_embedded():
        plog_info(
            "task",
            "TASK_WORKER_MODE=embedded，无需独立 Worker；请设 TASK_WORKER_MODE=external 后重启 API",
        )
        raise SystemExit(1)
    init_db()
    from app.services.index_reconcile import reconcile_database_on_startup

    reconcile_database_on_startup()
    start_worker(standalone=True)
    plog_info("task", "独立 Worker 已启动 DATA_DIR=%s", settings.data_dir)
    stop = asyncio.Event()

    def _handle_sig(*_args: object) -> None:
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_sig)
        except NotImplementedError:
            pass

    await stop.wait()
    await stop_worker()


if __name__ == "__main__":
    asyncio.run(_main())
