#!/usr/bin/env python3
"""快速检查 OpenScholar Transformers 是否在 MPS 上推理及大致吞吐。

用法（apps/api）：
  .venv/bin/python scripts/probe_openscholar_mps.py
  .venv/bin/python scripts/probe_openscholar_mps.py --max-new-tokens 128
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[1]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="探测 OpenScholar MPS 推理")
    parser.add_argument("--max-new-tokens", type=int, default=64)
    args = parser.parse_args()

    import torch

    print(f"torch {torch.__version__}")
    print(f"mps available: {torch.backends.mps.is_available()}")

    from app.config import settings
    from app.services.openscholar_chat import _ensure_chat_model, _generate_sync, _model_device

    model_id = settings.effective_openscholar_chat_model()
    print(f"model: {model_id}")

    tok, model = _ensure_chat_model()
    dev = _model_device(model)
    print(f"weights device: {dev}")

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "用一句话说明什么是 RAG。"},
    ]
    t0 = time.perf_counter()
    text = _generate_sync(messages, 0.2, max_new_tokens=args.max_new_tokens)
    sec = time.perf_counter() - t0
    print(f"elapsed: {sec:.2f}s")
    print(f"output ({len(text)} chars): {text[:200]!r}")
    print(
        "\n说明：自回归解码 batch=1 时 GPU 利用率通常只有 20–50%，"
        "活动监视器「GPU」曲线偏低属正常；请看日志中的 tok/s。"
    )


if __name__ == "__main__":
    main()
