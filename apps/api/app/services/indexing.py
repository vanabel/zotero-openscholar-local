from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.db import get_db
from app.pipeline_logging import plog_info
from app.services.chunker import chunk_markdown, estimate_tokens, stable_chunk_id
from app.services.llm import EmbeddingClient
from app.services.pdf_parse import (
    clear_parsed_output_dir,
    load_parsed_markdown,
    parse_one,
    parsed_pdf_sha256,
    sha256_text,
)
from app.services.task_queue import TaskProgress
from app.services.zotero_scanner import get_paper


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parsed_dir(paper_id: str) -> Path:
    return settings.parsed_dir / paper_id


def _chunk_count(paper_id: str) -> int:
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM chunks WHERE paper_id = ?", (paper_id,)).fetchone()
        return int(row["c"]) if row else 0


async def index_paper(
    paper_id: str,
    force: bool = False,
    *,
    reindex_only: bool = False,
    progress: TaskProgress | None = None,
) -> dict:
    t0 = time.monotonic()
    plog_info(
        "index",
        "index_paper 开始 paper_id=%s force=%s reindex_only=%s",
        paper_id,
        force,
        reindex_only,
    )
    if reindex_only and force:
        return {"ok": False, "error": "reindex_only 与 force 不能同时使用（前者仅重建分块/嵌入，不跑 MinerU）"}
    paper = get_paper(paper_id)
    if not paper or paper.get("deleted"):
        return {"ok": False, "error": "文献不存在或已归档"}

    pdf_path = Path(paper["pdf_path"])
    if not pdf_path.exists():
        return {"ok": False, "error": "PDF 文件不存在"}

    out_dir = _parsed_dir(paper_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    reused_parse = False
    reused_index = False
    pdf_sha = paper.get("sha256") or ""
    stored_pdf_sha = parsed_pdf_sha256(out_dir)
    pdf_changed = bool(stored_pdf_sha and pdf_sha and stored_pdf_sha != pdf_sha)

    if reindex_only:
        loaded = load_parsed_markdown(out_dir)
        if loaded is None:
            return {
                "ok": False,
                "error": "无本地 Markdown，请先完成解析（网页「建立索引」或 index?force=true）",
            }
        need_parse = False
    else:
        loaded = None if force else load_parsed_markdown(out_dir)
        need_parse = force or loaded is None or pdf_changed

    if pdf_changed and loaded and not force:
        plog_info(
            "index",
            "PDF 已变更（meta pdf_sha256=%s != 当前 %s），将重新解析",
            stored_pdf_sha[:12] if stored_pdf_sha else "?",
            pdf_sha[:12] if pdf_sha else "?",
        )

    if need_parse:
        if force:
            cleared = clear_parsed_output_dir(out_dir)
            plog_info("index", "强制重建：已清空解析缓存目录 %s（%s 项）", out_dir, cleared)
        if progress:
            progress.update("parse", 0, 1, "MinerU 解析中…")
        md, meta = await asyncio.to_thread(
            parse_one,
            paper_id,
            pdf_path,
            out_dir,
            force_reparse=force,
            pdf_sha256=(pdf_sha.strip() or None) if pdf_sha else None,
        )
        if progress:
            progress.update("parse", 1, 1, "解析完成")
        meta["pdf_sha256"] = pdf_sha
        (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        md_hash = sha256_text(md)
        title_guess = pdf_path.stem
        first_line = md.splitlines()[0] if md else ""
        if first_line.startswith("# "):
            title_guess = first_line[2:].strip()
        with get_db() as conn:
            conn.execute(
                """
                UPDATE papers SET
                  title = COALESCE(NULLIF(?, ''), title),
                  parse_status = 'parsed',
                  md_sha256 = ?,
                  index_status = 'pending',
                  updated_at = ?
                WHERE id = ?
                """,
                (title_guess, md_hash, _utc_now(), paper_id),
            )
    else:
        md, _md_path = loaded
        md_hash = sha256_text(md)
        reused_parse = True
        plog_info("index", "复用本地 Markdown，跳过 MinerU/解析 paper_id=%s md_chars=%s", paper_id, len(md))
        meta_path = out_dir / "meta.json"
        if pdf_sha:
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
                if not isinstance(meta, dict):
                    meta = {}
                if meta.get("pdf_sha256") != pdf_sha:
                    meta["pdf_sha256"] = pdf_sha
                    meta.setdefault("mode", "cached_markdown")
                    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                pass
        with get_db() as conn:
            conn.execute(
                """
                UPDATE papers SET
                  parse_status = 'parsed',
                  md_sha256 = ?,
                  updated_at = ?
                WHERE id = ?
                """,
                (md_hash, _utc_now(), paper_id),
            )

    if (
        not reindex_only
        and not force
        and paper.get("index_status") == "indexed"
        and paper.get("md_sha256") == md_hash
        and _chunk_count(paper_id) > 0
    ):
        reused_index = True
        plog_info("index", "复用已有分块与嵌入，跳过重建 paper_id=%s chunks=%s", paper_id, _chunk_count(paper_id))
        with get_db() as conn:
            conn.execute(
                "UPDATE papers SET index_status='indexed', updated_at=? WHERE id=?",
                (_utc_now(), paper_id),
            )
        return {
            "ok": True,
            "paper_id": paper_id,
            "chunks": _chunk_count(paper_id),
            "markdown_hash": md_hash,
            "embedding_ok": None,
            "reused_parse": reused_parse,
            "reused_index": True,
            "elapsed_sec": round(time.monotonic() - t0, 2),
        }

    if progress:
        progress.update("chunk", 0, 1, "分块中…")
    drafts = chunk_markdown(md)
    if progress:
        progress.update("chunk", 1, 1, f"共 {len(drafts)} 个片段")
    embed_client = EmbeddingClient()
    texts = [d.text for d in drafts]

    embeddings: list[list[float] | None] = [None] * len(texts)
    batch = 8
    n_texts = len(texts)
    for i in range(0, n_texts, batch):
        slice_t = texts[i : i + batch]
        done = min(i + len(slice_t), n_texts)
        if progress:
            progress.update("embed", done, n_texts)
        try:
            vecs = await embed_client.embed(slice_t)
            for j, v in enumerate(vecs):
                embeddings[i + j] = v
        except Exception as e:
            plog_info("index", "嵌入批次失败 [%s:%s]: %s", i, i + len(slice_t), e)
            for j in range(len(slice_t)):
                embeddings[i + j] = None

    scholar_embeddings: list[list[float] | None] = [None] * len(texts)
    from app.services.openscholar_retrieval import encode_passages, openscholar_retriever_enabled

    if openscholar_retriever_enabled():
        plog_info("index", "OpenScholar Retriever 嵌入开始 chunks=%s", len(texts))
        sb = settings.openscholar_encode_batch_size
        try:

            def _encode_scholar_batch(slice_t: list[str]) -> list[list[float]]:
                return encode_passages(slice_t)

            for i in range(0, len(texts), sb):
                slice_t = texts[i : i + sb]
                done = min(i + len(slice_t), len(texts))
                if progress:
                    progress.update("scholar_embed", done, len(texts))
                vecs = await asyncio.to_thread(_encode_scholar_batch, slice_t)
                for j, v in enumerate(vecs):
                    scholar_embeddings[i + j] = v
        except Exception as e:
            plog_info("index", "OpenScholar Retriever 嵌入失败（将仅依赖 FTS/运行时编码）: %s", e)
            scholar_embeddings = [None] * len(texts)
        else:
            plog_info(
                "index",
                "OpenScholar Retriever 嵌入完成 ok=%s",
                sum(1 for e in scholar_embeddings if e is not None),
            )

    if progress:
        progress.update("save", 0, 1, "写入数据库…")
    with get_db() as conn:
        conn.execute("DELETE FROM chunks WHERE paper_id = ?", (paper_id,))
        conn.execute("DELETE FROM chunks_fts WHERE paper_id = ?", (paper_id,))

        for d, emb, s_emb in zip(drafts, embeddings, scholar_embeddings, strict=True):
            cid = stable_chunk_id(paper_id, d.section_path, d.chunk_index)
            emb_json = json.dumps(emb, ensure_ascii=False) if emb is not None else None
            scholar_json = json.dumps(s_emb, ensure_ascii=False) if s_emb is not None else None
            tok = estimate_tokens(d.text)
            conn.execute(
                """
                INSERT INTO chunks(
                  id, paper_id, section_title, section_path, page_start, page_end,
                  chunk_index, text, token_count, embedding_json, scholar_embedding_json, created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    cid,
                    paper_id,
                    d.section_title,
                    d.section_path,
                    d.page_start,
                    d.page_end,
                    d.chunk_index,
                    d.text,
                    tok,
                    emb_json,
                    scholar_json,
                    _utc_now(),
                ),
            )
            conn.execute(
                "INSERT INTO chunks_fts(chunk_id, paper_id, body) VALUES(?,?,?)",
                (cid, paper_id, d.text),
            )

        conn.execute(
            """
            UPDATE papers SET index_status='indexed', md_sha256=?, updated_at=? WHERE id=?
            """,
            (md_hash, _utc_now(), paper_id),
        )
    if progress:
        progress.update("save", 1, 1, "完成")

    scholar_ok = sum(1 for e in scholar_embeddings if e is not None)
    plog_info(
        "index",
        "index_paper 完成 paper_id=%s chunks=%s embedding_ok=%s scholar_ok=%s reused_parse=%s reindex_only=%s 总耗时=%.2fs",
        paper_id,
        len(drafts),
        sum(1 for e in embeddings if e is not None),
        scholar_ok,
        reused_parse,
        reindex_only,
        time.monotonic() - t0,
    )
    return {
        "ok": True,
        "paper_id": paper_id,
        "chunks": len(drafts),
        "markdown_hash": md_hash,
        "embedding_ok": sum(1 for e in embeddings if e is not None),
        "scholar_embedding_ok": scholar_ok,
        "reused_parse": reused_parse,
        "reused_index": False,
        "reindex_only": reindex_only,
        "elapsed_sec": round(time.monotonic() - t0, 2),
    }
