"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import { labelTaskKind } from "@/lib/taskKind";

export type TaskStatsResponse = {
  total: number;
  pending: number;
  worker_concurrency: number;
  by_status: { status: string; count: number }[];
  by_type: { task_type: string; count: number }[];
  by_type_status: { task_type: string; status: string; count: number }[];
  by_kind?: { kind: string; count: number }[];
  by_kind_status?: { kind: string; status: string; count: number }[];
  pending_range: { oldest: string | null; newest: string | null } | null;
  orphan_pending: number;
  failed_samples: {
    id: string;
    task_type: string;
    kind?: string;
    paper_id: string | null;
    error: string;
    updated_at: string;
  }[];
};

const STATUS_LABEL: Record<string, string> = {
  queued: "排队",
  running: "执行中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const STATUS_TONE: Record<string, string> = {
  queued: "text-amber-900 bg-amber-50 border-amber-200",
  running: "text-sky-900 bg-sky-50 border-sky-200",
  completed: "text-emerald-800 bg-emerald-50 border-emerald-200",
  failed: "text-red-800 bg-red-50 border-red-200",
  cancelled: "text-ink-700 bg-mist-100 border-mist-200",
};

const KIND_TONE: Record<string, string> = {
  parse: "text-teal-900 bg-teal-50 border-teal-200",
  reindex: "text-violet-900 bg-violet-50 border-violet-200",
  index: "text-ink-800 bg-mist-100 border-mist-200",
  mineru_download: "text-sky-900 bg-sky-50 border-sky-200",
  summarize: "text-indigo-900 bg-indigo-50 border-indigo-200",
};

const KIND_ORDER = [
  "index",
  "parse",
  "mineru_download",
  "reindex",
  "summarize",
];

function labelStatus(s: string) {
  return STATUS_LABEL[s] ?? s;
}

function formatWhen(iso: string | null | undefined) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return iso;
  }
}

function countByStatus(rows: { status: string; count: number }[], status: string) {
  return rows.find((r) => r.status === status)?.count ?? 0;
}

function kindTone(kind: string) {
  return KIND_TONE[kind] ?? "text-ink-800 bg-mist-100 border-mist-200";
}

type Props = {
  autoRefresh?: boolean;
  intervalMs?: number;
  onQueueChanged?: () => void;
};

export function TaskStatsPanel({
  autoRefresh = false,
  intervalMs = 12_000,
  onQueueChanged,
}: Props) {
  const [open, setOpen] = useState(false);
  const [matrixOpen, setMatrixOpen] = useState(false);
  const [stats, setStats] = useState<TaskStatsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiGet<TaskStatsResponse>("/tasks/stats?failed_limit=8");
      setStats(data);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!autoRefresh) return;
    const t = window.setInterval(() => void load(), intervalMs);
    return () => window.clearInterval(t);
  }, [autoRefresh, intervalMs, load]);

  const queuedCount = countByStatus(stats?.by_status ?? [], "queued");
  const runningCount = countByStatus(stats?.by_status ?? [], "running");
  const failedCount = countByStatus(stats?.by_status ?? [], "failed");
  const pending = stats?.pending ?? 0;
  const orphanPending = stats?.orphan_pending ?? 0;

  const kindRows = useMemo(() => {
    const raw =
      stats?.by_kind && stats.by_kind.length > 0
        ? stats.by_kind
        : (stats?.by_type ?? []).map((r) => ({ kind: r.task_type, count: r.count }));
    return [...raw].sort((a, b) => {
      const ai = KIND_ORDER.indexOf(a.kind);
      const bi = KIND_ORDER.indexOf(b.kind);
      if (ai === -1 && bi === -1) return b.count - a.count;
      if (ai === -1) return 1;
      if (bi === -1) return -1;
      return ai - bi || b.count - a.count;
    });
  }, [stats]);

  const kindStatusRows = useMemo(() => {
    const raw =
      stats?.by_kind_status && stats.by_kind_status.length > 0
        ? stats.by_kind_status
        : (stats?.by_type_status ?? []).map((r) => ({
            kind: r.task_type,
            status: r.status,
            count: r.count,
          }));
    const statusOrder = ["running", "queued", "failed", "completed", "cancelled"];
    return [...raw].sort((a, b) => {
      const ka = KIND_ORDER.indexOf(a.kind);
      const kb = KIND_ORDER.indexOf(b.kind);
      if (ka !== kb) {
        if (ka === -1) return 1;
        if (kb === -1) return -1;
        return ka - kb;
      }
      const sa = statusOrder.indexOf(a.status);
      const sb = statusOrder.indexOf(b.status);
      return (sa === -1 ? 99 : sa) - (sb === -1 ? 99 : sb) || b.count - a.count;
    });
  }, [stats]);

  const activeKindRows = kindStatusRows.filter((r) =>
    ["queued", "running"].includes(r.status),
  );

  async function runAction(label: string, confirmText: string, path: string) {
    if (!window.confirm(confirmText)) return;
    setActionBusy(true);
    setActionMsg(null);
    setErr(null);
    try {
      const res = await apiPost<Record<string, number>>(path, {});
      const parts: string[] = [label];
      if (typeof res.cancelled === "number") parts.push(`取消排队 ${res.cancelled} 条`);
      if (typeof res.failed === "number" && res.failed > 0) parts.push(`标记失败 ${res.failed} 条`);
      if (typeof res.papers_reverted === "number" && res.papers_reverted > 0) {
        parts.push(`恢复文献状态 ${res.papers_reverted} 篇`);
      }
      setActionMsg(parts.join("："));
      await load();
      onQueueChanged?.();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "操作失败");
    } finally {
      setActionBusy(false);
    }
  }

  async function copyPaperId(paperId: string) {
    try {
      await navigator.clipboard.writeText(paperId);
      setCopiedId(paperId);
      window.setTimeout(() => setCopiedId((c) => (c === paperId ? null : c)), 2000);
    } catch {
      /* ignore */
    }
  }

  return (
    <section className="rounded-xl border border-mist-200 bg-white shadow-sm overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left hover:bg-mist-50/80"
        aria-expanded={open}
      >
        <div className="min-w-0 flex-1">
          <span className="text-sm font-semibold text-ink-950">任务队列概览</span>
          {stats != null && (
            <span className="mt-1 flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-ink-600">全表 {stats.total}</span>
              {queuedCount > 0 && (
                <StatusChip status="queued" label={`排队 ${queuedCount}`} />
              )}
              {runningCount > 0 && (
                <StatusChip status="running" label={`执行 ${runningCount}`} />
              )}
              {failedCount > 0 && (
                <StatusChip status="failed" label={`失败 ${failedCount}`} />
              )}
              {pending === 0 && failedCount === 0 && (
                <span className="text-xs text-emerald-800">· 空闲</span>
              )}
              {pending > 0 && (
                <span className="text-xs text-ink-500">
                  · Worker×{stats.worker_concurrency}
                </span>
              )}
            </span>
          )}
        </div>
        <span className="shrink-0 pt-0.5 text-xs text-ink-500">{open ? "收起 ▲" : "展开 ▼"}</span>
      </button>

      {open && (
        <div className="border-t border-mist-200 px-4 py-3 space-y-4">
          {stats && (
            <div className="grid grid-cols-3 gap-2">
              <MetricCard
                label="排队"
                value={queuedCount}
                tone="amber"
                hint={queuedCount > 0 ? "可「取消全部排队」" : undefined}
              />
              <MetricCard
                label="执行中"
                value={runningCount}
                tone="sky"
                hint={
                  runningCount > 0
                    ? `并发上限 ${stats.worker_concurrency}`
                    : undefined
                }
              />
              <MetricCard
                label="待处理合计"
                value={pending}
                tone="ink"
                hint={
                  stats.pending_range
                    ? `${formatWhen(stats.pending_range.oldest).slice(5)} 起`
                    : undefined
                }
              />
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void load()}
              disabled={loading || actionBusy}
              className="rounded-lg border border-mist-200 px-2.5 py-1 text-xs hover:bg-mist-100 disabled:opacity-50"
            >
              {loading ? "刷新中…" : "刷新"}
            </button>
            <button
              type="button"
              disabled={actionBusy || queuedCount === 0}
              onClick={() =>
                void runAction(
                  "已取消全部排队",
                  `确定取消全部排队中的任务？共 ${queuedCount} 条（不含正在执行的任务）。`,
                  "/tasks/cancel-queued",
                )
              }
              className="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs text-amber-950 hover:bg-amber-100 disabled:opacity-50"
              title="仅取消 status=queued，不中断 running"
            >
              取消全部排队{queuedCount > 0 ? `（${queuedCount}）` : ""}
            </button>
            <button
              type="button"
              disabled={actionBusy || orphanPending === 0}
              onClick={() =>
                void runAction(
                  "已清理孤儿任务",
                  `确定清理 ${orphanPending} 条指向已删/不存在文献的待处理任务？`,
                  "/tasks/cancel-orphans",
                )
              }
              className="rounded-lg border border-mist-200 px-2.5 py-1 text-xs hover:bg-mist-100 disabled:opacity-50"
            >
              清理孤儿任务{orphanPending > 0 ? `（${orphanPending}）` : ""}
            </button>
            {err && <span className="text-xs text-red-700">{err}</span>}
            {actionMsg && <span className="text-xs text-emerald-800">{actionMsg}</span>}
          </div>

          {stats && (
            <>
              {stats.orphan_pending > 0 && (
                <p className="text-xs text-amber-900 rounded-md border border-amber-200 bg-amber-50 px-2.5 py-2">
                  有 {stats.orphan_pending} 条待处理任务指向已删除/不存在的文献，建议「清理孤儿任务」。
                </p>
              )}

              {activeKindRows.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-500 mb-2">
                    进行中（按类型）
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {activeKindRows.map((r) => (
                      <span
                        key={`${r.kind}-${r.status}`}
                        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${kindTone(r.kind)}`}
                      >
                        <span
                          className={`rounded border px-1 py-0.5 text-[10px] font-medium ${STATUS_TONE[r.status] ?? "bg-mist-100 border-mist-200"}`}
                        >
                          {labelStatus(r.status)}
                        </span>
                        {labelTaskKind(r.kind)}
                        <strong className="tabular-nums">{r.count}</strong>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div className="grid gap-4 sm:grid-cols-2">
                <StatsTable
                  title="按状态"
                  rows={(stats.by_status ?? []).map((r) => ({
                    key: r.status,
                    col1: labelStatus(r.status),
                    col1Tone: STATUS_TONE[r.status],
                    count: r.count,
                  }))}
                />
                <StatsTable
                  title="按任务类型"
                  emptyHint="暂无任务记录"
                  rows={kindRows.map((r) => ({
                    key: r.kind,
                    col1: labelTaskKind(r.kind),
                    col1Tone: kindTone(r.kind),
                    count: r.count,
                  }))}
                />
              </div>

              {kindStatusRows.length > 0 && (
                <div>
                  <button
                    type="button"
                    onClick={() => setMatrixOpen((v) => !v)}
                    className="flex w-full items-center justify-between text-xs font-semibold uppercase tracking-wide text-ink-500 hover:text-ink-800"
                  >
                    <span>类型 × 状态明细（{kindStatusRows.length} 行）</span>
                    <span>{matrixOpen ? "收起 ▲" : "展开 ▼"}</span>
                  </button>
                  {matrixOpen && (
                    <div className="mt-2 overflow-x-auto rounded-lg border border-mist-200">
                      <table className="w-full min-w-[20rem] text-xs">
                        <thead className="bg-mist-50 text-ink-600">
                          <tr>
                            <th className="px-3 py-2 text-left font-medium">类型</th>
                            <th className="px-3 py-2 text-left font-medium">状态</th>
                            <th className="px-3 py-2 text-right font-medium">数量</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-mist-100">
                          {kindStatusRows.map((r) => (
                            <tr key={`${r.kind}-${r.status}`}>
                              <td className="px-3 py-2">
                                <span
                                  className={`inline-block rounded border px-1.5 py-0.5 ${kindTone(r.kind)}`}
                                >
                                  {labelTaskKind(r.kind)}
                                </span>
                              </td>
                              <td className="px-3 py-2">
                                <span
                                  className={`inline-block rounded border px-1.5 py-0.5 ${STATUS_TONE[r.status] ?? "bg-mist-100 border-mist-200"}`}
                                >
                                  {labelStatus(r.status)}
                                </span>
                              </td>
                              <td className="px-3 py-2 text-right tabular-nums font-medium">
                                {r.count}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {stats.failed_samples.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-500 mb-2">
                    最近失败（{stats.failed_samples.length}）
                  </h3>
                  <ul className="space-y-2 text-xs">
                    {stats.failed_samples.map((f) => (
                      <li
                        key={f.id}
                        className="rounded-lg border border-red-100 bg-red-50/60 px-2.5 py-2"
                      >
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                          <span
                            className={`rounded border px-1.5 py-0.5 ${kindTone(f.kind ?? f.task_type)}`}
                          >
                            {labelTaskKind(f.kind ?? f.task_type)}
                          </span>
                          <span className="text-ink-500">{formatWhen(f.updated_at)}</span>
                          {f.paper_id && (
                            <button
                              type="button"
                              onClick={() => void copyPaperId(f.paper_id!)}
                              className="font-mono text-[10px] text-sky-800 hover:underline"
                              title="复制 paper_id"
                            >
                              {f.paper_id.slice(0, 12)}…
                              {copiedId === f.paper_id ? " ✓" : ""}
                            </button>
                          )}
                        </div>
                        <p className="mt-1.5 text-red-900 break-words leading-relaxed line-clamp-4">
                          {f.error || "（无错误信息）"}
                        </p>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}

function StatusChip({ status, label }: { status: string; label: string }) {
  return (
    <span
      className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium ${STATUS_TONE[status] ?? "bg-mist-100 border-mist-200 text-ink-800"}`}
    >
      {label}
    </span>
  );
}

function MetricCard({
  label,
  value,
  tone,
  hint,
}: {
  label: string;
  value: number;
  tone: "amber" | "sky" | "ink";
  hint?: string;
}) {
  const tones = {
    amber: "border-amber-200 bg-amber-50/80",
    sky: "border-sky-200 bg-sky-50/80",
    ink: "border-mist-200 bg-mist-50/80",
  };
  const valueTones = {
    amber: "text-amber-950",
    sky: "text-sky-950",
    ink: "text-ink-950",
  };
  return (
    <div className={`rounded-lg border px-3 py-2 ${tones[tone]}`}>
      <div className="text-[10px] font-semibold uppercase tracking-wide text-ink-500">
        {label}
      </div>
      <div className={`mt-0.5 text-xl font-semibold tabular-nums ${valueTones[tone]}`}>
        {value}
      </div>
      {hint && <div className="mt-0.5 text-[10px] text-ink-600 truncate">{hint}</div>}
    </div>
  );
}

function StatsTable({
  title,
  rows,
  emptyHint,
}: {
  title: string;
  rows: { key: string; col1: string; col1Tone?: string; count: number }[];
  emptyHint?: string;
}) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-500 mb-2">
        {title}
      </h3>
      {rows.length === 0 ? (
        <p className="text-xs text-ink-500 rounded-lg border border-dashed border-mist-200 px-3 py-4 text-center">
          {emptyHint ?? "无数据"}
        </p>
      ) : (
        <table className="w-full text-xs rounded-lg border border-mist-200 overflow-hidden">
          <tbody className="divide-y divide-mist-100">
            {rows.map((r) => (
              <tr key={r.key}>
                <td className="px-3 py-2">
                  <span
                    className={`inline-block rounded border px-1.5 py-0.5 ${r.col1Tone ?? "bg-mist-100 border-mist-200 text-ink-800"}`}
                  >
                    {r.col1}
                  </span>
                </td>
                <td className="px-3 py-2 text-right tabular-nums font-medium">{r.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
