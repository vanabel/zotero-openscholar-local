"""OpenScholar Retriever (bi-encoder) + Reranker (cross-encoder) via Hugging Face."""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

from app.config import settings
from app.pipeline_logging import clip, plog_info

log = logging.getLogger(__name__)

_DEPS_OK = False
_IMPORT_ERROR: str | None = None

try:
    import torch
    import torch.nn.functional as F
    from transformers import AutoModel, AutoModelForSequenceClassification, AutoTokenizer

    _DEPS_OK = True
except ImportError as e:
    torch = None  # type: ignore[assignment]
    F = None  # type: ignore[assignment]
    AutoModel = None  # type: ignore[misc, assignment]
    AutoModelForSequenceClassification = None  # type: ignore[misc, assignment]
    AutoTokenizer = None  # type: ignore[misc, assignment]
    _IMPORT_ERROR = str(e)

_state_lock = threading.Lock()
_retriever_tok: Any = None
_retriever_model: Any = None
_reranker_tok: Any = None
_reranker_model: Any = None
_retriever_load_failed = False
_reranker_load_failed = False


def openscholar_deps_available() -> bool:
    return _DEPS_OK


def openscholar_retriever_enabled() -> bool:
    return bool(settings.openscholar_retriever_enabled and _DEPS_OK and not _retriever_load_failed)


def openscholar_reranker_enabled() -> bool:
    return bool(settings.openscholar_reranker_enabled and _DEPS_OK and not _reranker_load_failed)


def _resolve_device() -> str:
    raw = (settings.openscholar_device or "auto").strip().lower()
    if raw in ("cpu", "cuda", "mps"):
        return raw
    if not _DEPS_OK or torch is None:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _mean_pool(last_hidden: Any, attention_mask: Any) -> Any:
    mask = attention_mask.unsqueeze(-1).expand(last_hidden.size()).float()
    summed = torch.sum(last_hidden * mask, dim=1)
    counts = torch.clamp(mask.sum(dim=1), min=1e-9)
    return summed / counts


def _ensure_retriever() -> tuple[Any, Any]:
    global _retriever_tok, _retriever_model, _retriever_load_failed
    if _retriever_model is not None and _retriever_tok is not None:
        return _retriever_tok, _retriever_model
    with _state_lock:
        if _retriever_model is not None and _retriever_tok is not None:
            return _retriever_tok, _retriever_model
        if not _DEPS_OK:
            raise RuntimeError(f"OpenScholar 依赖未安装: {_IMPORT_ERROR}")
        device = _resolve_device()
        plog_info("retrieve", "加载 OpenScholar Retriever model=%s device=%s", settings.openscholar_retriever_model, device)
        tok = AutoTokenizer.from_pretrained(settings.openscholar_retriever_model)
        model = AutoModel.from_pretrained(settings.openscholar_retriever_model)
        model.eval()
        model.to(device)
        _retriever_tok = tok
        _retriever_model = model
        return tok, model


def _ensure_reranker() -> tuple[Any, Any]:
    """XLM-RoBERTa sequence classification (BGE-reranker 架构)；不用 CrossEncoder 以避免 processor 兼容问题。"""
    global _reranker_tok, _reranker_model, _reranker_load_failed
    if _reranker_model is not None and _reranker_tok is not None:
        return _reranker_tok, _reranker_model
    with _state_lock:
        if _reranker_model is not None and _reranker_tok is not None:
            return _reranker_tok, _reranker_model
        if not _DEPS_OK:
            raise RuntimeError(f"OpenScholar 依赖未安装: {_IMPORT_ERROR}")
        device = _resolve_device()
        path = settings.openscholar_reranker_model
        plog_info("retrieve", "加载 OpenScholar Reranker model=%s device=%s", path, device)
        tok = AutoTokenizer.from_pretrained(path)
        model = AutoModelForSequenceClassification.from_pretrained(path)
        model.eval()
        model.to(device)
        _reranker_tok = tok
        _reranker_model = model
        return tok, model


def mark_load_failed(reason: str, *, component: str = "all") -> None:
    """component: retriever | reranker | all"""
    global _retriever_load_failed, _reranker_load_failed
    if component in ("retriever", "all"):
        _retriever_load_failed = True
    if component in ("reranker", "all"):
        _reranker_load_failed = True
    log.warning("OpenScholar %s disabled: %s", component, reason)
    plog_info("retrieve", "OpenScholar %s 加载失败: %s", component, clip(reason, 200))


def encode_passages(texts: list[str]) -> list[list[float]]:
    """Bi-encoder passage embeddings (L2-normalized)."""
    if not texts:
        return []
    tok, model = _ensure_retriever()
    device = _resolve_device()
    max_len = settings.openscholar_retriever_max_length
    bs = settings.openscholar_encode_batch_size
    out: list[list[float]] = []
    with torch.no_grad():
        for i in range(0, len(texts), bs):
            batch = texts[i : i + bs]
            inputs = tok(
                batch,
                padding=True,
                truncation=True,
                max_length=max_len,
                return_tensors="pt",
            )
            inputs = {k: v.to(device) for k, v in inputs.items()}
            hidden = model(**inputs).last_hidden_state
            emb = _mean_pool(hidden, inputs["attention_mask"])
            emb = F.normalize(emb, p=2, dim=1)
            for row in emb.cpu().tolist():
                out.append([float(x) for x in row])
    return out


def encode_queries(texts: list[str]) -> list[list[float]]:
    return encode_passages(texts)


def rerank_scores(query: str, passages: list[str]) -> list[float]:
    if not passages:
        return []
    tok, model = _ensure_reranker()
    device = _resolve_device()
    max_chars = settings.openscholar_rerank_max_chars
    bs = settings.openscholar_rerank_batch_size
    scores: list[float] = []
    with torch.no_grad():
        for i in range(0, len(passages), bs):
            batch = passages[i : i + bs]
            pairs = [(query, (p[:max_chars] if len(p) > max_chars else p)) for p in batch]
            inputs = tok(
                [q for q, _ in pairs],
                [p for _, p in pairs],
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            inputs = {k: v.to(device) for k, v in inputs.items()}
            logits = model(**inputs).logits.view(-1)
            for s in logits.cpu().tolist():
                scores.append(float(s))
    return scores


def parse_stored_embedding(raw: str | None) -> list[float] | None:
    if not raw:
        return None
    try:
        vec = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(vec, list) or not vec:
        return None
    return [float(x) for x in vec]
