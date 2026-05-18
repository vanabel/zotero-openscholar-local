from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.pipeline_logging import clip, plog_debug, plog_info


class LLMConnectionError(RuntimeError):
    """LLM 服务不可达（Ollama 未启动、DNS、网络等）。"""


_LLM_CONNECT_RETRIES = 4

_TRANSIENT_HTTPX: tuple[type[BaseException], ...] = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.RemoteProtocolError,
    httpx.PoolTimeout,
)


def _http_status_retryable(status_code: int) -> bool:
    return status_code in (429, 502, 503, 504)


async def _async_backoff(attempt: int) -> None:
    await asyncio.sleep(min(2.0 * (2**attempt), 30.0))


def _connect_error_message(
    exc: BaseException,
    *,
    provider: str,
    base_url: str,
    model: str,
) -> str:
    if provider == "ollama":
        return (
            f"无法连接 Ollama（{base_url}，模型 {model}）：{exc}。"
            "请确认已运行 `ollama serve`，且 `ollama pull` 已拉取该模型。"
        )
    return f"无法连接 OpenAI 兼容 API（{base_url}，模型 {model}）：{exc}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chat_provider_name() -> str:
    return settings.resolved_chat_provider()


def _use_openai_chat() -> bool:
    return _chat_provider_name() == "openai"


def _use_transformers_chat() -> bool:
    return _chat_provider_name() == "transformers"


def _use_openai_embed() -> bool:
    return settings.resolved_embed_provider() == "openai"


def _require_openai(capability: str) -> None:
    if not settings.openai_ready():
        raise RuntimeError(
            f"{capability} 使用 OpenAI 兼容 API 需要配置 OPENAI_API_BASE 与 OPENAI_API_KEY，"
            "或将 CHAT_PROVIDER / EMBED_PROVIDER 设为 ollama。"
        )


def chat_model_id() -> str:
    if _use_openai_chat():
        return f"openai:{settings.openai_chat_model}"
    if _use_transformers_chat():
        return f"transformers:{settings.effective_openscholar_chat_model()}"
    return f"ollama:{settings.ollama_chat_model}"


def embed_model_id() -> str:
    if _use_openai_embed():
        return f"openai:{settings.openai_embed_model}"
    return f"ollama:{settings.ollama_embed_model}"


class LLMClient:
    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.2) -> str:
        use_openai = _use_openai_chat()
        use_transformers = _use_transformers_chat()
        provider = _chat_provider_name()
        model = (
            settings.openai_chat_model
            if use_openai
            else settings.effective_openscholar_chat_model()
            if use_transformers
            else settings.ollama_chat_model
        )
        plog_info("llm", "chat 开始 provider=%s model=%s temp=%s", provider, model, temperature)
        plog_debug("llm", "chat messages 条数=%s 总字符约=%s", len(messages), sum(len(m.get("content") or "") for m in messages))
        t0 = time.monotonic()
        if use_transformers:
            from app.services.openscholar_chat import chat_transformers

            text = await chat_transformers(messages, temperature)
            plog_info("llm", "chat 完成 耗时=%.2fs 输出字符=%s", time.monotonic() - t0, len(text or ""))
            return text
        if use_openai:
            _require_openai("对话")
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
        last: BaseException | None = None
        for attempt in range(_LLM_CONNECT_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=300.0) as client:
                    r = await client.post(url, json=payload)
                    r.raise_for_status()
                    data = r.json()
                    text = data.get("message", {}).get("content") or data.get("response") or ""
                    plog_info("llm", "chat 完成 耗时=%.2fs 输出字符=%s", time.monotonic() - t0, len(text or ""))
                    plog_debug("llm", "chat 输出预览: %s", clip(text or "", 400))
                    return text
            except httpx.HTTPStatusError as e:
                if _http_status_retryable(e.response.status_code) and attempt + 1 < _LLM_CONNECT_RETRIES:
                    plog_info("llm", "chat Ollama HTTP %s（尝试 %s/%s）", e.response.status_code, attempt + 1, _LLM_CONNECT_RETRIES)
                    await _async_backoff(attempt)
                    continue
                raise
            except _TRANSIENT_HTTPX as e:
                last = e
                plog_info("llm", "chat Ollama 连接失败（尝试 %s/%s）: %s", attempt + 1, _LLM_CONNECT_RETRIES, e)
                if attempt + 1 < _LLM_CONNECT_RETRIES:
                    await _async_backoff(attempt)
                    continue
        raise LLMConnectionError(
            _connect_error_message(
                last or RuntimeError("unknown"),
                provider="ollama",
                base_url=settings.ollama_base_url,
                model=settings.ollama_chat_model,
            )
        ) from last

    async def chat_stream(self, messages: list[dict[str, str]], temperature: float = 0.2) -> AsyncIterator[str]:
        """流式输出模型增量文本（OpenAI / Ollama / Transformers OpenScholar）。"""
        use_openai = _use_openai_chat()
        use_transformers = _use_transformers_chat()
        plog_info("llm", "chat_stream 开始 provider=%s", _chat_provider_name())
        t0 = time.monotonic()
        nchars = 0
        if use_transformers:
            from app.services.openscholar_chat import chat_transformers_stream

            async for piece in chat_transformers_stream(messages, temperature):
                nchars += len(piece)
                yield piece
            plog_info("llm", "chat_stream 结束 耗时=%.2fs 累计字符=%s", time.monotonic() - t0, nchars)
            return
        if use_openai:
            _require_openai("对话流式")
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
        last: BaseException | None = None
        for attempt in range(_LLM_CONNECT_RETRIES):
            try:
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
                return
            except httpx.HTTPStatusError as e:
                if _http_status_retryable(e.response.status_code) and attempt + 1 < _LLM_CONNECT_RETRIES:
                    plog_info(
                        "llm",
                        "chat_stream Ollama HTTP %s（尝试 %s/%s）",
                        e.response.status_code,
                        attempt + 1,
                        _LLM_CONNECT_RETRIES,
                    )
                    await _async_backoff(attempt)
                    continue
                raise
            except _TRANSIENT_HTTPX as e:
                last = e
                plog_info(
                    "llm",
                    "chat_stream Ollama 连接失败（尝试 %s/%s）: %s",
                    attempt + 1,
                    _LLM_CONNECT_RETRIES,
                    e,
                )
                if attempt + 1 < _LLM_CONNECT_RETRIES:
                    await _async_backoff(attempt)
                    continue
        raise LLMConnectionError(
            _connect_error_message(
                last or RuntimeError("unknown"),
                provider="ollama",
                base_url=settings.ollama_base_url,
                model=settings.ollama_chat_model,
            )
        ) from last


class EmbeddingClient:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if _use_openai_embed():
            _require_openai("嵌入")
            base = settings.openai_api_base.rstrip("/")
            url = f"{base}/embeddings"
            headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
            model = settings.openai_embed_model
            plog_debug("embed", "embed 开始 provider=openai model=%s 条数=%s", model, len(texts))
            t0 = time.monotonic()
            async with httpx.AsyncClient(timeout=120.0) as client:
                vecs: list[list[float]] = []
                for t in texts:
                    payload = {"model": model, "input": t}
                    r = await client.post(url, headers=headers, json=payload)
                    r.raise_for_status()
                    data = r.json()
                    vecs.append(data["data"][0]["embedding"])
                plog_debug("embed", "embed 完成 耗时=%.2fs dim=%s", time.monotonic() - t0, len(vecs[0]) if vecs else 0)
                return vecs

        url = f"{settings.ollama_base_url.rstrip('/')}/api/embeddings"
        plog_debug("embed", "embed 开始 provider=ollama model=%s 条数=%s", settings.ollama_embed_model, len(texts))
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
            plog_debug("embed", "embed 完成 耗时=%.2fs dim=%s", time.monotonic() - t0, len(vecs[0]) if vecs else 0)
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
        cid = c["chunk_id"]
        blocks.append(
            f"[CHUNK:{cid}] (序号 [{i}])\n"
            f"paper_id={c['paper_id']}\n"
            f"标题: {c.get('title') or '未知'}\n"
            f"章节: {c.get('section_path') or ''}\n"
            f"片段:\n{c['text']}\n"
        )
    ctx = "\n\n".join(blocks)
    if lang == "zh":
        sys = (
            "你是科研文献助手。仅根据提供的片段回答。"
            "每个事实性陈述句末必须使用证据锁定引用 [CHUNK:片段ID]（ID 见各块首行，不要用自编 [1][2]）。"
            "不要编造片段中不存在的内容。若证据不足请明确说明。"
        )
        user = f"问题：\n{question}\n\n证据片段：\n{ctx}"
    else:
        sys = (
            "You are a scholarly assistant. Answer only from the provided excerpts. "
            "Cite facts with evidence locks [CHUNK:fragment_id] from each block header (not ad-hoc [1][2])."
        )
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
