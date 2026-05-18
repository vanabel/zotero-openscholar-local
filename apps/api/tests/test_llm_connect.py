"""LLM 连接失败重试与错误信息。"""

import asyncio

import httpx
import pytest

from app.services.llm import LLMConnectionError, LLMClient, _connect_error_message


def test_connect_error_message_ollama():
    msg = _connect_error_message(
        httpx.ConnectError("All connection attempts failed"),
        provider="ollama",
        base_url="http://127.0.0.1:11434",
        model="llama3",
    )
    assert "Ollama" in msg
    assert "ollama serve" in msg


def test_chat_stream_raises_llm_connection_error(monkeypatch):
    calls: list[int] = []

    async def fake_backoff(_a: int) -> None:
        return None

    class FakeClient:
        def stream(self, *args, **kwargs):
            calls.append(1)
            raise httpx.ConnectError("fail", request=httpx.Request("POST", "http://127.0.0.1:11434/api/chat"))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr("app.services.llm._use_openai_chat", lambda: False)
    monkeypatch.setattr("app.services.llm._async_backoff", fake_backoff)
    monkeypatch.setattr("app.services.llm.httpx.AsyncClient", lambda **kw: FakeClient())

    async def run() -> None:
        llm = LLMClient()
        with pytest.raises(LLMConnectionError, match="无法连接 Ollama"):
            async for _ in llm.chat_stream([{"role": "user", "content": "hi"}]):
                pass

    asyncio.run(run())
    assert len(calls) == 4
