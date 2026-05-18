"""OpenScholar-8B 主对话：Transformers 本地加载（Llama 3.1 chat template）。"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from typing import Any

from app.config import settings
from app.pipeline_logging import clip, plog_info

_DEPS_OK = False
_IMPORT_ERROR: str | None = None

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer

    _DEPS_OK = True
except ImportError as e:
    torch = None  # type: ignore[assignment]
    AutoModelForCausalLM = None  # type: ignore[misc, assignment]
    AutoTokenizer = None  # type: ignore[misc, assignment]
    TextIteratorStreamer = None  # type: ignore[misc, assignment]
    _IMPORT_ERROR = str(e)

_state_lock = threading.Lock()
_chat_tok: Any = None
_chat_model: Any = None
_chat_load_failed = False


def openscholar_chat_deps_available() -> bool:
    return _DEPS_OK


def _resolve_device() -> str:
    raw = (settings.openscholar_chat_device or settings.openscholar_device or "auto").strip().lower()
    if raw in ("cpu", "cuda", "mps"):
        return raw
    if not _DEPS_OK or torch is None:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _require_deps() -> None:
    if not _DEPS_OK:
        raise RuntimeError(
            f"Transformers 对话需要 PyTorch 与 transformers：{_IMPORT_ERROR}。"
            "请在 apps/api 下执行：pip install -e '.[openscholar]'"
        )
    if _chat_load_failed:
        raise RuntimeError(
            f"OpenScholar 对话模型加载失败（{settings.effective_openscholar_chat_model()}），"
            "请检查 HF 缓存、磁盘空间或 OPENSCHOLAR_CHAT_DEVICE。"
        )


def _ensure_chat_model() -> tuple[Any, Any]:
    global _chat_tok, _chat_model, _chat_load_failed
    if _chat_model is not None and _chat_tok is not None:
        return _chat_tok, _chat_model
    with _state_lock:
        if _chat_model is not None and _chat_tok is not None:
            return _chat_tok, _chat_model
        _require_deps()
        model_id = settings.effective_openscholar_chat_model()
        device = _resolve_device()
        plog_info("llm", "加载 OpenScholar 对话模型 model=%s device=%s", model_id, device)
        try:
            tok = AutoTokenizer.from_pretrained(model_id)
            dtype = torch.float16 if device in ("cuda", "mps") else torch.float32
            load_kw: dict[str, Any] = {"torch_dtype": dtype, "low_cpu_mem_usage": True}
            if device == "cuda":
                load_kw["device_map"] = "auto"
            model = AutoModelForCausalLM.from_pretrained(model_id, **load_kw)
            if device == "mps" and not getattr(model, "hf_device_map", None):
                model = model.to("mps")
            elif device == "cpu" and not getattr(model, "hf_device_map", None):
                model = model.to("cpu")
            model.eval()
            if tok.pad_token_id is None and tok.eos_token_id is not None:
                tok.pad_token_id = tok.eos_token_id
            _chat_tok = tok
            _chat_model = model
        except Exception as e:
            _chat_load_failed = True
            raise RuntimeError(f"加载 OpenScholar 对话模型失败: {e}") from e
        return _chat_tok, _chat_model


def _model_device(model: Any) -> Any:
    if hasattr(model, "device"):
        return model.device
    try:
        return next(model.parameters()).device
    except StopIteration:
        return "cpu"


def _build_inputs(tok: Any, messages: list[dict[str, str]]) -> Any:
    chat_msgs = [{"role": str(m.get("role") or "user"), "content": str(m.get("content") or "")} for m in messages]
    if not hasattr(tok, "apply_chat_template"):
        raise RuntimeError("Tokenizer 不支持 apply_chat_template，请使用 Llama 3.1 系 OpenScholar 权重。")
    return tok.apply_chat_template(
        chat_msgs,
        tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt",
    )


def _generate_sync(messages: list[dict[str, str]], temperature: float) -> str:
    tok, model = _ensure_chat_model()
    inputs = _build_inputs(tok, messages).to(_model_device(model))
    max_new = int(settings.openscholar_chat_max_new_tokens)
    temp = max(float(temperature), 0.01)
    with torch.inference_mode():
        out = model.generate(
            inputs,
            max_new_tokens=max_new,
            temperature=temp,
            do_sample=True,
            pad_token_id=tok.pad_token_id,
            eos_token_id=tok.eos_token_id,
        )
    new_tokens = out[0, inputs.shape[-1] :]
    text = tok.decode(new_tokens, skip_special_tokens=True)
    plog_info("llm", "OpenScholar transformers 完成 输出字符=%s", len(text))
    plog_info("llm", "OpenScholar 输出预览: %s", clip(text, 400))
    return text


def _stream_sync(messages: list[dict[str, str]], temperature: float) -> Iterator[str]:
    tok, model = _ensure_chat_model()
    inputs = _build_inputs(tok, messages).to(_model_device(model))
    max_new = int(settings.openscholar_chat_max_new_tokens)
    temp = max(float(temperature), 0.01)
    streamer = TextIteratorStreamer(tok, skip_special_tokens=True, skip_prompt=True)
    gen_kw = dict(
        inputs=inputs,
        streamer=streamer,
        max_new_tokens=max_new,
        temperature=temp,
        do_sample=True,
        pad_token_id=tok.pad_token_id,
        eos_token_id=tok.eos_token_id,
    )

    def _run() -> None:
        with torch.inference_mode():
            model.generate(**gen_kw)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    for piece in streamer:
        if piece:
            yield str(piece)


async def chat_transformers(messages: list[dict[str, str]], temperature: float = 0.2) -> str:
    return await asyncio.to_thread(_generate_sync, messages, temperature)


async def chat_transformers_stream(
    messages: list[dict[str, str]], temperature: float = 0.2
) -> asyncio.AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    q: asyncio.Queue[str | BaseException | object] = asyncio.Queue()
    done = object()

    def worker() -> None:
        try:
            for piece in _stream_sync(messages, temperature):
                loop.call_soon_threadsafe(q.put_nowait, piece)
        except BaseException as e:
            loop.call_soon_threadsafe(q.put_nowait, e)
        finally:
            loop.call_soon_threadsafe(q.put_nowait, done)

    threading.Thread(target=worker, daemon=True).start()
    while True:
        item = await q.get()
        if item is done:
            break
        if isinstance(item, BaseException):
            raise item
        yield str(item)
