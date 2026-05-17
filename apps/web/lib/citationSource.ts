export type CitationLike = {
  source?: string | null;
  section_path?: string | null;
  section_title?: string | null;
  page_start?: number | null;
  page_end?: number | null;
};

export function formatPageRange(pageStart?: number | null, pageEnd?: number | null): string {
  if (pageStart == null && pageEnd == null) return "";
  if (pageStart != null && pageEnd != null && pageEnd !== pageStart) {
    return `第 ${pageStart}–${pageEnd} 页`;
  }
  const p = pageStart ?? pageEnd;
  return p != null ? `第 ${p} 页` : "";
}

/** 引用卡片：章节 + 页码（优先 API 的 source 字段）。 */
export function formatCitationSource(c: CitationLike): string {
  if (c.source && String(c.source).trim()) return String(c.source).trim();
  const bits: string[] = [];
  const sec = (c.section_path || c.section_title || "").trim();
  if (sec) bits.push(sec);
  const page = formatPageRange(c.page_start, c.page_end);
  if (page) bits.push(page);
  return bits.join(" · ");
}
