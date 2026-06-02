"""OpenScholar-8B 主对话：Transformers 本地加载（Llama 3.1 chat template）。"""

from __future__ import annotations

import asyncio
import threading
import time
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
_infer_lock = threading.Lock()
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
            load_kw: dict[str, Any] = {"dtype": dtype, "low_cpu_mem_usage": True}
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
            plog_info(
                "llm",
                "OpenScholar 权重已载入 device=%s（MPS/CUDA 即本机 GPU 加速）",
                _model_device(model),
            )
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


def _is_mps_device(device: Any) -> bool:
    return str(device).startswith("mps")


def _mps_sync(device: Any) -> None:
    if _DEPS_OK and torch is not None and _is_mps_device(device):
        torch.mps.synchronize()


def _build_inputs(
    tok: Any,
    messages: list[dict[str, str]],
    *,
    max_input_tokens: int | None = None,
) -> Any:
    """返回 shape (1, seq) 的 input_ids 张量（CPU）。"""
    chat_msgs = [{"role": str(m.get("role") or "user"), "content": str(m.get("content") or "")} for m in messages]
    if not hasattr(tok, "apply_chat_template"):
        raise RuntimeError("Tokenizer 不支持 apply_chat_template，请使用 Llama 3.1 系 OpenScholar 权重。")
    cap = int(max_input_tokens or getattr(tok, "model_max_length", 4096) or 4096)
    cap = min(cap, 4096)
    encoded = tok.apply_chat_template(
        chat_msgs,
        tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt",
        truncation=True,
        max_length=cap,
    )
    # 新版 transformers 可能返回 BatchEncoding 而非裸 Tensor
    if isinstance(encoded, dict):
        ids = encoded["input_ids"]
    elif hasattr(encoded, "input_ids"):
        ids = encoded.input_ids
    else:
        ids = encoded
    if not isinstance(ids, torch.Tensor):
        ids = torch.tensor(ids)
    if ids.dim() == 1:
        ids = ids.unsqueeze(0)
    return ids


def _generate_sync(
    messages: list[dict[str, str]],
    temperature: float,
    *,
    max_new_tokens: int | None = None,
    max_input_tokens: int | None = None,
) -> str:
    tok, model = _ensure_chat_model()
    device = _model_device(model)
    plog_info("llm", "OpenScholar 正在编码 prompt…")
    inputs = _build_inputs(tok, messages, max_input_tokens=max_input_tokens).to(device)
    input_len = int(inputs.shape[-1])
    plog_info("llm", "OpenScholar prompt 编码完成 input_tokens=%s", input_len)
    max_new = int(max_new_tokens or settings.openscholar_chat_max_new_tokens)
    temp = max(float(temperature), 0.01)
    t0 = time.perf_counter()
    with _infer_lock:
        queue_wait = time.perf_counter() - t0
        plog_info(
            "llm",
            "OpenScholar 推理开始 input_tokens=%s max_new_tokens=%s device=%s",
            input_len,
            max_new,
            device,
        )
        try:
            with torch.inference_mode():
                _mps_sync(device)
                gen_t0 = time.perf_counter()
                out = model.generate(
                    inputs,
                    max_new_tokens=max_new,
                    temperature=temp,
                    do_sample=True,
                    pad_token_id=tok.pad_token_id,
                    eos_token_id=tok.eos_token_id,
                )
                _mps_sync(device)
                gen_sec = time.perf_counter() - gen_t0
        except Exception as e:
            plog_info("llm", "OpenScholar 推理失败 device=%s: %s", device, e)
            raise
        new_tokens = out[0, input_len:]
        out_len = int(new_tokens.shape[-1])
        text = tok.decode(new_tokens, skip_special_tokens=True)
        tok_s = out_len / gen_sec if gen_sec > 0 else 0.0
        plog_info(
            "llm",
            "OpenScholar 推理完成 device=%s 输入token=%s 输出token=%s 生成=%.2fs 排队=%.2fs 均速=%.1f tok/s",
            device,
            input_len,
            out_len,
            gen_sec,
            queue_wait,
            tok_s,
        )
        plog_info("llm", "OpenScholar 输出预览: %s", clip(text, 400))
        return text


def _stream_sync(
    messages: list[dict[str, str]],
    temperature: float,
    *,
    max_new_tokens: int | None = None,
) -> Iterator[str]:
    tok, model = _ensure_chat_model()
    inputs = _build_inputs(tok, messages).to(_model_device(model))
    max_new = int(max_new_tokens or settings.openscholar_chat_max_new_tokens)
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
        with _infer_lock:
            with torch.inference_mode():
                model.generate(**gen_kw)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    for piece in streamer:
        if piece:
            yield str(piece)


async def chat_transformers(
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    *,
    max_new_tokens: int | None = None,
    max_input_tokens: int | None = None,
) -> str:
    return await asyncio.to_thread(
        _generate_sync,
        messages,
        temperature,
        max_new_tokens=max_new_tokens,
        max_input_tokens=max_input_tokens,
    )


async def chat_transformers_stream(
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    *,
    max_new_tokens: int | None = None,
) -> asyncio.AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    q: asyncio.Queue[str | BaseException | object] = asyncio.Queue()
    done = object()

    def worker() -> None:
        try:
            for piece in _stream_sync(messages, temperature, max_new_tokens=max_new_tokens):
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
