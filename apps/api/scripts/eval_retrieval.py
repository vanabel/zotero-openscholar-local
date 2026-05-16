#!/usr/bin/env python3
"""P3 检索回归：读取 tests/eval/eval_queries.jsonl，对每条 query 跑 retrieve 并统计命中率。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.db import init_db
from app.pipeline_logging import setup_logging
from app.services.retriever import retrieve


def _load_queries(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    return rows


async def _eval_one(row: dict, *, top_k: int) -> dict:
    q = row.get("query") or ""
    chunks = await retrieve(q, k=top_k)
    paper_ids = [c.get("paper_id") for c in chunks if c.get("paper_id")]
    texts = " ".join((c.get("text") or "") for c in chunks).lower()
    expected_ids = [x for x in (row.get("expected_paper_ids") or []) if x]
    expected_terms = [str(t).lower() for t in (row.get("expected_terms") or []) if t]

    id_hit = bool(expected_ids) and any(pid in paper_ids for pid in expected_ids)
    term_hit = bool(expected_terms) and any(t in texts for t in expected_terms)
    scored = id_hit or term_hit if (expected_ids or expected_terms) else None

    return {
        "query": q,
        "hits": len(chunks),
        "paper_ids_top": paper_ids[:5],
        "id_hit": id_hit,
        "term_hit": term_hit,
        "scored": scored,
        "notes": row.get("notes"),
    }


async def _run(path: Path, *, top_k: int) -> int:
    queries = _load_queries(path)
    if not queries:
        print(f"无查询：{path}", file=sys.stderr)
        return 1
    results = []
    for row in queries:
        results.append(await _eval_one(row, top_k=top_k))
    scored = [r for r in results if r["scored"] is not None]
    ok = sum(1 for r in scored if r["scored"])
    for r in results:
        flag = ""
        if r["scored"] is True:
            flag = " OK"
        elif r["scored"] is False:
            flag = " MISS"
        print(f"- {r['query']!r} hits={r['hits']} papers={r['paper_ids_top']}{flag}")
    if scored:
        print(f"\n命中 {ok}/{len(scored)}（有 expected_* 的条目）")
    else:
        print("\n未配置 expected_paper_ids / expected_terms，仅输出检索结果（请在 jsonl 中填入期望）")
    return 0 if not scored or ok == len(scored) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="检索评测（eval_queries.jsonl）")
    parser.add_argument(
        "--file",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "tests" / "eval" / "eval_queries.jsonl",
    )
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()
    setup_logging()
    init_db()
    raise SystemExit(asyncio.run(_run(args.file, top_k=args.top_k)))


if __name__ == "__main__":
    main()
