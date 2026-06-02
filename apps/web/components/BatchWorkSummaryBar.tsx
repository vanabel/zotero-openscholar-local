"use client";

export type BatchWorkSummary = {
  index_missing: number;
  index_missing_including_indexing: number;
  parse_missing: number;
  summarize_missing: number;
  unscored_with_markdown: number;
  /** SQLite 含向量但 Lance 尚无该文献时的「待同步」篇数；同步成功后会减少 */
  lance_scholar_papers: number;
  /** SQLite 中至少有一条 scholar 向量的文献数（候选池，同步到 Lance 后不变） */
  lance_scholar_sqlite_with_vectors: number;
  /** Lance `scholar_chunks` 中已出现过的文献数（按 paper_id 去重） */
  lance_scholar_in_lance: number;
  lancedb_enabled: boolean;
};

export const WORK_QUEUE_KEYS = [
  "index_missing",
  "parse_missing",
  "summarize_missing",
  "unscored_rescore",
  "lance_scholar",
] as const;

export type WorkQueueFilter = (typeof WORK_QUEUE_KEYS)[number];

const FILTER_LABELS: Record<WorkQueueFilter, string> = {
  index_missing: "索引未建立",
  parse_missing: "解析缺失",
  summarize_missing: "摘要缺失",
  unscored_rescore: "未评分补分",
  lance_scholar: "待同步 Lance",
};

function countForKey(summary: BatchWorkSummary, key: WorkQueueFilter): number {
  switch (key) {
    case "index_missing":
      return summary.index_missing;
    case "parse_missing":
      return summary.parse_missing;
    case "summarize_missing":
      return summary.summarize_missing;
    case "unscored_rescore":
      return summary.unscored_with_markdown;
    case "lance_scholar":
      return summary.lance_scholar_papers;
    default:
      return 0;
  }
}

type Tone = "mist" | "amber" | "sky" | "violet" | "indigo";

const KEY_TONE: Record<WorkQueueFilter, Tone> = {
  index_missing: "amber",
  parse_missing: "mist",
  summarize_missing: "indigo",
  unscored_rescore: "mist",
  lance_scholar: "violet",
};

const tones: Record<Tone, string> = {
  mist: "border-mist-200 bg-mist-50 text-ink-800",
  amber: "border-amber-200 bg-amber-50 text-amber-950",
  sky: "border-sky-200 bg-sky-50 text-sky-950",
  violet: "border-violet-200 bg-violet-50 text-violet-950",
  indigo: "border-indigo-200 bg-indigo-50 text-indigo-950",
};

type Props = {
  summary: BatchWorkSummary;
  activeWorkQueue: WorkQueueFilter | null;
  onWorkQueueChange: (next: WorkQueueFilter | null) => void;
};

export function workQueueLabel(key: WorkQueueFilter): string {
  return FILTER_LABELS[key];
}

export function BatchWorkSummaryBar({ summary, activeWorkQueue, onWorkQueueChange }: Props) {
  const idxExtra = summary.index_missing_including_indexing - summary.index_missing;
  return (
    <section className="rounded-xl border border-mist-200 bg-white px-4 py-3 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-500">批量操作 · 当前待处理数量</h2>
        {!summary.lancedb_enabled && (
          <span className="text-[11px] text-amber-900">LanceDB 未启用：同步 Lance 将不可用</span>
        )}
      </div>
      <p className="mt-1 text-[11px] text-ink-600 leading-relaxed">
        点击下方标签<strong>按待办类型筛选</strong>下方文献列表（与对应批量按钮范围一致）；再点同一标签取消筛选。数字为<strong>全库</strong>统计；若同时输入搜索词，列表条数会进一步变少。
      </p>
      <p className="mt-0.5 text-[11px] text-ink-500">
        解析缺失 / 未评分补分会扫描本地 <code className="rounded bg-mist-100 px-0.5">parsed/</code>，文献极多时统计会略慢（与列表加载分开）。
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {WORK_QUEUE_KEYS.map((key) => {
          const active = activeWorkQueue === key;
          const disabled = key === "lance_scholar" && !summary.lancedb_enabled;
          const tone = KEY_TONE[key];
          const n = countForKey(summary, key);
          const lanceSub =
            key === "lance_scholar"
              ? summary.lancedb_enabled
                ? `已在 Lance ${summary.lance_scholar_in_lance ?? 0} · SQLite 含向量 ${summary.lance_scholar_sqlite_with_vectors ?? 0}`
                : `SQLite 含向量 ${summary.lance_scholar_sqlite_with_vectors ?? summary.lance_scholar_papers}（未启用 LanceDB）`
              : null;
          return (
            <button
              key={key}
              type="button"
              disabled={disabled}
              aria-pressed={active}
              title={
                disabled
                  ? "LanceDB 未启用"
                  : active
                    ? "点击取消筛选"
                    : key === "lance_scholar" && summary.lancedb_enabled
                      ? `${FILTER_LABELS[key]}：${n}；${lanceSub}`
                      : `仅看：${FILTER_LABELS[key]}`
              }
              onClick={() => {
                if (disabled) return;
                onWorkQueueChange(active ? null : key);
              }}
              className={`inline-flex flex-col items-start gap-0.5 rounded-lg border px-2.5 py-1.5 text-left text-xs transition-colors ${tones[tone]} ${
                active ? "ring-2 ring-sky-400 ring-offset-1" : "hover:brightness-[0.98]"
              } ${disabled ? "cursor-not-allowed opacity-45" : "cursor-pointer"}`}
            >
              <span className="inline-flex w-full items-baseline justify-between gap-2">
                <span className="font-medium">{FILTER_LABELS[key]}</span>
                <strong className="tabular-nums text-sm">{n}</strong>
              </span>
              {lanceSub ? <span className="max-w-[14rem] text-[10px] font-normal leading-snug text-ink-600">{lanceSub}</span> : null}
            </button>
          );
        })}
      </div>
      {activeWorkQueue && (
        <p className="mt-2 text-xs text-sky-950">
          当前列表筛选：<strong>{FILTER_LABELS[activeWorkQueue]}</strong>
          <button
            type="button"
            className="ml-2 text-sky-800 underline underline-offset-2 hover:text-sky-950"
            onClick={() => onWorkQueueChange(null)}
          >
            清除
          </button>
        </p>
      )}
      {idxExtra > 0 && (
        <p className="mt-2 text-[11px] text-ink-600">
          另有 <strong className="tabular-nums">{idxExtra}</strong> 篇状态为「建立索引中」
          <code className="mx-0.5 rounded bg-mist-100 px-1">indexing</code>
          （默认「索引未建立」按钮不含此项；可在 API 使用{" "}
          <code className="rounded bg-mist-100 px-1">include_indexing</code>）。
        </p>
      )}
      <details className="mt-3 group">
        <summary className="cursor-pointer list-none text-xs font-medium text-sky-900 hover:underline [&::-webkit-details-marker]:hidden">
          推荐顺序与依赖关系
          <span className="ml-1 text-ink-500 group-open:hidden">（展开）</span>
          <span className="ml-1 text-ink-500 hidden group-open:inline">（收起）</span>
        </summary>
        <ol className="mt-2 space-y-2 pl-4 text-xs text-ink-700 leading-relaxed [list-style-type:decimal]">
          <li>
            <strong>解析缺失</strong>：先得到可用的{" "}
            <code className="rounded bg-mist-100 px-1">document.md</code>（MinerU / pypdf）。
          </li>
          <li>
            <strong>索引未建立</strong>：依赖上一步的正文；会分块、嵌入，并在开启 OpenScholar 时写入 scholar 向量到 SQLite。
          </li>
          <li>
            <strong>同步 Lance</strong>：依赖 SQLite 中已有 scholar 向量（通常在上一步索引完成后）。只把已有向量写入 LanceDB，<strong>不重新嵌入</strong>；不会删除 SQLite
            中的向量，故「SQLite 含向量」总数不变，「待同步」会在写入 Lance 后下降。
          </li>
          <li>
            <strong>未评分补分</strong>：只要有 <code className="rounded bg-mist-100 px-1">document.md</code> 即可，<strong>不要求</strong>{" "}
            已 indexed；与索引无硬先后，但常在解析完成之后做。
          </li>
          <li>
            <strong>摘要缺失</strong>：<strong>必须先</strong> <code className="rounded bg-mist-100 px-1">indexed</code>
            ，与 Lance 同步无强制先后。
          </li>
        </ol>
      </details>
    </section>
  );
}
