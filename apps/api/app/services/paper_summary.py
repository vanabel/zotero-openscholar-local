"""为已索引文献生成 paper_summary（供综述检索优先层）。"""

from __future__ import annotations

from app.config import settings
from app.pipeline_logging import plog_info
from app.services.llm import LLMClient, chat_model_id
from app.services.pdf_parse import load_parsed_markdown
from app.services.summaries import upsert_paper_summary
from app.services.zotero_scanner import get_paper

# 过长 prefill 会在 MPS 上极慢且易空输出；约 8k 字符 ≈ 2k token 量级
_SUMMARY_INPUT_MAX = 8_000


async def generate_paper_summary(paper_id: str, *, lang: str = "zh") -> dict:
    paper = get_paper(paper_id)
    if not paper or paper.get("deleted"):
        return {"ok": False, "error": "文献不存在或已归档"}
    if (paper.get("index_status") or "") != "indexed":
        return {"ok": False, "error": "文献尚未完成索引，无法生成摘要"}

    loaded = load_parsed_markdown(settings.parsed_dir / paper_id)
    if loaded is None:
        return {"ok": False, "error": "无 document.md"}
    md, _path = loaded
    excerpt = md[:_SUMMARY_INPUT_MAX]
    title = (paper.get("title") or paper_id).strip()
    if lang == "zh":
        sys = (
            "你是学术文献摘要助手。仅根据给定 Markdown 片段撰写结构化中文摘要（200–400 字），"
            "包含：研究问题、方法、主要结果、局限。不要编造片段中不存在的内容。"
        )
        user = f"标题：{title}\n\n正文片段：\n{excerpt}"
    else:
        sys = "Write a structured abstract (200–400 words) from the excerpt only: problem, methods, results, limits."
        user = f"Title: {title}\n\nExcerpt:\n{excerpt}"

    client = LLMClient()
    try:
        text = await client.chat(
            [{"role": "system", "content": sys}, {"role": "user", "content": user}],
            temperature=0.2,
            max_new_tokens=int(settings.openscholar_summary_max_new_tokens),
            max_input_tokens=2048,
        )
    except Exception as e:
        err = str(e).strip() or f"{type(e).__name__}"
        return {"ok": False, "error": err}

    content = (text or "").strip()
    if len(content) < 40:
        plog_info(
            "summary",
            "摘要过短 paper_id=%s 输出字符=%s（检查 MPS 内存或改用 Ollama）",
            paper_id,
            len(content),
        )
        return {"ok": False, "error": "摘要过短或模型无输出"}

    sid = upsert_paper_summary(paper_id, "paper_summary", content, model=chat_model_id())
    plog_info("summary", "已写入 paper_summary paper_id=%s chars=%s", paper_id, len(content))
    return {"ok": True, "summary_id": sid, "chars": len(content)}
