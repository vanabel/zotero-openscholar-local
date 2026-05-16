from __future__ import annotations

from typing import Literal

ReviewTemplate = Literal[
    "literature_review",
    "grant_proposal",
    "quick_review",
    "comparative_review",
]


def build_review_messages(
    topic: str,
    focus: str | None,
    contexts: list[dict],
    lang: str,
    *,
    template: ReviewTemplate = "literature_review",
) -> list[dict[str, str]]:
    blocks = []
    for i, c in enumerate(contexts, start=1):
        page = c.get("page_start")
        page_hint = f" 页码≈{page}" if page else ""
        blocks.append(
            f"[{i}] paper_id={c['paper_id']} chunk_id={c['chunk_id']}\n"
            f"标题: {c.get('title') or '未知'}\n"
            f"章节: {c.get('section_path') or ''}{page_hint}\n"
            f"片段:\n{c['text']}\n"
        )
    ctx = "\n\n".join(blocks)
    if template == "grant_proposal":
        if lang == "zh":
            sys = (
                "你是科研项目申请书写作助手。仅根据证据撰写「研究现状」部分，结构须包含："
                "（1）国内外研究现状；（2）存在的科学问题；（3）本项目的切入角度；（4）创新性。"
                "每个关键论断句末用 [n] 引用编号。不要编造证据之外的内容；证据不足处请明确说明。"
            )
            user = f"项目主题：{topic}\n补充说明：{focus or '无'}\n\n证据片段：\n{ctx}"
        else:
            sys = (
                "Draft the 'research background' section of a grant proposal from evidence only. "
                "Sections: state of the art; open problems; angle of this project; novelty. Cite [n]."
            )
            user = f"Project topic: {topic}\nNotes: {focus or ''}\n\nEvidence:\n{ctx}"
    elif template == "quick_review":
        if lang == "zh":
            sys = (
                "你是文献速览助手。仅根据证据写 300–600 字中文速览："
                "核心结论、主要方法、与主题的关系、主要局限。关键句末用 [n] 引用。不要编造。"
            )
            user = f"主题：{topic}\n补充：{focus or '无'}\n\n证据：\n{ctx}"
        else:
            sys = "Write a 300–600 word quick scan: conclusions, methods, relevance, limits. Cite [n] from evidence only."
            user = f"Topic: {topic}\nNotes: {focus or ''}\n\nEvidence:\n{ctx}"
    elif template == "comparative_review":
        if lang == "zh":
            sys = (
                "你是比较综述助手。仅根据证据撰写中文对比综述："
                "开头 1–2 段导语后，必须包含一个 Markdown 表格，列至少包括："
                "文献（用 [n] 标注）、方法、数据/设定、主要结论、局限。"
                "表后可用短段总结异同。关键论断用 [n]，不要编造表格中未出现的事实。"
            )
            user = f"对比主题：{topic}\n对比维度说明：{focus or '方法、结论、局限'}\n\n证据：\n{ctx}"
        else:
            sys = (
                "Write a comparative review with a Markdown table (paper [n], methods, data, findings, limits) "
                "plus a short synthesis. Cite [n]; no invented facts."
            )
            user = f"Topic: {topic}\nAxes: {focus or 'methods, findings, limits'}\n\nEvidence:\n{ctx}"
    elif lang == "zh":
        sys = (
            "你是资深综述作者。请基于证据撰写结构化中文文献综述，"
            "包含：背景与问题、主要方法与结果脉络、异同与争议、开放问题。"
            "每个关键论断末尾用 [n] 引用编号。不要编造证据之外的内容。"
        )
        user = f"综述主题：{topic}\n补充说明：{focus or '无'}\n\n证据片段：\n{ctx}"
    else:
        sys = "Write a structured mini literature review with citations [n] only from evidence."
        user = f"Topic: {topic}\nNotes: {focus or ''}\n\nEvidence:\n{ctx}"
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def review_to_markdown(
    body: str,
    topic: str,
    citations: list[dict],
    *,
    template: ReviewTemplate = "literature_review",
    lang: str = "zh",
) -> str:
    title = topic.strip()
    headings = {
        "grant_proposal": ("研究现状（申请书草稿）", "Research Background (Grant Draft)"),
        "quick_review": ("文献速览", "Quick Literature Scan"),
        "comparative_review": ("对比综述", "Comparative Review"),
        "literature_review": ("文献综述", "Literature Review"),
    }
    zh_h, en_h = headings.get(template, headings["literature_review"])
    heading = zh_h if lang == "zh" else en_h
    lines = [f"# {heading}", "", f"**主题**：{title}", "", body.strip(), ""]
    if citations:
        lines.append("## 参考文献线索" if lang == "zh" else "## Reference leads")
        lines.append("")
        for c in citations:
            ref = c.get("ref", "?")
            title_c = c.get("title") or c.get("paper_id") or ""
            sec = c.get("section_path") or ""
            page = c.get("page_start")
            extra = sec or (f"p.{page}" if page else "")
            lines.append(f"- [{ref}] {title_c}" + (f" — {extra}" if extra else ""))
    return "\n".join(lines).strip() + "\n"
