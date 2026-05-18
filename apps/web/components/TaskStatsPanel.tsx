"use client";

import { useCallback, useEffect, useState } from "react";
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
  queued: "text-amber-900 bg-amber-50",
  running: "text-sky-900 bg-sky-50",
  completed: "text-emerald-800 bg-emerald-50",
  failed: "text-red-800 bg-red-50",
  cancelled: "text-ink-700 bg-mist-100",
};

const KIND_TONE: Record<string, string> = {
  parse: "text-teal-900 bg-teal-50",
  reindex: "text-violet-900 bg-violet-50",
  index: "text-ink-800 bg-mist-100",
  summarize: "text-indigo-900 bg-indigo-50",
};

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
  const [stats, setStats] = useState<TaskStatsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

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

  const pending = stats?.pending ?? 0;
  const queuedCount =
    stats?.by_status.find((r) => r.status === "queued")?.count ?? 0;
  const orphanPending = stats?.orphan_pending ?? 0;

  const kindRows =
    stats?.by_kind && stats.by_kind.length > 0
      ? stats.by_kind
      : (stats?.by_type ?? []).map((r) => ({
          kind: r.task_type,
          count: r.count,
        }));

  const kindStatusRows =
    stats?.by_kind_status && stats.by_kind_status.length > 0
      ? stats.by_kind_status
      : (stats?.by_type_status ?? []).map((r) => ({
          kind: r.task_type,
          status: r.status,
          count: r.count,
        }));

  async function runAction(
    label: string,
    confirmText: string,
    path: string,
  ) {
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

  return (
    <section className="rounded-xl border border-mist-200 bg-white shadow-sm overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-mist-50/80"
        aria-expanded={open}
      >
        <div>
          <span className="text-sm font-semibold text-ink-950">任务队列概览</span>
          {stats != null && (
            <span className="mt-0.5 block text-xs text-ink-600">
              全表 {stats.total} 条
              {pending > 0 ? (
                <>
                  {" "}
                  · 待处理 <strong className="text-amber-900">{pending}</strong>（Worker 并发{" "}
                  {stats.worker_concurrency}）
                </>
              ) : (
                <> · 无排队任务</>
              )}
            </span>
          )}
        </div>
        <span className="shrink-0 text-xs text-ink-500">{open ? "收起 ▲" : "展开 ▼"}</span>
      </button>

      {open && (
        <div className="border-t border-mist-200 px-4 py-3 space-y-4">
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
              {stats.pending_range && (
                <p className="text-xs text-ink-600">
                  待处理任务创建时间：{formatWhen(stats.pending_range.oldest)} —{" "}
                  {formatWhen(stats.pending_range.newest)}
                </p>
              )}
              {stats.orphan_pending > 0 && (
                <p className="text-xs text-amber-900 rounded-md bg-amber-50 px-2 py-1.5">
                  有 {stats.orphan_pending} 条待处理任务指向已删除/不存在的文献，执行时可能失败。
                </p>
              )}

              <div className="grid gap-4 sm:grid-cols-2">
                <StatsTable
                  title="按状态"
                  rows={stats.by_status.map((r) => ({
                    key: r.status,
                    col1: labelStatus(r.status),
                    col1Tone: STATUS_TONE[r.status],
                    count: r.count,
                  }))}
                />
                <StatsTable
                  title="按任务类型"
                  rows={kindRows.map((r) => ({
                    key: r.kind,
                    col1: labelTaskKind(r.kind),
                    col1Tone: KIND_TONE[r.kind],
                    count: r.count,
                  }))}
                />
              </div>

              <div>
                <h3 className="text-xs font-semibold uppercase text-ink-500 mb-2">类型 × 状态</h3>
                <div className="overflow-x-auto rounded-lg border border-mist-200">
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
                          <td className="px-3 py-2">{labelTaskKind(r.kind)}</td>
                          <td className="px-3 py-2">
                            <span
                              className={`inline-block rounded px-1.5 py-0.5 ${STATUS_TONE[r.status] ?? "bg-mist-100"}`}
                            >
                              {labelStatus(r.status)}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-right tabular-nums font-medium">{r.count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {stats.failed_samples.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold uppercase text-ink-500 mb-2">最近失败（最多 8 条）</h3>
                  <ul className="space-y-2 text-xs">
                    {stats.failed_samples.map((f) => (
                      <li key={f.id} className="rounded-lg border border-red-100 bg-red-50/50 px-2.5 py-2">
                        <div className="flex flex-wrap gap-x-2 gap-y-0.5 text-ink-700">
                          <span>{labelTaskKind(f.kind ?? f.task_type)}</span>
                          <span className="text-ink-500">{formatWhen(f.updated_at)}</span>
                          {f.paper_id && (
                            <code className="text-[10px] text-ink-600">{f.paper_id.slice(0, 12)}…</code>
                          )}
                        </div>
                        <p className="mt-1 text-red-900 break-words">{f.error || "（无错误信息）"}</p>
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

function StatsTable({
  title,
  rows,
}: {
  title: string;
  rows: { key: string; col1: string; col1Tone?: string; count: number }[];
}) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase text-ink-500 mb-2">{title}</h3>
      <table className="w-full text-xs rounded-lg border border-mist-200 overflow-hidden">
        <tbody className="divide-y divide-mist-100">
          {rows.map((r) => (
            <tr key={r.key}>
              <td className="px-3 py-2">
                <span
                  className={`inline-block rounded px-1.5 py-0.5 ${r.col1Tone ?? "bg-mist-100 text-ink-800"}`}
                >
                  {r.col1}
                </span>
              </td>
              <td className="px-3 py-2 text-right tabular-nums font-medium">{r.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
