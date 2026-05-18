#!/usr/bin/env python3
"""超算/批处理：MinerU 解析 PDF → parsed/document.md（不含分块与嵌入）。"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.db import init_db
from app.pipeline_logging import setup_logging
from app.services.parse_batch import list_paper_ids_for_parse, run_parse_batch


def _argv_for_parse() -> list[str]:
    argv = sys.argv[1:]
    while argv and argv[0] == "--":
        argv = argv[1:]
    return argv


def main() -> None:
    parser = argparse.ArgumentParser(description="批量解析 PDF（parse_only，不写 chunk/向量）")
    parser.add_argument("--paper-id", action="append", dest="paper_ids")
    parser.add_argument("--all", action="store_true", help="所有在超算上能找到 PDF 的文献")
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="仅尚无 document.md 或 PDF 已变更的文献",
    )
    parser.add_argument("--force", action="store_true", help="强制重新解析")
    args = parser.parse_args(_argv_for_parse())
    setup_logging()
    init_db()

    ids = list(args.paper_ids or [])
    if args.all:
        ids = list_paper_ids_for_parse(missing_only=args.missing_only)
    elif not ids:
        parser.error("请指定 --paper-id 或 --all")

    seen: set[str] = set()
    deduped: list[str] = []
    for pid in ids:
        if pid in seen:
            continue
        seen.add(pid)
        deduped.append(pid)

    if not deduped:
        print("没有待解析文献（需可解析的 PDF 路径，见 docs/HPC_PARSE.md）")
        raise SystemExit(0)

    print(f"parse_batch papers={len(deduped)} force={args.force}", flush=True)
    summary = asyncio.run(run_parse_batch(deduped, force=args.force))
    print(
        f"完成: ok={summary['succeeded']} skip={summary['skipped']} fail={summary['failed']} total={summary['total']}",
        flush=True,
    )
    for err in summary.get("errors") or []:
        print(f"  fail {err.get('paper_id')}: {err.get('error')}", file=sys.stderr)
    raise SystemExit(1 if summary.get("failed") else 0)


if __name__ == "__main__":
    main()
