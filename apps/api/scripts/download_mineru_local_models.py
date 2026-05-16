#!/usr/bin/env python3
"""
将 MinerU 默认仓库快照到本机目录，供 MINERU_MODEL_SOURCE=local + mineru.json 使用。

依赖：由本仓库 `pip install -e '.[dev,hf]'`（见 `pyproject.toml` 的 `hf` 额外依赖）安装 `huggingface_hub` 与 `httpx[socks]`。

用法（在 apps/api 下，请使用本仓库 venv，勿用系统 python）：
  .venv/bin/python scripts/download_mineru_local_models.py --base ./data/mineru-models
  .venv/bin/python scripts/download_mineru_local_models.py --base ./data/mineru-models --vlm-only
  .venv/bin/python scripts/download_mineru_local_models.py --base ./data/mineru-models --no-proxy
  # 或从仓库根目录：npm run download:mineru-models
  # 追加参数：npm run download:mineru-models -- --no-proxy

下载完成后：把 config/mineru.json.example 复制为 mineru.json，把其中路径改为
  {base}/MinerU2.5-Pro-2604-1.2B 与 {base}/PDF-Extract-Kit-1.0，
再在 apps/api/.env 中设置 MINERU_MODEL_SOURCE=local 与 MINERU_TOOLS_CONFIG_JSON 指向该 json。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Iterator

# huggingface_hub 通过 httpx 读代理；SOCKS 需 socksio，否则见终端报错。
_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


@contextmanager
def _without_proxy_env() -> Iterator[None]:
    saved: dict[str, str] = {}
    for k in _PROXY_ENV_KEYS:
        if k in os.environ:
            saved[k] = os.environ.pop(k)
    try:
        yield
    finally:
        os.environ.update(saved)


def main() -> int:
    p = argparse.ArgumentParser(description="下载 MinerU VLM / Pipeline 模型到本地目录")
    p.add_argument(
        "--base",
        type=Path,
        default=Path("./data/mineru-models"),
        help="输出根目录（默认 ./data/mineru-models）",
    )
    p.add_argument(
        "--vlm-only",
        action="store_true",
        help="仅下载 VLM（hybrid 仍需要 pipeline，仅适合测试或你另有 pipeline 目录）",
    )
    p.add_argument(
        "--no-proxy",
        action="store_true",
        help="下载时临时清除 HTTP(S)/ALL_PROXY 环境变量，避免 SOCKS 代理触发 httpx 缺少 socksio 报错",
    )
    args = p.parse_args()

    dl_ctx = _without_proxy_env() if args.no_proxy else nullcontext()
    with dl_ctx:
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            print("请先安装: pip install huggingface_hub", file=sys.stderr)
            return 1

        base: Path = args.base.expanduser().resolve()
        base.mkdir(parents=True, exist_ok=True)

        vlm_id = "opendatalab/MinerU2.5-Pro-2604-1.2B"
        pipe_id = "opendatalab/PDF-Extract-Kit-1.0"

        vlm_dir = base / "MinerU2.5-Pro-2604-1.2B"
        print(f"下载 VLM: {vlm_id} -> {vlm_dir}")
        try:
            snapshot_download(repo_id=vlm_id, local_dir=str(vlm_dir))
        except ImportError as e:
            msg = str(e).lower()
            if "socks" in msg or "socksio" in msg:
                print(
                    "错误：环境变量中的 SOCKS 代理需要 socksio，当前未安装。\n"
                    "  解决 A: pip install \"httpx[socks]\"\n"
                    "  解决 B: 同一命令加 --no-proxy（临时直连下载，适合本机可直连 HF 时）",
                    file=sys.stderr,
                )
                return 1
            raise

        pipe_dir = None
        if not args.vlm_only:
            pipe_dir = base / "PDF-Extract-Kit-1.0"
            print(f"下载 Pipeline 资源: {pipe_id} -> {pipe_dir}（体积较大，请耐心等待）")
            snapshot_download(repo_id=pipe_id, local_dir=str(pipe_dir))

    snippet = {
        "config_version": "1.3.1",
        "models-dir": {
            "vlm": str(vlm_dir),
            **({"pipeline": str(pipe_dir)} if pipe_dir else {}),
        },
    }
    out_json = base / "mineru.generated.json"
    out_json.write_text(json.dumps(snippet, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入示例配置: {out_json}")
    print("请在 .env 中设置：")
    print("  MINERU_MODEL_SOURCE=local")
    print(f"  MINERU_TOOLS_CONFIG_JSON={out_json}")
    if args.vlm_only:
        print("注意：仅 VLM 时 hybrid 仍需要 pipeline 路径，请补全 models-dir.pipeline 或重新运行去掉 --vlm-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
