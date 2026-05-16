#!/usr/bin/env python3
"""
在调用 MinerU CLI 前覆盖任务状态轮询间隔（上游 api_client 固定 1s，日志过多）。

由 pdf_parse 用与 MINERU_CLI 同 venv 的 python 执行本脚本；间隔来自环境变量
MINERU_TASK_STATUS_POLL_INTERVAL_SECONDS（apps/api/.env 中 MINERU_TASK_POLL_INTERVAL_SEC）。
"""
from __future__ import annotations

import os
import sys


def main() -> None:
    raw = (os.environ.get("MINERU_TASK_STATUS_POLL_INTERVAL_SECONDS") or "8").strip()
    try:
        interval = float(raw)
    except ValueError:
        print(f"无效的 MINERU_TASK_STATUS_POLL_INTERVAL_SECONDS: {raw!r}", file=sys.stderr)
        raise SystemExit(2)
    interval = max(1.0, min(interval, 120.0))

    import mineru.cli.api_client as api_client

    api_client.TASK_STATUS_POLL_INTERVAL_SECONDS = interval

    from mineru.cli.client import main as mineru_main

    mineru_main()


if __name__ == "__main__":
    main()
