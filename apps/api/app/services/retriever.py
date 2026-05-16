from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
import time

from app.config import settings
from app.db import get_db
from app.pipeline_logging import clip, plog_debug, plog_info
from app.services.chunker import cosine_sim
from app.services.retrieval_scope import (
    RetrievalScope,
    chunk_type_sql_exclude,
    paper_id_filter_sql,
    resolve_paper_ids,
)


def retrieve_limits() -> tuple[int, int]:
    """(top_k_fts, top_k_final) from settings; final 不超过 fts。"""
    fts = settings.retrieve_top_k_fts
    final = min(settings.retrieve_top_k_final, fts)
    return fts, final


def dedupe_chunks_by_text(ranked: list[dict], *, min_chars: int = 48) -> list[dict]:
    """检索结果级去重：相同正文（或前缀指纹）只保留排名最高的一条。"""
    if not ranked:
        return []
    seen: set[str] = set()
    out: list[dict] = []
    for c in ranked:
        text = (c.get("text") or "").strip()
        if not text:
            out.append(c)
            continue
        if len(text) < min_chars:
            key = text
        else:
            key = hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    if len(out) < len(ranked):
        plog_info("retrieve", "chunk 正文去重：%s → %s", len(ranked), len(out))
    return out


def apply_paper_quota(
    ranked: list[dict],
    *,
    max_per_paper: int,
    max_distinct_papers: int | None,
    limit: int,
) -> list[dict]:
    """
    在保持重排顺序的前提下限制单篇 chunk 数与文献篇数，避免一篇 PDF 垄断上下文。
    max_per_paper / max_distinct_papers 为 0 时表示该项不限制。
    """
    if not ranked or limit <= 0:
        return []
    out: list[dict] = []
    per_paper: dict[str, int] = {}
    papers_in_out: set[str] = set()
    for c in ranked:
        pid = str(c.get("paper_id") or "")
        if not pid:
            continue
        if max_per_paper > 0 and per_paper.get(pid, 0) >= max_per_paper:
            continue
        if (
            max_distinct_papers is not None
            and max_distinct_papers > 0
            and pid not in papers_in_out
            and len(papers_in_out) >= max_distinct_papers
        ):
            continue
        out.append(c)
        per_paper[pid] = per_paper.get(pid, 0) + 1
        papers_in_out.add(pid)
        if len(out) >= limit:
            break
    return out


def _finalize_retrieval(candidates: list[dict], top_k_final: int) -> list[dict]:
    """应用跨篇配额并在全量排序列表上回填至 top_k_final（避免仅扫描前 K 条导致条数不足）。"""
    if not candidates or top_k_final <= 0:
        return []
    candidates = dedupe_chunks_by_text(candidates)
    max_per = settings.retrieve_max_chunks_per_paper
    max_papers = settings.retrieve_max_papers
    if max_per <= 0 and max_papers <= 0:
        return candidates[:top_k_final]
    max_distinct = max_papers if max_papers > 0 else None
    max_per_eff = max_per if max_per > 0 else top_k_final
    naive = len(candidates[:top_k_final])
    out = apply_paper_quota(
        candidates,
        max_per_paper=max_per_eff,
        max_distinct_papers=max_distinct,
        limit=top_k_final,
    )
    if len(out) != naive or (len(out) < top_k_final and len(candidates) > len(out)):
        plog_info(
            "retrieve",
            "跨篇配额 max_per_paper=%s max_papers=%s：候选池 %s 条 → 输出 %s 条（目标 %s）",
            max_per_eff,
            max_distinct,
            len(candidates),
            len(out),
            top_k_final,
        )
    return out


# FTS5 查询语法中的保留词；作为「词」出现时需避免参与 MATCH，否则会语法错误或语义错误。
_FTS5_QUERY_RESERVED = frozenset(
    {
        "and",
        "or",
        "not",
        "near",
        "a",
        "an",
        "the",
        "to",
        "of",
        "in",
        "for",
        "on",
        "is",
        "are",
        "as",
        "at",
        "be",
        "by",
        "was",
        "were",
    }
)


def _atomic_search_tokens(query: str, max_tokens: int = 24) -> list[str]:
    """
    拆出 FTS / LIKE 可用的检索词。
    - 英文：multi-point → multi、point，避免 FTS5 把 '-' 当成 NOT。
    - 中文/非 ASCII：按连续非 ASCII、非标点片段提取（与 unicode 词界大致一致）。
    """
    q = query.strip()
    if not q:
        return []
    out: list[str] = []

    def push(p: str) -> None:
        nonlocal out
        p = p.strip()
        if len(p) < 2:
            return
        low = p.lower()
        if low in _FTS5_QUERY_RESERVED:
            return
        if p not in out:
            out.append(p)
        if len(out) >= max_tokens:
            return

    for w in re.findall(r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*", q):
        for part in re.split(r"[-_]+", w):
            push(part.lower())
            if len(out) >= max_tokens:
                return out

    for block in re.findall(r"[^\x00-\x7f\s,.;:!?。，、；：？！\"'（）()\[\]{}]{2,}", q):
        b = block.strip()
        if len(b) > 24:
            b = b[:24]
        push(b)
        if len(out) >= max_tokens:
            return out

    return out


def fts_retrieve(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 40,
    *,
    allowed_paper_ids: set[str] | None = None,
    exclude_chunk_types: list[str] | None = None,
) -> list[dict]:
    tokens = _atomic_search_tokens(query)
    if not tokens:
        plog_info("retrieve", "fts 无检索词（query 过短或仅停用词） preview=%s", clip(query, 120))
        return []
    if allowed_paper_ids is not None and not allowed_paper_ids:
        return []

    match = " OR ".join(tokens)
    plog_info("retrieve", "fts MATCH tokens=%s 条 match预览=%s", len(tokens), clip(match, 200))
    plog_debug("retrieve", "fts token 列表: %s", tokens)
    paper_sql, paper_params = paper_id_filter_sql(allowed_paper_ids, alias="p")
    chunk_sql, chunk_params = chunk_type_sql_exclude(exclude_chunk_types)
    sql = f"""
    SELECT c.chunk_id, c.paper_id, c.body,
           bm25(chunks_fts) AS rank
    FROM chunks_fts c
    JOIN chunks ch ON ch.id = c.chunk_id
    JOIN papers p ON p.id = ch.paper_id AND p.deleted = 0
    WHERE chunks_fts MATCH ?{paper_sql}{chunk_sql}
    ORDER BY rank
    LIMIT ?
    """
    try:
        rows = conn.execute(sql, (match, *paper_params, *chunk_params, limit)).fetchall()
    except sqlite3.OperationalError as e:
        plog_info("retrieve", "fts MATCH 异常，将 LIKE 回退: %s", e)
        rows = []

    if rows:
        plog_info("retrieve", "fts 命中 rows=%s", len(rows))
        return [
            {"chunk_id": r["chunk_id"], "paper_id": r["paper_id"], "text": r["body"], "fts_rank": r["rank"]}
            for r in rows
        ]

    plog_info("retrieve", "fts 零命中，使用 LIKE 回退")
    out = _like_fallback_chunks(
        conn, tokens, limit, allowed_paper_ids=allowed_paper_ids, exclude_chunk_types=exclude_chunk_types
    )
    plog_info("retrieve", "LIKE 回退 命中=%s", len(out))
    return out


def _like_fallback_chunks(
    conn: sqlite3.Connection,
    tokens: list[str],
    limit: int,
    *,
    allowed_paper_ids: set[str] | None = None,
    exclude_chunk_types: list[str] | None = None,
) -> list[dict]:
    if not tokens:
        return []
    if allowed_paper_ids is not None and not allowed_paper_ids:
        return []
    tokens_sorted = sorted(set(tokens), key=len, reverse=True)[:8]
    conds: list[str] = []
    params: list[str] = []
    for t in tokens_sorted:
        conds.append("lower(ch.text) LIKE ?")
        params.append(f"%{t.lower()}%")
    where_sql = " OR ".join(conds)
    paper_sql, paper_params = paper_id_filter_sql(allowed_paper_ids, alias="p")
    chunk_sql, chunk_params = chunk_type_sql_exclude(exclude_chunk_types)
    sql = f"""
    SELECT ch.id AS chunk_id, ch.paper_id, ch.text AS body, 0.0 AS rank
    FROM chunks ch
    JOIN papers p ON p.id = ch.paper_id AND p.deleted = 0
    WHERE ({where_sql}){paper_sql}{chunk_sql}
    LIMIT ?
    """
    params.extend(paper_params)
    params.extend(chunk_params)
    params.append(limit)
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []
    return [
        {"chunk_id": r["chunk_id"], "paper_id": r["paper_id"], "text": r["body"], "fts_rank": r["rank"]}
        for r in rows
    ]


def fts_retrieve_merge(
    conn: sqlite3.Connection,
    queries: list[str],
    *,
    limit_per: int,
    merged_cap: int,
    allowed_paper_ids: set[str] | None = None,
    exclude_chunk_types: list[str] | None = None,
) -> list[dict]:
    best: dict[str, dict] = {}
    seen_q: set[str] = set()
    for q in queries:
        s = (q or "").strip()
        if not s:
            continue
        lk = s.lower()
        if lk in seen_q:
            continue
        seen_q.add(lk)
        for h in fts_retrieve(
            conn,
            s,
            limit=limit_per,
            allowed_paper_ids=allowed_paper_ids,
            exclude_chunk_types=exclude_chunk_types,
        ):
            cid = str(h["chunk_id"])
            r = float(h.get("fts_rank") or 0.0)
            old = best.get(cid)
            if old is None or r < float(old.get("fts_rank") or 0.0):
                best[cid] = h
    merged = sorted(best.values(), key=lambda x: float(x.get("fts_rank") or 0.0))[:merged_cap]
    return merged


def hydrate_chunks(conn: sqlite3.Connection, hits: list[dict]) -> list[dict]:
    if not hits:
        return []
    ids = [h["chunk_id"] for h in hits]
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        f"""
        SELECT ch.id, ch.paper_id, ch.section_title, ch.section_path, ch.page_start, ch.page_end,
               ch.text, ch.embedding_json, ch.scholar_embedding_json, ch.chunk_type,
               p.title AS paper_title
        FROM chunks ch
        JOIN papers p ON p.id = ch.paper_id
        WHERE ch.id IN ({placeholders}) AND p.deleted = 0
        """,
        ids,
    ).fetchall()
    by_id = {r["id"]: dict(r) for r in rows}
    ordered = []
    for h in hits:
        row = by_id.get(h["chunk_id"])
        if not row:
            continue
        ordered.append(
            {
                "chunk_id": row["id"],
                "paper_id": row["paper_id"],
                "title": row["paper_title"],
                "section_path": row["section_path"],
                "page_start": row["page_start"],
                "page_end": row["page_end"],
                "text": row["text"],
                "embedding_json": row["embedding_json"],
                "scholar_embedding_json": row.get("scholar_embedding_json"),
                "chunk_type": row.get("chunk_type"),
                "fts_rank": h.get("fts_rank"),
            }
        )
    return ordered


def _scope_kwargs(scope: RetrievalScope | None) -> tuple[set[str] | None, list[str] | None]:
    if scope is None:
        return None, None
    with get_db() as conn:
        allowed = resolve_paper_ids(conn, scope)
    exclude = scope.exclude_chunk_types or None
    return allowed, exclude


def rrf_merge_ranked_lists(ranked_ids: list[list[str]], *, k: int = 60) -> list[str]:
    """Reciprocal Rank Fusion over chunk_id lists (best first per list)."""
    scores: dict[str, float] = {}
    for lst in ranked_ids:
        for rank, cid in enumerate(lst):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.keys(), key=lambda x: scores[x], reverse=True)


def _dense_rank_chunk_ids(
    query_vec: list[float],
    candidates: list[dict],
    *,
    limit: int,
) -> list[str]:
    from app.services.openscholar_retrieval import encode_passages, openscholar_retriever_enabled, parse_stored_embedding

    scored: list[tuple[float, str]] = []
    need_text: list[tuple[int, str]] = []
    for i, c in enumerate(candidates):
        cid = str(c["chunk_id"])
        vec = parse_stored_embedding(c.get("scholar_embedding_json"))
        if vec is None and openscholar_retriever_enabled():
            need_text.append((i, c["text"]))
        if vec is None:
            continue
        scored.append((cosine_sim(query_vec, vec), cid))

    if need_text and openscholar_retriever_enabled():
        texts = [t for _, t in need_text]
        try:
            fresh = encode_passages(texts)
            for (idx, _), vec in zip(need_text, fresh, strict=True):
                scored.append((cosine_sim(query_vec, vec), str(candidates[idx]["chunk_id"])))
        except Exception as e:
            plog_info("retrieve", "OpenScholar 现场编码 passage 失败: %s", e)

    scored.sort(key=lambda x: x[0], reverse=True)
    seen: set[str] = set()
    out: list[str] = []
    for _, cid in scored:
        if cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
        if len(out) >= limit:
            break
    return out


def _dense_retrieve_all_scholar(
    conn: sqlite3.Connection,
    query_vec: list[float],
    *,
    limit: int,
    allowed_paper_ids: set[str] | None = None,
    exclude_chunk_types: list[str] | None = None,
) -> list[str]:
    from app.services.openscholar_retrieval import parse_stored_embedding

    if allowed_paper_ids is not None and not allowed_paper_ids:
        return []
    paper_sql, paper_params = paper_id_filter_sql(allowed_paper_ids, alias="p")
    chunk_sql, chunk_params = chunk_type_sql_exclude(exclude_chunk_types)
    rows = conn.execute(
        f"""
        SELECT ch.id, ch.scholar_embedding_json
        FROM chunks ch
        JOIN papers p ON p.id = ch.paper_id AND p.deleted = 0
        WHERE ch.scholar_embedding_json IS NOT NULL{paper_sql}{chunk_sql}
        """,
        (*paper_params, *chunk_params),
    ).fetchall()
    scored: list[tuple[float, str]] = []
    for r in rows:
        vec = parse_stored_embedding(r["scholar_embedding_json"])
        if vec is None:
            continue
        scored.append((cosine_sim(query_vec, vec), str(r["id"])))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [cid for _, cid in scored[:limit]]


def _rerank_with_cross_encoder(query: str, candidates: list[dict], top_k: int) -> list[dict]:
    from app.services.openscholar_retrieval import mark_load_failed, openscholar_reranker_enabled, rerank_scores

    if not openscholar_reranker_enabled() or not candidates:
        return candidates
    pool = min(settings.openscholar_rerank_pool, len(candidates))
    pool_cands = candidates[:pool]
    try:
        scores = rerank_scores(query, [c["text"] for c in pool_cands])
    except Exception as e:
        mark_load_failed(str(e), component="reranker")
        plog_info("retrieve", "OpenScholar Reranker 失败，回退 dense/FTS 顺序: %s", e)
        return candidates
    ranked = sorted(zip(scores, pool_cands), key=lambda x: x[0], reverse=True)
    ordered = [c for _, c in ranked]
    seen_ids = {str(c["chunk_id"]) for c in ordered}
    tail = [c for c in candidates if str(c["chunk_id"]) not in seen_ids]
    full = ordered + tail
    if scored := ranked[: min(5, len(ranked))]:
        plog_debug("retrieve", "OpenScholar rerank top 分数: %s", [round(s, 4) for s, _ in scored])
    plog_info(
        "retrieve",
        "OpenScholar Reranker 池=%s 已排序=%s（目标 top_k=%s，跨篇配额后截断）",
        pool,
        len(full),
        top_k,
    )
    return full


def _legacy_vector_rerank(candidates: list[dict], query_vec: list[float], top_k: int) -> list[dict]:
    scored = []
    for c in candidates:
        emb = c.get("embedding_json")
        if not emb:
            scored.append((0.0, c))
            continue
        try:
            vec = json.loads(emb)
        except Exception:
            scored.append((0.0, c))
            continue
        scored.append((cosine_sim(query_vec, vec), c))
    scored.sort(key=lambda x: x[0], reverse=True)
    ordered = [c for _, c in scored]
    if scored:
        plog_debug("retrieve", "Ollama/bge 向量重排 top 相似度: %s", [round(x[0], 4) for x in scored[: min(5, len(scored))]])
    plog_info("retrieve", "Ollama 嵌入重排后排序=%s（目标 top_k=%s）", len(ordered), top_k)
    return ordered


def _openscholar_retrieve_sync(
    query: str,
    queries: list[str],
    *,
    top_k_fts: int,
    top_k_final: int,
    scope: RetrievalScope | None = None,
) -> list[dict]:
    from app.services.openscholar_retrieval import (
        encode_queries,
        mark_load_failed,
        openscholar_deps_available,
        openscholar_reranker_enabled,
        openscholar_retriever_enabled,
    )

    if not openscholar_deps_available():
        plog_info("retrieve", "OpenScholar 未安装依赖 (pip install -e '.[openscholar]')，跳过")
        return []

    use_retriever = openscholar_retriever_enabled()
    use_reranker = openscholar_reranker_enabled()
    if not use_retriever and not use_reranker:
        return []

    try:
        q_vecs = encode_queries([query]) if use_retriever else []
        query_vec = q_vecs[0] if q_vecs else None
    except Exception as e:
        mark_load_failed(str(e), component="retriever")
        plog_info("retrieve", "OpenScholar Retriever 编码 query 失败: %s", e)
        return []

    allowed, exclude_types = _scope_kwargs(scope)
    with get_db() as conn:
        if allowed is None and scope is not None:
            allowed = resolve_paper_ids(conn, scope)
        if len(queries) == 1:
            fts_hits = fts_retrieve(
                conn, queries[0], limit=top_k_fts, allowed_paper_ids=allowed, exclude_chunk_types=exclude_types
            )
        else:
            per = max(10, top_k_fts // len(queries))
            fts_hits = fts_retrieve_merge(
                conn,
                queries,
                limit_per=per,
                merged_cap=top_k_fts,
                allowed_paper_ids=allowed,
                exclude_chunk_types=exclude_types,
            )
        candidates = hydrate_chunks(conn, fts_hits)

        fts_order = [str(c["chunk_id"]) for c in candidates]
        ranked_lists: list[list[str]] = [fts_order] if fts_order else []

        if use_retriever and query_vec:
            dense_from_db = _dense_retrieve_all_scholar(
                conn, query_vec, limit=top_k_fts, allowed_paper_ids=allowed, exclude_chunk_types=exclude_types
            )
            if dense_from_db:
                ranked_lists.append(dense_from_db)
                plog_info("retrieve", "OpenScholar 全库 dense 召回=%s", len(dense_from_db))
            dense_on_fts = _dense_rank_chunk_ids(query_vec, candidates, limit=top_k_fts)
            if dense_on_fts:
                ranked_lists.append(dense_on_fts)

        if len(ranked_lists) > 1:
            merged_ids = rrf_merge_ranked_lists(ranked_lists)
            by_id = {str(c["chunk_id"]): c for c in candidates}
            extra_ids = [cid for cid in merged_ids if cid not in by_id]
            if extra_ids and use_retriever and query_vec:
                placeholders = ",".join("?" * len(extra_ids))
                rows = conn.execute(
                    f"""
                    SELECT ch.id, ch.paper_id, ch.section_title, ch.section_path, ch.page_start, ch.page_end,
                           ch.text, ch.embedding_json, ch.scholar_embedding_json, p.title AS paper_title
                    FROM chunks ch
                    JOIN papers p ON p.id = ch.paper_id
                    WHERE ch.id IN ({placeholders}) AND p.deleted = 0
                    """,
                    extra_ids,
                ).fetchall()
                for r in rows:
                    by_id[str(r["id"])] = {
                        "chunk_id": r["id"],
                        "paper_id": r["paper_id"],
                        "title": r["paper_title"],
                        "section_path": r["section_path"],
                        "page_start": r["page_start"],
                        "page_end": r["page_end"],
                        "text": r["text"],
                        "embedding_json": r["embedding_json"],
                        "scholar_embedding_json": r["scholar_embedding_json"],
                        "fts_rank": None,
                    }
            candidates = [by_id[cid] for cid in merged_ids if cid in by_id]
            plog_info("retrieve", "RRF 合并后候选=%s", len(candidates))
        elif not candidates and use_retriever and query_vec:
            dense_ids = _dense_retrieve_all_scholar(
                conn, query_vec, limit=top_k_fts, allowed_paper_ids=allowed, exclude_chunk_types=exclude_types
            )
            if dense_ids:
                placeholders = ",".join("?" * len(dense_ids))
                rows = conn.execute(
                    f"""
                    SELECT ch.id, ch.paper_id, ch.section_title, ch.section_path, ch.page_start, ch.page_end,
                           ch.text, ch.embedding_json, ch.scholar_embedding_json, p.title AS paper_title
                    FROM chunks ch
                    JOIN papers p ON p.id = ch.paper_id
                    WHERE ch.id IN ({placeholders}) AND p.deleted = 0
                    """,
                    dense_ids,
                ).fetchall()
                by_dense = {str(r["id"]): r for r in rows}
                candidates = []
                for cid in dense_ids:
                    r = by_dense.get(cid)
                    if not r:
                        continue
                    candidates.append(
                        {
                            "chunk_id": r["id"],
                            "paper_id": r["paper_id"],
                            "title": r["paper_title"],
                            "section_path": r["section_path"],
                            "page_start": r["page_start"],
                            "page_end": r["page_end"],
                            "text": r["text"],
                            "embedding_json": r["embedding_json"],
                            "scholar_embedding_json": r["scholar_embedding_json"],
                            "fts_rank": None,
                        }
                    )
                plog_info("retrieve", "FTS 无命中，OpenScholar dense-only 候选=%s", len(candidates))

    if use_reranker:
        return _rerank_with_cross_encoder(query, candidates, top_k_final)
    if use_retriever and query_vec:
        order = _dense_rank_chunk_ids(query_vec, candidates, limit=len(candidates))
        by_id = {str(c["chunk_id"]): c for c in candidates}
        ranked = [by_id[cid] for cid in order if cid in by_id]
        seen = {str(c["chunk_id"]) for c in ranked}
        ranked.extend(c for c in candidates if str(c["chunk_id"]) not in seen)
        return ranked
    return candidates


async def retrieve_for_query(
    query: str,
    top_k_fts: int = 40,
    top_k_final: int = 8,
    query_vec: list[float] | None = None,
    extra_queries: list[str] | None = None,
    scope: RetrievalScope | None = None,
    *,
    include_references: bool = False,
) -> list[dict]:
    t0 = time.monotonic()
    queries: list[str] = [query.strip()]
    if extra_queries:
        base = query.strip().lower()
        seen_lower = {base}
        for eq in extra_queries:
            s = (eq or "").strip()
            if not s:
                continue
            lk = s.lower()
            if lk in seen_lower:
                continue
            seen_lower.add(lk)
            queries.append(s)

    from app.services.openscholar_retrieval import openscholar_reranker_enabled, openscholar_retriever_enabled

    if scope is None and not include_references:
        scope = RetrievalScope(exclude_chunk_types=["references"])
    elif scope is not None and include_references:
        scope = RetrievalScope(
            paper_ids=scope.paper_ids,
            tags_any=scope.tags_any,
            collections_any=scope.collections_any,
            years_min=scope.years_min,
            years_max=scope.years_max,
            exclude_chunk_types=[],
        )

    use_os = openscholar_retriever_enabled() or openscholar_reranker_enabled()
    if use_os:
        plog_info(
            "retrieve",
            "OpenScholar 流水线 retriever=%s reranker=%s",
            openscholar_retriever_enabled(),
            openscholar_reranker_enabled(),
        )
        try:
            top = await asyncio.to_thread(
                _openscholar_retrieve_sync,
                query.strip(),
                queries,
                top_k_fts=top_k_fts,
                top_k_final=top_k_final,
                scope=scope,
            )
            if top:
                top = _finalize_retrieval(top, top_k_final)
                plog_info(
                    "retrieve",
                    "retrieve_for_query (OpenScholar) 返回=%s 耗时=%.2fs",
                    len(top),
                    time.monotonic() - t0,
                )
                return top
        except Exception as e:
            plog_info("retrieve", "OpenScholar 流水线异常，回退 FTS/嵌入: %s", e)

    allowed, exclude_types = _scope_kwargs(scope)
    with get_db() as conn:
        if allowed is None and scope is not None:
            allowed = resolve_paper_ids(conn, scope)
        if len(queries) == 1:
            fts_hits = fts_retrieve(
                conn, queries[0], limit=top_k_fts, allowed_paper_ids=allowed, exclude_chunk_types=exclude_types
            )
        else:
            per = max(10, top_k_fts // len(queries))
            fts_hits = fts_retrieve_merge(
                conn,
                queries,
                limit_per=per,
                merged_cap=top_k_fts,
                allowed_paper_ids=allowed,
                exclude_chunk_types=exclude_types,
            )
        candidates = hydrate_chunks(conn, fts_hits)
    plog_info(
        "retrieve",
        "retrieve_for_query hydrate 后候选=%s (原始命中=%s) 耗时=%.2fs",
        len(candidates),
        len(fts_hits),
        time.monotonic() - t0,
    )

    if query_vec:
        return _finalize_retrieval(_legacy_vector_rerank(candidates, query_vec, top_k_final), top_k_final)

    plog_info("retrieve", "无 query 向量，按 FTS 顺序返回（top_k=%s）", top_k_final)
    return _finalize_retrieval(candidates, top_k_final)
