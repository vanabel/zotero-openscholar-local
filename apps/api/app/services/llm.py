from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.pipeline_logging import clip, plog_debug, plog_info


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def chat_model_id() -> str:
    if settings.openai_api_key and settings.openai_api_base:
        return f"openai:{settings.openai_chat_model}"
    return f"ollama:{settings.ollama_chat_model}"


class LLMClient:
    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.2) -> str:
        use_openai = bool(settings.openai_api_key and settings.openai_api_base)
        plog_info("llm", "chat 开始 provider=%s model=%s temp=%s", "openai" if use_openai else "ollama", settings.openai_chat_model if use_openai else settings.ollama_chat_model, temperature)
        plog_debug("llm", "chat messages 条数=%s 总字符约=%s", len(messages), sum(len(m.get("content") or "") for m in messages))
        t0 = time.monotonic()
        if use_openai:
            base = settings.openai_api_base.rstrip("/")
            url = f"{base}/chat/completions"
            headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
            payload: dict[str, Any] = {
                "model": settings.openai_chat_model,
                "messages": messages,
                "temperature": temperature,
            }
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(url, headers=headers, json=payload)
                r.raise_for_status()
                data = r.json()
                text = data["choices"][0]["message"]["content"]
                plog_info("llm", "chat 完成 耗时=%.2fs 输出字符=%s", time.monotonic() - t0, len(text or ""))
                plog_debug("llm", "chat 输出预览: %s", clip(text or "", 400))
                return text

        url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
        payload = {
            "model": settings.ollama_chat_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        async with httpx.AsyncClient(timeout=300.0) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            text = data.get("message", {}).get("content") or data.get("response") or ""
            plog_info("llm", "chat 完成 耗时=%.2fs 输出字符=%s", time.monotonic() - t0, len(text or ""))
            plog_debug("llm", "chat 输出预览: %s", clip(text or "", 400))
            return text

    async def chat_stream(self, messages: list[dict[str, str]], temperature: float = 0.2) -> AsyncIterator[str]:
        """流式输出模型增量文本（OpenAI / Ollama）。"""
        use_openai = bool(settings.openai_api_key and settings.openai_api_base)
        plog_info("llm", "chat_stream 开始 provider=%s", "openai" if use_openai else "ollama")
        t0 = time.monotonic()
        nchars = 0
        if settings.openai_api_key and settings.openai_api_base:
            base = settings.openai_api_base.rstrip("/")
            url = f"{base}/chat/completions"
            headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
            payload: dict[str, Any] = {
                "model": settings.openai_chat_model,
                "messages": messages,
                "temperature": temperature,
                "stream": True,
            }
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as r:
                    r.raise_for_status()
                    async for line in r.aiter_lines():
                        line = (line or "").strip()
                        if not line or line.startswith(":"):
                            continue
                        if line == "data: [DONE]":
                            break
                        if not line.startswith("data: "):
                            continue
                        try:
                            obj = json.loads(line[6:])
                        except json.JSONDecodeError:
                            continue
                        choices = obj.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        piece = delta.get("content") or ""
                        if piece:
                            nchars += len(piece)
                            yield piece
            plog_info("llm", "chat_stream 结束 耗时=%.2fs 累计字符=%s", time.monotonic() - t0, nchars)
            return

        url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
        payload = {
            "model": settings.ollama_chat_model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature},
        }
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("POST", url, json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    line = (line or "").strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = obj.get("message") or {}
                    piece = msg.get("content") or ""
                    if piece:
                        nchars += len(piece)
                        yield piece
        plog_info("llm", "chat_stream 结束 耗时=%.2fs 累计字符=%s", time.monotonic() - t0, nchars)


class EmbeddingClient:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if settings.openai_api_key and settings.openai_api_base:
            base = settings.openai_api_base.rstrip("/")
            url = f"{base}/embeddings"
            headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
            # OpenAI embeddings API
            plog_info("embed", "embed 开始 provider=openai 条数=%s", len(texts))
            t0 = time.monotonic()
            async with httpx.AsyncClient(timeout=120.0) as client:
                vecs: list[list[float]] = []
                for t in texts:
                    payload = {"model": "text-embedding-3-small", "input": t}
                    r = await client.post(url, headers=headers, json=payload)
                    r.raise_for_status()
                    data = r.json()
                    vecs.append(data["data"][0]["embedding"])
                plog_info("embed", "embed 完成 耗时=%.2fs dim=%s", time.monotonic() - t0, len(vecs[0]) if vecs else 0)
                return vecs

        url = f"{settings.ollama_base_url.rstrip('/')}/api/embeddings"
        plog_info("embed", "embed 开始 provider=ollama model=%s 条数=%s", settings.ollama_embed_model, len(texts))
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=120.0) as client:
            vecs: list[list[float]] = []
            for t in texts:
                r = await client.post(
                    url,
                    json={"model": settings.ollama_embed_model, "prompt": t},
                )
                r.raise_for_status()
                data = r.json()
                emb = data.get("embedding")
                if not emb:
                    raise RuntimeError("Ollama 未返回 embedding，请确认已拉取嵌入模型。")
                vecs.append(emb)
            plog_info("embed", "embed 完成 耗时=%.2fs dim=%s", time.monotonic() - t0, len(vecs[0]) if vecs else 0)
            return vecs


async def try_embed_one(text: str) -> list[float] | None:
    try:
        client = EmbeddingClient()
        v = await client.embed([text])
        return v[0] if v else None
    except Exception as e:
        plog_info("embed", "try_embed_one 失败（将仅用 FTS）: %s", e)
        return None


def build_citation_prompt(
    question: str,
    contexts: list[dict],
    lang: str = "zh",
) -> list[dict[str, str]]:
    """构造「证据 + [n] 引用」消息；范式对齐 OpenScholar 类可核查文献 RAG（非官方模型或语料）。"""
    blocks = []
    for i, c in enumerate(contexts, start=1):
        blocks.append(
            f"[{i}] paper_id={c['paper_id']} chunk_id={c['chunk_id']}\n"
            f"标题: {c.get('title') or '未知'}\n"
            f"章节: {c.get('section_path') or ''}\n"
            f"片段:\n{c['text']}\n"
        )
    ctx = "\n\n".join(blocks)
    if lang == "zh":
        sys = (
            "你是科研文献助手。仅根据提供的片段回答，并在句末使用引用编号如 [1][2]。"
            "不要编造片段中不存在的内容。若证据不足请明确说明。"
        )
        user = f"问题：\n{question}\n\n证据片段：\n{ctx}"
    else:
        sys = "You are a scholarly assistant. Answer only from the provided excerpts. Cite like [1][2]."
        user = f"Question:\n{question}\n\nEvidence:\n{ctx}"
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def new_task_id() -> str:
    return uuid.uuid4().hex


def log_task(conn, task_id: str, task_type: str, paper_id: str | None, status: str, error: str | None = None):
    now = _utc_now()
    conn.execute(
        """
        INSERT INTO tasks(id, task_type, paper_id, status, error, created_at, updated_at)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
          status=excluded.status,
          error=excluded.error,
          updated_at=excluded.updated_at
        """,
        (task_id, task_type, paper_id, status, error, now, now),
    )
