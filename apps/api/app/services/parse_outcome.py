from __future__ import annotations

"""根据解析结果 meta 与 Markdown 生成 parse_status / status_message。"""

from app.pipeline_logging import clip


def summarize_parse_outcome(md: str, meta: dict | None) -> tuple[str | None, str | None]:
    """
    返回 (parse_status, status_message)。
    parse_status 为 None 表示保持 parsed；为 failed 表示解析不可用。
    """
    meta = meta or {}
    text = (md or "").strip()
    mode = str(meta.get("mode") or "")

    if len(text) < 80 or "提取失败" in text[:500]:
        detail = _mineru_detail(meta)
        if str(meta.get("mode") or "") == "pdf_invalid":
            msg = str(meta.get("pdf_error") or detail or "PDF 无效或已损坏，无法解析。")
        else:
            msg = "PDF 解析未得到可用正文（可能为扫描件或 MinerU 失败）。"
            if detail:
                msg += f" 详情：{detail}"
        return "failed", msg[:2000]

    warnings: list[str] = []
    if mode.startswith("pypdf"):
        warnings.append("已降级为 pypdf 文本提取，版式/公式/表格可能丢失")
    elif mode == "pypdf":
        warnings.append("未使用 MinerU，仅 pypdf 提取")
    elif "fallback" in mode:
        warnings.append(f"MinerU 未完整成功（{mode}），已降级提取")

    err = (meta.get("mineru_error") or meta.get("mineru_log_tail") or "").strip()
    if err and "fallback" not in mode and not mode.startswith("pypdf"):
        warnings.append(f"MinerU 告警：{clip(err, 400)}")

    exit_code = meta.get("mineru_exit_code")
    if exit_code and int(exit_code) != 0:
        warnings.append(f"MinerU 退出码 {exit_code}")

    if meta.get("mineru_partial_after_timeout"):
        warnings.append("MinerU 超时，仅保留部分 Markdown")

    if warnings:
        return None, "解析提示：" + "；".join(dict.fromkeys(warnings))[:2000]
    return None, None


def _mineru_detail(meta: dict) -> str:
    for key in ("mineru_error", "mineru_log_tail"):
        v = meta.get(key)
        if v and str(v).strip():
            return clip(str(v).strip(), 500)
    mode = meta.get("mode")
    return str(mode) if mode else ""
