from __future__ import annotations

from typing import Literal

ReviewTemplate = Literal["literature_review", "grant_proposal"]


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
        blocks.append(
            f"[{i}] paper_id={c['paper_id']} chunk_id={c['chunk_id']}\n"
            f"标题: {c.get('title') or '未知'}\n"
            f"章节: {c.get('section_path') or ''}\n"
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
    if template == "grant_proposal":
        heading = "研究现状（申请书草稿）" if lang == "zh" else "Research Background (Grant Draft)"
    else:
        heading = "文献综述" if lang == "zh" else "Literature Review"
    lines = [f"# {heading}", "", f"**主题**：{title}", "", body.strip(), ""]
    if citations:
        lines.append("## 参考文献线索")
        lines.append("")
        for c in citations:
            ref = c.get("ref", "?")
            title_c = c.get("title") or c.get("paper_id") or ""
            sec = c.get("section_path") or ""
            lines.append(f"- [{ref}] {title_c}" + (f" — {sec}" if sec else ""))
    return "\n".join(lines).strip() + "\n"
