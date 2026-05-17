#!/usr/bin/env python3
"""超算/批处理：仅写入 scholar_embedding_json，不重建分块与 Ollama/OpenAI 嵌入。"""

from __future__ import annotations

import argparse
import sys

from app.db import init_db
from app.pipeline_logging import setup_logging
from app.services.openscholar_retrieval import openscholar_deps_available, openscholar_retriever_enabled
from app.services.scholar_embed_batch import list_paper_ids_for_scholar_embed, run_scholar_embed_batch


def _argv_for_parse() -> list[str]:
    argv = sys.argv[1:]
    while argv and argv[0] == "--":
        argv = argv[1:]
    return argv


def main() -> None:
    parser = argparse.ArgumentParser(
        description="仅更新 OpenScholar Retriever 向量（scholar_embedding_json）",
    )
    parser.add_argument("--paper-id", action="append", dest="paper_ids", help="指定 paper_id，可重复")
    parser.add_argument("--all", action="store_true", help="所有已有 chunk 的文献")
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="与 --all 合用：仅处理至少有一条缺 scholar 向量的文献（默认推荐）",
    )
    parser.add_argument("--force", action="store_true", help="强制重算已有 scholar 向量")
    parser.add_argument("--no-lance", action="store_true", help="不写入 LanceDB（仅 SQLite）")
    args = parser.parse_args(_argv_for_parse())
    setup_logging()
    init_db()

    if not openscholar_deps_available():
        print("错误: 未安装 OpenScholar 依赖。请执行: pip install -e '.[openscholar]'", file=sys.stderr)
        raise SystemExit(1)
    if not openscholar_retriever_enabled():
        print("错误: OPENSCHOLAR_RETRIEVER_ENABLED=0 或模型加载失败", file=sys.stderr)
        raise SystemExit(1)

    ids = list(args.paper_ids or [])
    if args.all:
        ids = list_paper_ids_for_scholar_embed(missing_only=args.missing_only)
    elif not ids:
        parser.error("请指定 --paper-id、--all，或配合 --missing-only")

    seen: set[str] = set()
    deduped: list[str] = []
    for pid in ids:
        if pid in seen:
            continue
        seen.add(pid)
        deduped.append(pid)

    if not deduped:
        print("没有待处理的文献（chunk 已齐全或库为空）")
        raise SystemExit(0)

    print(f"处理 {len(deduped)} 篇文献 force={args.force} sync_lance={not args.no_lance}", flush=True)
    summary = run_scholar_embed_batch(
        deduped,
        force=args.force,
        sync_lance=not args.no_lance,
    )
    print(
        f"完成: ok={summary['succeeded']} skip={summary['skipped']} "
        f"fail={summary['failed']} total={summary['total']}",
        flush=True,
    )
    for err in summary.get("errors") or []:
        print(f"  fail {err.get('paper_id')}: {err.get('error')}", file=sys.stderr)
    raise SystemExit(1 if summary.get("failed") else 0)


if __name__ == "__main__":
    main()
