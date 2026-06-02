/** 与后端 index / summarize 流水线阶段一致 */

export const PHASE_LABEL: Record<string, string> = {
  queued: "排队",
  parse: "PDF 解析",
  chunk: "分块",
  embed: "BGE 嵌入",
  scholar_embed: "OpenScholar Retriever",
  save: "写入索引",
  summarize: "生成摘要",
  done: "完成",
};

export function labelPhase(phase: string): string {
  return PHASE_LABEL[phase] ?? phase;
}

export function pipelinePhasesForKind(kind: string): string[] {
  switch (kind) {
    case "parse":
    case "mineru_download":
      return ["parse"];
    case "reindex":
      return ["chunk", "embed", "scholar_embed", "save"];
    case "summarize":
      return ["summarize"];
    default:
      return ["parse", "chunk", "embed", "scholar_embed", "save"];
  }
}
