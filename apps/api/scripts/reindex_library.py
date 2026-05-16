#!/usr/bin/env python3
"""复用已解析 Markdown，仅重建分块、FTS 与嵌入（含 scholar_embedding_json）。不调用 MinerU。"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.config import settings
from app.db import get_db, init_db
from app.pipeline_logging import setup_logging
from app.services.indexing import index_paper
from app.services.pdf_parse import load_parsed_markdown


def _paper_ids_with_markdown(*, all_papers: bool, only_unindexed: bool) -> list[str]:
    with get_db() as conn:
        sql = "SELECT id FROM papers WHERE deleted = 0"
        if only_unindexed:
            sql += " AND index_status != 'indexed'"
        rows = conn.execute(sql).fetchall()
    out: list[str] = []
    for r in rows:
        pid = str(r["id"])
        if load_parsed_markdown(settings.parsed_dir / pid) is not None:
            out.append(pid)
        elif not all_papers:
            continue
    return out


async def _run(ids: list[str]) -> int:
    if not ids:
        print("没有可重建索引的文献（需已有 data/parsed/{id}/ 下的 Markdown）")
        return 0
    ok = fail = skip = 0
    for i, pid in enumerate(ids, start=1):
        print(f"[{i}/{len(ids)}] reindex {pid} ...", flush=True)
        res = await index_paper(pid, reindex_only=True)
        if res.get("ok"):
            ok += 1
            print(
                f"  ok chunks={res.get('chunks')} "
                f"embed={res.get('embedding_ok')} scholar={res.get('scholar_embedding_ok')}"
            )
        elif res.get("reused_index"):
            skip += 1
            print("  skip (already indexed, unexpected with reindex_only)")
        else:
            fail += 1
            print(f"  fail: {res.get('error', res)}", file=sys.stderr)
    print(f"完成: ok={ok} fail={fail} skip={skip} total={len(ids)}")
    return 1 if fail else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="仅重建索引（不跑 MinerU）")
    parser.add_argument("--paper-id", action="append", dest="paper_ids", help="指定 paper_id，可重复")
    parser.add_argument("--all", action="store_true", help="所有已有本地 Markdown 的文献")
    parser.add_argument(
        "--unindexed-only",
        action="store_true",
        help="与 --all 合用：仅 index_status != indexed 且有 Markdown 的文献",
    )
    args = parser.parse_args()
    setup_logging()
    init_db()

    ids = list(args.paper_ids or [])
    if args.all:
        ids = _paper_ids_with_markdown(all_papers=True, only_unindexed=args.unindexed_only)
    elif not ids:
        parser.error("请指定 --paper-id 或 --all")

    # dedupe preserve order
    seen: set[str] = set()
    deduped: list[str] = []
    for pid in ids:
        if pid in seen:
            continue
        seen.add(pid)
        deduped.append(pid)

    raise SystemExit(asyncio.run(_run(deduped)))


if __name__ == "__main__":
    main()
