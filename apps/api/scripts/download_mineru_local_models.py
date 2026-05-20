#!/usr/bin/env python3
"""
将 MinerU 模型放到 apps/api/data/mineru-models，供 MINERU_MODEL_SOURCE=local 使用。

默认从 ~/mineru.json（或 MINERU_TOOLS_CONFIG_JSON）的 models-dir **复制/链接**已有目录，
避免重复从 Hugging Face 下载。若本地尚无权重，再加 --download。

用法（apps/api 下）：
  .venv/bin/python scripts/download_mineru_local_models.py
  .venv/bin/python scripts/download_mineru_local_models.py --from-config ~/mineru.json
  .venv/bin/python scripts/download_mineru_local_models.py --download          # 强制 HF 下载
  .venv/bin/python scripts/download_mineru_local_models.py --link              # 符号链接而非复制
  npm run download:mineru-models
  npm run download:mineru-models -- --download
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Iterator

_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)

VLM_DIR_NAME = "MinerU2.5-Pro-2604-1.2B"
PIPE_DIR_NAME = "PDF-Extract-Kit-1.0"
VLM_REPO_ID = "opendatalab/MinerU2.5-Pro-2604-1.2B"
PIPE_REPO_ID = "opendatalab/PDF-Extract-Kit-1.0"


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


def _vlm_dir_ok(d: Path) -> bool:
    """VLM（HF/ModelScope 快照）：根目录含 config.json + 权重。"""
    if not d.is_dir():
        return False
    if not (d / "config.json").is_file():
        return False
    if (d / "model.safetensors").is_file() or (d / "pytorch_model.bin").is_file():
        return True
    return any(d.glob("model-*-of-*.safetensors"))


def _pipeline_dir_ok(d: Path) -> bool:
    """PDF-Extract-Kit：ModelScope 布局为 models/ 子目录；HF 快照也可能含 config.json。"""
    if not d.is_dir():
        return False
    if (d / "models").is_dir():
        return True
    return _vlm_dir_ok(d)


def _source_dir_ok(d: Path, *, kind: str) -> bool:
    if kind == "pipeline":
        return _pipeline_dir_ok(d)
    return _vlm_dir_ok(d)


def _default_config_path() -> Path:
    env = (os.environ.get("MINERU_TOOLS_CONFIG_JSON") or "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / "mineru.json"


def _read_models_dir(config_path: Path) -> dict[str, Path]:
    if not config_path.is_file():
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"无法读取 {config_path}: {e}", file=sys.stderr)
        return {}
    raw = data.get("models-dir")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Path] = {}
    for key in ("vlm", "pipeline"):
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = Path(val.strip()).expanduser()
    return out


def _install_from_source(
    src: Path,
    dst: Path,
    *,
    link: bool,
    label: str,
    kind: str,
) -> bool:
    if not _source_dir_ok(src, kind=kind):
        print(f"跳过 {label}：源目录无效: {src}", file=sys.stderr)
        return False
    if _source_dir_ok(dst, kind=kind):
        print(f"已存在 {label}，跳过: {dst}")
        return True
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    if link:
        dst.symlink_to(src.resolve(), target_is_directory=True)
        print(f"已链接 {label}: {dst} -> {src.resolve()}")
    else:
        print(f"复制 {label}: {src} -> {dst}（体积大时请耐心等待）")
        shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=False)
        print(f"完成 {label}: {dst}")
    return True


def _download_hf(*, base: Path, vlm_only: bool, no_proxy: bool) -> tuple[Path, Path | None]:
    dl_ctx = _without_proxy_env() if no_proxy else nullcontext()
    with dl_ctx:
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            print("请先安装: pip install huggingface_hub", file=sys.stderr)
            raise SystemExit(1) from None

        vlm_dir = base / VLM_DIR_NAME
        print(f"从 Hugging Face 下载 VLM: {VLM_REPO_ID} -> {vlm_dir}")
        try:
            snapshot_download(repo_id=VLM_REPO_ID, local_dir=str(vlm_dir))
        except ImportError as e:
            msg = str(e).lower()
            if "socks" in msg or "socksio" in msg:
                print(
                    "错误：SOCKS 代理需要 socksio，或加 --no-proxy。\n"
                    "  pip install \"httpx[socks]\" 或 --no-proxy",
                    file=sys.stderr,
                )
                raise SystemExit(1) from e
            raise

        pipe_dir: Path | None = None
        if not vlm_only:
            pipe_dir = base / PIPE_DIR_NAME
            print(f"从 Hugging Face 下载 Pipeline: {PIPE_REPO_ID} -> {pipe_dir}")
            snapshot_download(repo_id=PIPE_REPO_ID, local_dir=str(pipe_dir))
        return vlm_dir, pipe_dir


def _write_generated_json(base: Path, vlm_dir: Path, pipe_dir: Path | None) -> Path:
    snippet = {
        "config_version": "1.3.1",
        "models-dir": {
            "vlm": str(vlm_dir.resolve()),
            **({"pipeline": str(pipe_dir.resolve())} if pipe_dir else {}),
        },
    }
    out_json = base / "mineru.generated.json"
    out_json.write_text(json.dumps(snippet, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_json


def _argv_for_parse() -> list[str]:
    """pnpm/npm 经 `run script -- --flags` 时可能把字面量 `--` 传给脚本，此处剥掉。"""
    return [a for a in sys.argv[1:] if a != "--"]


def main() -> int:
    p = argparse.ArgumentParser(
        description="准备 MinerU 本地权重（默认从 mineru.json 复制；--download 才走 Hugging Face）",
    )
    p.add_argument("--base", type=Path, default=Path("./data/mineru-models"), help="输出根目录")
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="PATH",
        help="mineru.json 路径（默认 ~/mineru.json 或 MINERU_TOOLS_CONFIG_JSON）",
    )
    p.add_argument(
        "--download",
        action="store_true",
        help="不从本地配置复制，改为从 Hugging Face 下载",
    )
    p.add_argument("--link", action="store_true", help="复制改为符号链接到源目录")
    p.add_argument("--vlm-only", action="store_true", help="仅处理 VLM")
    p.add_argument("--no-proxy", action="store_true", help="HF 下载时临时清除代理环境变量")
    p.add_argument("--force", action="store_true", help="目标已存在时仍覆盖（复制/链接前删除）")
    args = p.parse_args(_argv_for_parse())

    base = args.base.expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)

    vlm_dst = base / VLM_DIR_NAME
    pipe_dst = base / PIPE_DIR_NAME

    if args.force:
        for d in (vlm_dst, pipe_dst):
            if d.is_symlink() or d.is_file():
                d.unlink(missing_ok=True)
            elif d.is_dir():
                shutil.rmtree(d, ignore_errors=True)

    if not args.download:
        cfg_path = (args.config or _default_config_path()).expanduser()
        sources = _read_models_dir(cfg_path)
        if sources:
            print(f"从配置读取 models-dir: {cfg_path}")
            vlm_ok = False
            pipe_ok = False
            if "vlm" in sources:
                vlm_ok = _install_from_source(
                    sources["vlm"], vlm_dst, link=args.link, label="VLM", kind="vlm"
                )
            if not args.vlm_only and "pipeline" in sources:
                pipe_ok = _install_from_source(
                    sources["pipeline"],
                    pipe_dst,
                    link=args.link,
                    label="Pipeline",
                    kind="pipeline",
                )
            elif args.vlm_only:
                pipe_ok = True

            if vlm_ok and (args.vlm_only or pipe_ok):
                out_json = _write_generated_json(
                    base, vlm_dst, pipe_dst if not args.vlm_only else None
                )
                print(f"已写入: {out_json}")
                print("apps/api/.env 建议：")
                print("  MINERU_MODEL_SOURCE=local")
                print(f"  MINERU_TOOLS_CONFIG_JSON={out_json}")
                print("（或继续用 ~/mineru.json，只要 models-dir 指向有效目录）")
                return 0

            print("配置中的源目录不可用，将尝试 --download …", file=sys.stderr)
        else:
            print(f"未找到可用配置 {cfg_path}，将尝试 --download …", file=sys.stderr)

    vlm_dir, pipe_dir = _download_hf(base=base, vlm_only=args.vlm_only, no_proxy=args.no_proxy)
    out_json = _write_generated_json(base, vlm_dir, pipe_dir)
    print(f"已写入: {out_json}")
    print("请在 .env 中设置 MINERU_MODEL_SOURCE=local 与 MINERU_TOOLS_CONFIG_JSON")
    if args.vlm_only:
        print("注意：仅 VLM 时 hybrid 仍需要 pipeline，请补全或去掉 --vlm-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
