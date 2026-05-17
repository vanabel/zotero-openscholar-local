#!/usr/bin/env python3
"""超算/批处理：仅写入 embedding_json（EMBED_PROVIDER=openai，需出网）。"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.config import settings
from app.db import init_db
from app.pipeline_logging import setup_logging
from app.services.embed_batch import list_paper_ids_for_embed, run_embed_batch
from app.services.llm import embed_model_id


def _argv_for_parse() -> list[str]:
    argv = sys.argv[1:]
    while argv and argv[0] == "--":
        argv = argv[1:]
    return argv


def main() -> None:
    parser = argparse.ArgumentParser(description="仅更新 embedding_json（OpenAI 兼容嵌入 API）")
    parser.add_argument("--paper-id", action="append", dest="paper_ids")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--missing-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--batch-size", type=int, default=8, help="每批 chunk 数（默认 8）")
    args = parser.parse_args(_argv_for_parse())
    setup_logging()
    init_db()

    if settings.resolved_embed_provider() != "openai":
        print(
            f"错误: 需 EMBED_PROVIDER=openai 且 OPENAI_API_BASE/KEY；当前为 {settings.resolved_embed_provider()}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    ids = list(args.paper_ids or [])
    if args.all:
        ids = list_paper_ids_for_embed(missing_only=args.missing_only)
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
        print("没有待处理的文献")
        raise SystemExit(0)

    print(f"embed_batch model={embed_model_id()} papers={len(deduped)} force={args.force}", flush=True)
    summary = asyncio.run(
        run_embed_batch(deduped, force=args.force, batch_size=max(1, args.batch_size))
    )
    print(
        f"完成: ok={summary['succeeded']} skip={summary['skipped']} fail={summary['failed']} total={summary['total']}",
        flush=True,
    )
    for err in summary.get("errors") or []:
        print(f"  fail {err.get('paper_id')}: {err.get('error')}", file=sys.stderr)
    raise SystemExit(1 if summary.get("failed") else 0)


if __name__ == "__main__":
    main()
