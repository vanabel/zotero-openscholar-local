from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from pypdf import PdfReader

from app.config import settings
from app.pipeline_logging import clip, plog_info

_MINERU_CLI_WRAPPER = Path(__file__).resolve().parents[2] / "scripts" / "mineru_cli_wrapper.py"


def _mineru_executable() -> str | None:
    """支持 MINERU_CLI 为绝对路径；否则在 PATH 中查找。"""
    cli = (settings.mineru_cli or "").strip()
    if not cli:
        return None
    p = Path(cli).expanduser()
    if p.is_file():
        return str(p.resolve())
    return shutil.which(cli)


def _mineru_subprocess_env() -> dict[str, str]:
    """合并 MinerU 官方识别的环境变量（见 mineru.utils.models_download_utils / config_reader）。"""
    env = os.environ.copy()
    src = (settings.mineru_model_source or "").strip()
    if src:
        env["MINERU_MODEL_SOURCE"] = src
    cfg = (settings.mineru_tools_config_json or "").strip()
    if cfg:
        p = Path(cfg).expanduser()
        if p.is_file():
            env["MINERU_TOOLS_CONFIG_JSON"] = str(p.resolve())
        else:
            plog_info("parse", "MINERU_TOOLS_CONFIG_JSON 不是可读文件，已忽略: %s", cfg)
    poll = settings.mineru_task_poll_interval_sec
    env["MINERU_TASK_STATUS_POLL_INTERVAL_SECONDS"] = str(poll)
    return env


def _mineru_command(mineru_bin: str, tail: list[str]) -> list[str]:
    """用同 venv 的 python 跑 wrapper，覆盖 MinerU 默认 1s 任务轮询。"""
    mineru_path = Path(mineru_bin).resolve()
    py = mineru_path.parent / "python"
    if _MINERU_CLI_WRAPPER.is_file() and py.is_file():
        return [str(py), str(_MINERU_CLI_WRAPPER.resolve()), *tail]
    return [mineru_bin, *tail]


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    if not path.is_file():
        raise ValueError(f"不是可读常规文件，已跳过: {path}")
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clear_parsed_output_dir(out_dir: Path) -> int:
    """
    删除解析目录下已有产物，便于 MinerU 在无缓存干扰下重新生成。
    仅删除 out_dir 内子项，不删除 out_dir 本身。
    """
    if not out_dir.is_dir():
        return 0
    n = 0
    for child in list(out_dir.iterdir()):
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
            n += 1
        except OSError:
            pass
    return n


def _pypdf_to_markdown(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    parts: list[str] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        t = t.strip()
        if t:
            parts.append(f"## Page {i}\n\n{t}")
    if not parts:
        return f"# 提取失败\n\n无法从 PDF 读取文本（可能为扫描件）。请安装 MinerU 并配置 CLI。\n\n文件: `{pdf_path}`"
    return "\n\n".join(parts)


def parse_one(
    paper_id: str,
    pdf_path: Path,
    out_dir: Path,
    *,
    force_reparse: bool = False,
    pdf_sha256: str | None = None,
) -> tuple[str, dict]:
    """
    返回 (markdown, meta)。
    优先 MinerU CLI；否则 pypdf 降级。
    force_reparse：为 True 时应在调用前已清空 out_dir（由 index 在「强制重建」时负责）。
    """
    plog_info(
        "parse",
        "parse_one 开始 paper_id=%s path=%s force_reparse=%s pdf_sha256=%s",
        paper_id,
        pdf_path,
        force_reparse,
        (pdf_sha256[:12] + "…") if pdf_sha256 and len(pdf_sha256) > 12 else pdf_sha256,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    meta: dict = {"mode": "unknown", "mineru": False, "force_reparse": force_reparse}

    mineru_mode = (settings.mineru_mode or "cli").strip().lower()
    if mineru_mode == "cloud":
        from app.services.mineru_cloud import MinerUCloudError, parse_pdf_via_cloud_with_splitting

        plog_info("parse", "使用 MinerU 云端 API base=%s", settings.mineru_api_base_url)
        try:
            md, cloud_meta = parse_pdf_via_cloud_with_splitting(
                pdf_path,
                paper_id,
                out_dir,
                force_reparse=force_reparse,
                pdf_sha256=pdf_sha256,
            )
            meta.update(cloud_meta)
            plog_info("parse", "parse_one 完成 mode=mineru_cloud md_chars=%s", len(md))
            return md, meta
        except MinerUCloudError as e:
            meta["mineru_error"] = str(e)
            plog_info("parse", "MinerU 云端失败: %s，pypdf 降级", e)
            md = _pypdf_to_markdown(pdf_path)
            (out_dir / "document.md").write_text(md, encoding="utf-8")
            meta["mode"] = "pypdf_fallback_after_mineru_cloud_error"
            return md, meta

    mineru_bin = _mineru_executable()
    if mineru_bin:
        plog_info("parse", "使用 MinerU: %s", mineru_bin)
        meta["mode"] = "mineru"
        meta["mineru"] = True
        out_abs = str(out_dir.resolve())
        pdf_abs = str(pdf_path.resolve())
        style = (settings.mineru_cli_style or "v3").strip().lower()
        if style == "legacy":
            tail = [pdf_abs, "-o", out_abs]
        else:
            tail = ["-p", pdf_abs, "-o", out_abs]
        api_url = (settings.mineru_api_url or "").strip()
        if api_url:
            tail.extend(["--api-url", api_url])
            meta["mineru_api_url"] = api_url
        cmd = _mineru_command(mineru_bin, tail)
        meta["mineru_task_poll_interval_sec"] = settings.mineru_task_poll_interval_sec
        plog_info(
            "parse",
            "MinerU 命令 style=%s poll_interval=%ss cmd=%s",
            style,
            settings.mineru_task_poll_interval_sec,
            clip(" ".join(cmd), 500),
        )
        try:
            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=settings.parse_timeout_sec,
                env=_mineru_subprocess_env(),
            )
        except subprocess.TimeoutExpired as e:
            meta["mineru_error"] = f"timeout: {e}"
            plog_info("parse", "MinerU 超时: %s", e)
            md_path = _find_markdown(out_dir)
            if md_path and md_path.exists():
                md = md_path.read_text(encoding="utf-8", errors="replace")
                if len(md.strip()) >= 100:
                    meta["mode"] = "mineru_partial_after_timeout"
                    (out_dir / "document.md").write_text(md, encoding="utf-8")
                    plog_info("parse", "MinerU 超时但保留已生成 md chars=%s", len(md))
                    return md, meta
            md = _pypdf_to_markdown(pdf_path)
            (out_dir / "document.md").write_text(md, encoding="utf-8")
            meta["mode"] = "pypdf_fallback_after_mineru_error"
            return md, meta
        except FileNotFoundError as e:
            meta["mineru_error"] = str(e)
            plog_info("parse", "MinerU 可执行异常: %s", e)
            md = _pypdf_to_markdown(pdf_path)
            (out_dir / "document.md").write_text(md, encoding="utf-8")
            meta["mode"] = "pypdf_fallback_after_mineru_error"
            return md, meta

        log_blob = ((result.stderr or "").strip() + "\n--- stdout ---\n" + (result.stdout or "").strip()).strip()
        if result.returncode != 0:
            plog_info("parse", "MinerU 退出码=%s 日志节选=%s", result.returncode, clip(log_blob, 8000))
        else:
            plog_info("parse", "MinerU 退出码=0")

        md_path = _find_markdown(out_dir)
        if md_path and md_path.exists():
            md = md_path.read_text(encoding="utf-8", errors="replace")
            if len(md.strip()) >= 100:
                if result.returncode != 0:
                    meta["mineru_exit_code"] = result.returncode
                    meta["mineru_log_tail"] = clip(log_blob, 6000)
                    plog_info(
                        "parse",
                        "MinerU 非零退出但输出目录已有 Markdown，采用 MinerU 结果 exit=%s chars=%s",
                        result.returncode,
                        len(md),
                    )
                (out_dir / "document.md").write_text(md, encoding="utf-8")
                plog_info("parse", "parse_one 完成 mode=mineru md_chars=%s", len(md))
                return md, meta

        meta["mineru_error"] = (f"exit {result.returncode} " + clip(log_blob, 2000)).strip()
        plog_info("parse", "MinerU 未生成可用 md，pypdf 降级。detail=%s", clip(log_blob, 2000))
        md = _pypdf_to_markdown(pdf_path)
        (out_dir / "document.md").write_text(md, encoding="utf-8")
        meta["mode"] = "pypdf_fallback_after_mineru_error"
        plog_info("parse", "parse_one 完成 mode=pypdf_fallback md_chars=%s", len(md))
        return md, meta

    meta["mode"] = "pypdf"
    plog_info("parse", "MinerU 不可用或未产出 md，使用 pypdf")
    md = _pypdf_to_markdown(pdf_path)
    (out_dir / "document.md").write_text(md, encoding="utf-8")
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    plog_info("parse", "parse_one 完成 mode=pypdf md_chars=%s", len(md))
    return md, meta


def _find_markdown(out_dir: Path) -> Path | None:
    candidates = [p for p in out_dir.rglob("*.md") if p.is_file()]
    if not candidates:
        return None
    for name in ("document.md", "full.md", "auto.md", "middle.md"):
        for p in candidates:
            if p.name.lower() == name:
                return p
    return sorted(candidates, key=lambda p: len(str(p)))[0]


def load_parsed_markdown(out_dir: Path, *, min_chars: int = 100) -> tuple[str, Path] | None:
    """
    读取 data/parsed/{id}/ 下已有 Markdown；若无 document.md 则查找 MinerU 产出的 full.md 等并归一化到 document.md。
    """
    if not out_dir.is_dir():
        return None
    canonical = out_dir / "document.md"
    if canonical.is_file():
        text = canonical.read_text(encoding="utf-8", errors="replace")
        if len(text.strip()) >= min_chars:
            return text, canonical
    found = _find_markdown(out_dir)
    if not found or not found.is_file():
        return None
    text = found.read_text(encoding="utf-8", errors="replace")
    if len(text.strip()) < min_chars:
        return None
    if found.resolve() != canonical.resolve():
        canonical.write_text(text, encoding="utf-8")
        plog_info("parse", "复用已有 Markdown 并归一化: %s -> document.md", found.relative_to(out_dir))
    return text, canonical


def parsed_pdf_sha256(out_dir: Path) -> str | None:
    """meta.json 中记录的 PDF sha256（解析成功时写入）。"""
    meta_path = out_dir / "meta.json"
    if not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    v = meta.get("pdf_sha256")
    return str(v) if v else None
