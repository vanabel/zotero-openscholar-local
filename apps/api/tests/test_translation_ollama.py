"""翻译提示与可选 Ollama 冒烟（默认跳过，不依赖本机模型）。"""

from __future__ import annotations

import os

import httpx
import pytest

from app.services.translation import _hunyuan_zh_to_xx


def test_hunyuan_zh_to_en_prompt_matches_official_wrap():
    """与 `ollama run … "将以下文本翻译为英语…\\n\\n你好世界"` 内层正文一致。"""
    body = "你好世界"
    out = _hunyuan_zh_to_xx(body, "英语")
    assert "将以下文本翻译为英语" in out
    assert "不要额外解释" in out
    assert "你好世界" in out


def test_ollama_api_chat_hy_mt_zh_to_en_hello_world():
    """
    等价于 CLI：
    ollama run hy-mt:1.5 "将以下文本翻译为英语，注意只需要输出翻译后的结果，不要额外解释：

    你好世界"
    默认跳过；本机已拉起 Ollama 且已 create 模型时：RUN_OLLAMA_TRANSLATION_TEST=1 pnpm test
    """
    if os.environ.get("RUN_OLLAMA_TRANSLATION_TEST") != "1":
        pytest.skip("设置 RUN_OLLAMA_TRANSLATION_TEST=1 以启用 Ollama 翻译冒烟")

    base = (
        os.environ.get("OLLAMA_TRANSLATION_TEST_URL")
        or os.environ.get("OLLAMA_BASE_URL")
        or "http://127.0.0.1:11434"
    ).rstrip("/")
    model = os.environ.get("OLLAMA_TRANSLATION_TEST_MODEL", "hy-mt:1.5")
    prompt = (
        "将以下文本翻译为英语，注意只需要输出翻译后的结果，不要额外解释：\n\n"
        "你好世界"
    )
    url = f"{base}/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "temperature": 0.7,
            "top_k": 20,
            "top_p": 0.6,
            "repeat_penalty": 1.05,
        },
    }
    try:
        r = httpx.post(url, json=payload, timeout=120.0)
    except httpx.ConnectError as e:
        pytest.skip(f"Ollama 不可达 {url}: {e}")
    if r.status_code != 200:
        pytest.skip(f"Ollama 返回 {r.status_code}: {r.text[:300]!r}")

    data = r.json()
    text = ((data.get("message") or {}).get("content") or "").strip()
    assert len(text) > 0, "空回复"
    assert len(text) < 800, f"回复过长，疑似跑题续写: {text[:400]!r}"
    lo = text.lower()
    assert any(k in lo for k in ("hello", "world", "hi")), f"未出现常见英译词: {text!r}"
