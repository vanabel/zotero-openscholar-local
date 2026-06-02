#!/usr/bin/env python3
"""
从魔搭 ModelScope 下载 OpenScholar-8B 全量权重到 ~/models/openscholar-ms-8b，
供 CHAT_PROVIDER=transformers 与 OPENSCHOLAR_CHAT_MODEL 本地路径使用。

用法（apps/api 下）：
  .venv/bin/python scripts/download_openscholar_chat_model.py
  .venv/bin/python scripts/download_openscholar_chat_model.py --force   # 删除未下完的目录后重下
  npm run download:openscholar-chat

下载完成后在 apps/api/.env 设置：
  OPENSCHOLAR_CHAT_MODEL=/Users/<you>/models/openscholar-ms-8b
  CHAT_PROVIDER=transformers
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# 允许从 apps/api 根目录运行
_API_ROOT = Path(__file__).resolve().parents[1]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.config import is_usable_hf_model_dir  # noqa: E402

MODELSCOPE_MODEL_ID = "OpenScholar/Llama-3.1_OpenScholar-8B"
DEFAULT_LOCAL_DIR = Path.home() / "models" / "openscholar-ms-8b"


def _download(local_dir: Path) -> Path:
    try:
        from modelscope.hub.snapshot_download import snapshot_download
    except ImportError as e:
        raise SystemExit(
            "未安装 modelscope。请执行：cd apps/api && .venv/bin/pip install modelscope"
        ) from e

    local_dir.mkdir(parents=True, exist_ok=True)
    print(f"从魔搭下载 {MODELSCOPE_MODEL_ID} → {local_dir}")
    print("（约 16GB，请保持网络畅通；中断后可再次运行以续传）")
    out = snapshot_download(
        MODELSCOPE_MODEL_ID,
        local_dir=str(local_dir),
    )
    return Path(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="魔搭下载 OpenScholar-8B 对话权重")
    parser.add_argument(
        "--local-dir",
        type=Path,
        default=DEFAULT_LOCAL_DIR,
        help=f"目标目录（默认 {DEFAULT_LOCAL_DIR}）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="若目录存在但权重不完整，先删除再下载",
    )
    args = parser.parse_args()
    local_dir = args.local_dir.expanduser().resolve()

    if is_usable_hf_model_dir(local_dir):
        print(f"已存在完整权重：{local_dir}")
        print("无需下载。若需覆盖请加 --force")
        return

    if local_dir.exists() and args.force:
        print(f"删除未完成目录：{local_dir}")
        shutil.rmtree(local_dir)
    elif local_dir.exists() and not is_usable_hf_model_dir(local_dir):
        print(
            f"目录存在但权重不完整：{local_dir}\n"
            "请加 --force 删除后重下，或手动清理后重试。"
        )
        raise SystemExit(1)

    out = _download(local_dir)
    if not is_usable_hf_model_dir(out):
        raise SystemExit(
            f"下载结束但未检测到完整权重（需 model.safetensors 或 pytorch_model.bin）：{out}"
        )
    print(f"完成：{out}")
    print(f"\n请在 apps/api/.env 设置：\n  OPENSCHOLAR_CHAT_MODEL={out}")


if __name__ == "__main__":
    main()
