/** 与后端 task_kind 一致：index 任务按 payload 细分为 parse / reindex / index。 */

export type TaskPayload = {
  parse_only?: boolean;
  reindex_only?: boolean;
  force?: boolean;
};

export type TaskLike = {
  task_type?: string;
  kind?: string;
  payload?: TaskPayload | null;
};

export function resolveTaskKind(t: TaskLike | null | undefined): string {
  if (!t) return "index";
  if (t.kind) return t.kind;
  if (t.task_type === "summarize") return "summarize";
  const p = t.payload;
  if (p?.parse_only) return "parse";
  if (p?.reindex_only) return "reindex";
  return t.task_type === "index" ? "index" : t.task_type ?? "index";
}

export const TASK_KIND_LABEL: Record<string, string> = {
  parse: "仅解析",
  reindex: "仅重建索引",
  index: "建立索引",
  summarize: "摘要",
};

export function labelTaskKind(kind: string): string {
  return TASK_KIND_LABEL[kind] ?? kind;
}

export function isTaskActive(status: string | undefined): boolean {
  return status === "queued" || status === "running";
}
