"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  type ActiveTaskRow,
  compareActiveTasks,
} from "@/lib/useActiveTasks";
import { labelTaskKind, resolveTaskKind } from "@/lib/taskKind";
import {
  buildPhaseRows,
  computeOverallProgress,
  formatPhaseDetail,
  formatQueueEstimateBrief,
  formatQueueEstimateSummary,
  type PhaseRowView,
  type QueueEstimate,
  type TaskTimingSnapshot,
  totalElapsedForTask,
  touchTaskTimings,
} from "@/lib/taskMonitorMetrics";

function OverallProgressBar({
  percent,
  phaseSummary,
}: {
  percent: number;
  phaseSummary: string | null;
}) {
  return (
    <div className="flex items-center gap-2">
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2 text-[10px] text-ink-600 mb-0.5">
          <span className="font-medium text-ink-800">总进度</span>
          <span className="tabular-nums shrink-0 flex items-baseline gap-1.5">
            <span className="text-xs font-semibold text-sky-800">{percent}%</span>
            {phaseSummary ? (
              <span className="text-ink-500 font-normal">{phaseSummary}</span>
            ) : null}
          </span>
        </div>
        <div
          className="h-1.5 rounded-full bg-mist-200 overflow-hidden"
          role="progressbar"
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`总进度 ${percent}%`}
        >
          <div
            className="h-full rounded-full bg-sky-500 transition-[width] duration-500"
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>
    </div>
  );
}

function displayTitle(t: ActiveTaskRow) {
  const title = t.paper_title?.trim();
  if (title) return title;
  const pid = t.paper_id;
  if (!pid) return "（无文献）";
  return `${pid.slice(0, 12)}…`;
}

function phaseIcon(status: PhaseRowView["status"]) {
  if (status === "done") return "✓";
  if (status === "running") return "▶";
  if (status === "skipped") return "—";
  return "○";
}

function PhaseRow({ row }: { row: PhaseRowView }) {
  const detail = formatPhaseDetail(row);
  const running = row.status === "running";

  return (
    <li
      className={`flex items-baseline gap-1.5 py-0.5 text-[10px] leading-snug min-w-0 ${
        running ? "text-ink-900" : row.status === "done" ? "text-ink-700" : "text-ink-500"
      }`}
    >
      <span className="shrink-0 w-3 text-center tabular-nums" aria-hidden>
        {phaseIcon(row.status)}
      </span>
      <span className={`shrink-0 ${running ? "font-medium" : ""}`}>{row.label}</span>
      <span className="min-w-0 flex-1 truncate text-right tabular-nums text-ink-500">
        {detail}
      </span>
    </li>
  );
}

type Props = {
  items: ActiveTaskRow[];
  workerConcurrency?: number;
  indexEmbedConcurrency?: number;
  queuedCount?: number;
  queueEstimate?: QueueEstimate;
  byKindEstimates?: Record<string, QueueEstimate>;
};

export function ActiveTasksMonitor({
  items,
  workerConcurrency,
  indexEmbedConcurrency,
  queuedCount: queuedFromStats,
  queueEstimate,
  byKindEstimates,
}: Props) {
  const [open, setOpen] = useState(true);
  const [now, setNow] = useState(() => Date.now());
  const timingsRef = useRef<Map<string, TaskTimingSnapshot>>(new Map());

  const running = useMemo(
    () => [...items].filter((t) => t.status === "running").sort(compareActiveTasks),
    [items],
  );
  const queuedInStream = useMemo(
    () => items.filter((t) => t.status === "queued").length,
    [items],
  );
  const queuedCount = queuedFromStats ?? queuedInStream;
  const queueSummary = queueEstimate ? formatQueueEstimateSummary(queueEstimate) : null;
  const kindEtaLines = useMemo(() => {
    if (!byKindEstimates) return [];
    return Object.entries(byKindEstimates)
      .map(([kind, est]) => {
        const brief = formatQueueEstimateBrief(est);
        if (!brief) return null;
        return `${labelTaskKind(kind)} ${brief}`;
      })
      .filter(Boolean) as string[];
  }, [byKindEstimates]);

  useEffect(() => {
    touchTaskTimings(timingsRef.current, items, Date.now());
  }, [items]);

  useEffect(() => {
    if (running.length === 0 && queuedCount === 0) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [running.length, queuedCount]);

  if (running.length === 0 && queuedCount === 0) return null;

  const queuedOnly = running.length === 0 && queuedCount > 0;

  return (
    <section className="rounded-xl border border-sky-200 bg-sky-50/40 shadow-sm overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left hover:bg-sky-50/80"
        aria-expanded={open}
      >
        <div className="min-w-0 flex-1">
          <span className="text-sm font-semibold text-ink-950">
            {queuedOnly ? "任务排队中" : "正在处理 · 按文献"}
          </span>
          <span className="mt-1 block text-xs text-ink-600">
            {queuedOnly ? (
              <>排队 {queuedCount}{queueSummary ? ` · ${queueSummary}` : ""}</>
            ) : (
              <>
                执行中 {running.length}
                {queuedCount > 0 ? ` · 排队 ${queuedCount}` : ""}
                {workerConcurrency != null && workerConcurrency > 0
                  ? ` · 任务并发 ${workerConcurrency}`
                  : ""}
                {indexEmbedConcurrency != null && indexEmbedConcurrency > 0
                  ? ` · 嵌入 API ${indexEmbedConcurrency} 路`
                  : ""}
                {queueSummary ? ` · ${queueSummary}` : ""}
              </>
            )}
          </span>
          {kindEtaLines.length > 1 && (
            <span className="mt-0.5 block text-[10px] text-sky-800">
              分类型：{kindEtaLines.join(" · ")}
            </span>
          )}
          {workerConcurrency != null &&
            running.length > 0 &&
            running.length < workerConcurrency &&
            queuedCount > 0 && (
              <span className="mt-0.5 block text-[10px] text-amber-800">
                未满额：running 最多 {workerConcurrency} 篇；其余在排队。嵌入阶段全局仅{" "}
                {indexEmbedConcurrency ?? 2} 路并行，与「执行中」篇数无关。
              </span>
            )}
          {workerConcurrency != null &&
            indexEmbedConcurrency != null &&
            running.length >= indexEmbedConcurrency &&
            indexEmbedConcurrency < workerConcurrency && (
              <span className="mt-0.5 block text-[10px] text-ink-500">
                多篇同时在嵌入时，实际调用嵌入 API 的约 {indexEmbedConcurrency} 路（
                INDEX_EMBED_CONCURRENCY）；要提高请改 .env 并重启 API。
              </span>
            )}
        </div>
        <span className="shrink-0 text-xs text-ink-500">{open ? "收起 ▲" : "展开 ▼"}</span>
      </button>

      {open && !queuedOnly && (
        <ul className="border-t border-sky-200/80 divide-y divide-sky-100/80 bg-white/70">
          {running.map((t) => {
            const kind = resolveTaskKind(t);
            const snap = timingsRef.current.get(t.id);
            const phases = buildPhaseRows(t, now);
            const totalElapsed = totalElapsedForTask(t, snap, now);
            const overall = computeOverallProgress(t, now);

            return (
              <li key={t.id} className="px-4 py-2.5 space-y-1.5">
                <div className="flex items-center justify-between gap-2 min-w-0">
                  <p
                    className="text-sm font-medium text-ink-950 truncate"
                    title={t.paper_title ?? t.paper_id ?? ""}
                  >
                    {displayTitle(t)}
                  </p>
                  <span className="shrink-0 text-[10px] tabular-nums text-sky-800">
                    {totalElapsed}
                  </span>
                </div>
                <p className="text-[10px] text-ink-500 -mt-1">
                  <span className="font-mono">{t.paper_id?.slice(0, 12)}</span>
                  <span className="mx-1">·</span>
                  {labelTaskKind(kind)}
                </p>

                <ol className="space-y-0">
                  {phases
                    .filter((row) => row.status !== "skipped")
                    .map((row) => (
                      <PhaseRow key={row.phase} row={row} />
                    ))}
                </ol>

                <div className="border-t border-mist-100 pt-1.5">
                  <OverallProgressBar
                    percent={overall.percent}
                    phaseSummary={overall.phaseSummary}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {open && queuedOnly && (
        <p className="border-t border-sky-200/80 bg-white/70 px-4 py-3 text-xs text-ink-600 leading-relaxed">
          Worker 即将从队列取走任务；完成首批任务后将按队列整体均速显示剩余时间。
          {workerConcurrency != null && workerConcurrency > 1
            ? ` 当前任务并发 ${workerConcurrency}，可同时处理多篇。`
            : null}
        </p>
      )}
    </section>
  );
}
