#!/usr/bin/env python3
"""
在调用 MinerU CLI 前覆盖任务状态轮询间隔（MinerU 3.x 的 api_client 默认 1s，日志过多）。

MinerU 2.2.x 无 mineru.cli.api_client，仅跳过轮询补丁，仍转发到 mineru.cli.client。

由 pdf_parse 用与 MINERU_CLI 同 venv 的 python 执行；间隔来自
MINERU_TASK_STATUS_POLL_INTERVAL_SECONDS（apps/api/.env 中 MINERU_TASK_POLL_INTERVAL_SEC）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


_SHIM_DIR = Path(__file__).resolve().parent / "mineru_shims"


def _prepend_shim_path() -> None:
    shim = str(_SHIM_DIR)
    if shim not in sys.path:
        sys.path.insert(0, shim)
    parts = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
    if shim not in parts:
        os.environ["PYTHONPATH"] = os.pathsep.join([shim, *parts])


def _install_magika_fallback() -> None:
    """
    SWU 的 Python 3.12 / CentOS7 无 onnxruntime wheel；MinerU 3.x 仅用 magika 判断
    输入文件类型/少量语言标签。若真实 magika 因缺 onnxruntime 不可导入，提供足够用于
    PDF CLI 的轻量 shim。
    """
    try:
        import magika  # noqa: F401
        return
    except ModuleNotFoundError as e:
        if e.name not in {"magika", "onnxruntime"}:
            raise
    _prepend_shim_path()
    sys.modules.pop("magika", None)
    import magika  # type: ignore[import-not-found] # noqa: F401


def _patch_poll_interval(interval: float) -> None:
    try:
        import mineru.cli.api_client as api_client
    except ModuleNotFoundError:
        return
    api_client.TASK_STATUS_POLL_INTERVAL_SECONDS = interval


def _run_mineru_main() -> None:
    _install_magika_fallback()
    try:
        from mineru.cli.client import main as mineru_main
    except ImportError as e:
        if getattr(e, "name", None) != "mineru.cli.client":
            raise
        from mineru.cli import main as mineru_main  # type: ignore[attr-defined]
    mineru_main()


def main() -> None:
    raw = (os.environ.get("MINERU_TASK_STATUS_POLL_INTERVAL_SECONDS") or "8").strip()
    try:
        interval = float(raw)
    except ValueError:
        print(f"无效的 MINERU_TASK_STATUS_POLL_INTERVAL_SECONDS: {raw!r}", file=sys.stderr)
        raise SystemExit(2)
    interval = max(1.0, min(interval, 120.0))

    _patch_poll_interval(interval)
    _run_mineru_main()


if __name__ == "__main__":
    main()
