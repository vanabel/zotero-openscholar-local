from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import AsyncIterator
from typing import Any, Literal

import httpx

from app.config import settings
from app.pipeline_logging import clip, one_line, plog_debug, plog_info

log = logging.getLogger(__name__)

TargetLang = Literal["zh", "en"]

# HY-MT1.5 官方：无默认 system；ZH<=>XX 须用「将以下文本翻译为…」包装（见 tencent/HY-MT1.5-1.8B-GGUF README）。
def _hunyuan_zh_to_xx(source_text: str, target_language_cn: str) -> str:
    return (
        f"将以下文本翻译为{target_language_cn}，注意只需要输出翻译后的结果，不要额外解释：\n\n"
        f"{source_text.strip()}"
    )


_QUERY_JSON_INNER = """任务：根据用户问题生成用于文献检索的中英两种表述。
只输出一行 JSON（不要 markdown、不要其它说明），格式为：
{"zh":"中文表述（用于检索）","en":"English phrasing (for retrieval)"}
若原文已是中文，zh 可与原文一致或略规范化；若已是英文，en 可与原文一致。

用户问题：
"""


_TARGET_CN: dict[TargetLang, str] = {"zh": "中文", "en": "英语"}


def _answer_translate_prompt(answer: str, target_lang: TargetLang) -> str:
    """
    Hy-MT 官方用法：单层「将以下文本翻译为…」+ 正文。
    勿在正文内再嵌英文任务说明，否则易混语种或复读提示词。
    """
    cite = "保持 [1]、[2] 等引用编号不变，"
    return (
        f"将以下文本翻译为{_TARGET_CN[target_lang]}，{cite}"
        f"注意只需要输出翻译后的结果，不要额外解释：\n\n"
        f"{answer.strip()}"
    )


def _translation_base_url() -> str:
    u = (settings.translation_ollama_url or settings.ollama_base_url or "").rstrip("/")
    return u or "http://127.0.0.1:11434"


def _has_translation_model() -> bool:
    return bool(settings.translation_ollama_model.strip())


def translation_model_configured() -> bool:
    """已配置翻译模型（与 BILINGUAL_* 开关无关，供按需翻译接口使用）。"""
    return _has_translation_model()


def translation_for_retrieval_enabled() -> bool:
    return bool(settings.bilingual_retrieval and _has_translation_model())


def translation_for_answer_enabled() -> bool:
    return bool(settings.bilingual_answer and _has_translation_model())


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    m = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", t, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return t


_QUERY_JSON_KEYS_ZH = ("zh", "chinese", "query_zh", "zh_query", "中文")
_QUERY_JSON_KEYS_EN = ("en", "english", "query_en", "en_query", "英文")


def _norm_query_field(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _pick_query_field(obj: dict, keys: tuple[str, ...]) -> str | None:
    for k in keys:
        if k in obj:
            got = _norm_query_field(obj[k])
            if got:
                return got
    for k, v in obj.items():
        if str(k).lower() in keys:
            got = _norm_query_field(v)
            if got:
                return got
    return None


def _parse_query_json_regex(t: str) -> tuple[str | None, str | None]:
    zh: str | None = None
    en: str | None = None
    for key in ("zh", "chinese", "中文"):
        m = re.search(rf'["\']?{re.escape(key)}["\']?\s*[:=]\s*["\']([^"\']+)["\']', t, re.I)
        if m:
            zh = m.group(1).strip() or None
            break
    for key in ("en", "english", "英文"):
        m = re.search(rf'["\']?{re.escape(key)}["\']?\s*[:=]\s*["\']([^"\']+)["\']', t, re.I)
        if m:
            en = m.group(1).strip() or None
            break
    return zh, en


def _parse_query_json(raw: str) -> tuple[str | None, str | None]:
    t = _strip_json_fence(raw)
    obj: Any = None
    try:
        obj = json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", t)
        if m:
            try:
                obj = json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    if isinstance(obj, dict):
        zs = _pick_query_field(obj, _QUERY_JSON_KEYS_ZH)
        es = _pick_query_field(obj, _QUERY_JSON_KEYS_EN)
        if zs or es:
            return zs, es
    return _parse_query_json_regex(t)


def _is_mostly_cjk(text: str) -> bool:
    letters = [c for c in text if not c.isspace()]
    if not letters:
        return False
    cjk = sum(1 for c in letters if "\u4e00" <= c <= "\u9fff")
    return cjk / len(letters) >= 0.25


async def _translate_retrieval_phrase(q: str, target_lang: TargetLang) -> str | None:
    raw = await _ollama_chat(
        [{"role": "user", "content": _hunyuan_zh_to_xx(q, _TARGET_CN[target_lang])}],
        temperature=settings.translation_temperature,
        purpose=f"检索扩展回退→{target_lang}",
        source_chars=len(q),
    )
    out = _sanitize_translation_output(raw)
    return out if out and out.strip().lower() != q.strip().lower() else None


async def _fallback_retrieval_queries(q: str) -> tuple[str | None, str | None]:
    """JSON 解析失败时：保留原问句一侧，另一侧用 Hy-MT 直译。"""
    if _is_mostly_cjk(q):
        en = await _translate_retrieval_phrase(q, "en")
        plog_info("translate", "检索扩展 回退(原文偏中文) zh=原文 en=%s", clip(str(en or ""), 60))
        return q, en
    zh = await _translate_retrieval_phrase(q, "zh")
    plog_info("translate", "检索扩展 回退(原文偏英文) zh=%s en=原文", clip(str(zh or ""), 60))
    return zh, q


def _translate_messages(answer: str, target_lang: TargetLang) -> list[dict[str, str]]:
    return [{"role": "user", "content": _answer_translate_prompt(answer, target_lang)}]


def _ollama_options(temperature: float, *, num_predict: int | None = None) -> dict[str, float | int]:
    opts: dict[str, float | int] = {
        "temperature": temperature,
        "top_k": 20,
        "top_p": 0.6,
        "repeat_penalty": 1.18,
    }
    if num_predict is not None:
        opts["num_predict"] = num_predict
    return opts


def _estimate_num_predict(source_chars: int) -> int:
    """限制生成长度，减轻 Hy-MT 流式复读。"""
    return min(max(int(source_chars * 1.35) + 64, 256), 12_000)


def _collapse_repeated_paragraphs(text: str) -> str:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if not paras:
        return text.strip()
    out: list[str] = []
    prev = ""
    for p in paras:
        if p == prev:
            continue
        out.append(p)
        prev = p
    return "\n\n".join(out)


def _stream_hit_repetition(accumulated: str) -> bool:
    """检测尾部是否已进入周期性复读。"""
    if len(accumulated) < 500:
        return False
    tail = accumulated[-1200:]
    for period in range(80, min(400, len(tail) // 3)):
        chunk = tail[-period:]
        if len(chunk) < 40:
            continue
        if tail.count(chunk) >= 3:
            return True
    return False


def _sanitize_translation_output(text: str) -> str:
    t = text.strip()
    if not t:
        return t
    lines = t.splitlines()
    while lines and any(
        lines[0].startswith(p)
        for p in (
            "将以下文本翻译为",
            "将以下学术回答翻译为",
            "以下为带引用标记",
            "Translation:",
            "以下是翻译",
        )
    ):
        lines.pop(0)
    t = "\n".join(lines).strip() or t
    return _collapse_repeated_paragraphs(t)


async def _ollama_chat_stream(
    messages: list[dict[str, str]],
    *,
    temperature: float,
    purpose: str,
    source_chars: int = 0,
) -> AsyncIterator[str]:
    base = _translation_base_url()
    model = settings.translation_ollama_model.strip()
    if not model:
        raise ValueError("translation model not set")
    url = f"{base}/api/chat"
    prompt_chars = sum(len(m.get("content") or "") for m in messages)
    plog_info(
        "translate",
        "%s 流式请求 model=%s url=%s temp=%s prompt_chars=%s",
        purpose,
        model,
        base,
        temperature,
        prompt_chars,
    )
    plog_debug("translate", "%s prompt_preview=%s", purpose, one_line(messages[-1].get("content", ""), 120))
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": _ollama_options(temperature, num_predict=_estimate_num_predict(source_chars)),
    }
    t0 = time.monotonic()
    nchars = 0
    seen = ""
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
                if obj.get("done") and not (obj.get("message") or {}).get("content"):
                    break
                msg = obj.get("message") or {}
                piece = msg.get("content") or ""
                if not piece:
                    continue
                # Ollama 部分版本在 message.content 中返回「截至目前的全文」，需取增量
                if piece.startswith(seen):
                    delta = piece[len(seen) :]
                    seen = piece
                else:
                    delta = piece
                    seen += piece
                if not delta:
                    continue
                if _stream_hit_repetition(seen):
                    plog_info("translate", "%s 检测到复读，提前结束生成", purpose)
                    break
                nchars += len(delta)
                yield delta
    plog_info(
        "translate",
        "%s 流式完成 耗时=%.2fs out_chars=%s",
        purpose,
        time.monotonic() - t0,
        nchars,
    )


async def _ollama_chat(
    messages: list[dict[str, str]], *, temperature: float, purpose: str, source_chars: int = 0
) -> str:
    parts: list[str] = []
    async for piece in _ollama_chat_stream(
        messages, temperature=temperature, purpose=purpose, source_chars=source_chars
    ):
        parts.append(piece)
    content = "".join(parts).strip()
    plog_debug("translate", "%s 汇总 preview=%s", purpose, one_line(content, 80))
    return content


async def translate_answer_to_stream(answer: str, target_lang: TargetLang) -> AsyncIterator[str]:
    """流式输出译文 token。需已配置 TRANSLATION_OLLAMA_MODEL。"""
    if not translation_model_configured():
        plog_info("translate", "流式跳过：未配置 TRANSLATION_OLLAMA_MODEL")
        return
    t = answer.strip()
    if not t:
        return
    if target_lang not in ("zh", "en"):
        target_lang = "zh"
    plog_info("translate", "回答翻译流式 开始 target=%s in_chars=%s", target_lang, len(t))
    messages = _translate_messages(t, target_lang)
    async for piece in _ollama_chat_stream(
        messages,
        temperature=settings.translation_temperature,
        purpose=f"回答→{target_lang}",
        source_chars=len(t),
    ):
        yield piece


async def stream_translate_sse_events(answer: str, target_lang: TargetLang) -> AsyncIterator[dict]:
    """
    生成翻译相关 SSE 事件：bilingual_start → bilingual_token* → bilingual（完整正文）。
    """
    if target_lang not in ("zh", "en"):
        target_lang = "zh"
    yield {"type": "bilingual_start", "lang": target_lang}
    buf: list[str] = []
    try:
        async for piece in translate_answer_to_stream(answer, target_lang):
            buf.append(piece)
            yield {"type": "bilingual_token", "lang": target_lang, "t": piece}
    except Exception as e:
        plog_info("translate", "回答翻译流式 失败 target=%s: %s", target_lang, e)
        log.warning("answer translate stream to %s failed: %s", target_lang, e)
        return
    full = _sanitize_translation_output("".join(buf))
    if full:
        plog_info("translate", "回答翻译流式 成功 target=%s out_chars=%s", target_lang, len(full))
        yield {"type": "bilingual", "lang": target_lang, "text": full}
    else:
        plog_info("translate", "回答翻译流式 空输出 target=%s", target_lang)


async def expand_query_for_retrieval(user_question: str) -> tuple[str | None, str | None]:
    """Return (zh_query, en_query) for extra FTS passes. On failure returns (None, None)."""
    if not translation_for_retrieval_enabled():
        return None, None
    q = user_question.strip()
    if not q:
        return None, None
    plog_info("translate", "检索扩展 开始 question=%s", clip(q, 120))
    try:
        prompt = _QUERY_JSON_INNER + q
        raw = await _ollama_chat(
            [{"role": "user", "content": prompt}],
            temperature=min(settings.translation_temperature, 0.2),
            purpose="检索扩展",
            source_chars=len(prompt),
        )
        zh, en = _parse_query_json(raw)
        if not zh and not en:
            plog_info(
                "translate",
                "检索扩展 JSON 无有效字段，尝试回退 raw_preview=%s",
                clip(raw, 240),
            )
            zh, en = await _fallback_retrieval_queries(q)
        if not zh and not en:
            plog_info("translate", "检索扩展 回退仍无可用 query，跳过额外 FTS")
            return None, None
        if zh == q and en == q:
            plog_info("translate", "检索扩展 与原文相同，跳过额外 FTS")
            return None, None
        plog_info("translate", "检索扩展 完成 zh=%s en=%s", clip(str(zh or ""), 60), clip(str(en or ""), 60))
        return zh, en
    except Exception as e:
        plog_info("translate", "检索扩展 失败，尝试回退: %s", e)
        log.warning("bilingual query expansion failed: %s", e)
        try:
            return await _fallback_retrieval_queries(q)
        except Exception as e2:
            plog_info("translate", "检索扩展 回退失败: %s", e2)
            return None, None


async def translate_answer_to(answer: str, target_lang: TargetLang) -> str | None:
    """将回答译为 target_lang（zh | en）。需已配置 TRANSLATION_OLLAMA_MODEL。"""
    if not translation_model_configured():
        plog_info("translate", "跳过：未配置 TRANSLATION_OLLAMA_MODEL")
        return None
    t = answer.strip()
    if not t:
        return None
    target_lang = target_lang if target_lang in ("zh", "en") else "zh"  # type: ignore[assignment]
    plog_info("translate", "回答翻译 开始 target=%s in_chars=%s", target_lang, len(t))
    try:
        out = await _ollama_chat(
            _translate_messages(t, target_lang),
            temperature=settings.translation_temperature,
            purpose=f"回答→{target_lang}",
            source_chars=len(t),
        )
        result = _sanitize_translation_output(out) or None
        if result:
            plog_info("translate", "回答翻译 成功 target=%s out_chars=%s", target_lang, len(result))
        else:
            plog_info("translate", "回答翻译 空输出 target=%s", target_lang)
        return result
    except Exception as e:
        plog_info("translate", "回答翻译 失败 target=%s: %s", target_lang, e)
        log.warning("answer translate to %s failed: %s", target_lang, e)
        return None


async def translate_answer_to_zh(answer: str) -> str | None:
    return await translate_answer_to(answer, "zh")


async def translate_answer_to_en(answer: str) -> str | None:
    return await translate_answer_to(answer, "en")
