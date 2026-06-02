"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { TaskStatsResponse } from "@/components/TaskStatsPanel";
import { apiGet } from "@/lib/api";
import { labelTaskKind } from "@/lib/taskKind";
import {
  formatQueueEstimateBrief,
  formatQueueEstimateSummary,
} from "@/lib/taskMonitorMetrics";
import { useSharedActiveTasks } from "@/components/ActiveTasksProvider";
import { useQueueEstimate } from "@/lib/useQueueEstimate";

function countByStatus(rows: { status: string; count: number }[], status: string) {
  return rows.find((r) => r.status === status)?.count ?? 0;
}

/** 全站顶栏：任意页面可见后台任务队列与预计完成时间。 */
export function GlobalTaskQueueBanner() {
  const { activeItems, anyActive, startWatching, sync } = useSharedActiveTasks();
  const [stats, setStats] = useState<TaskStatsResponse | null>(null);

  const loadStats = useCallback(async () => {
    try {
      const data = await apiGet<TaskStatsResponse>("/tasks/stats?failed_limit=0");
      setStats(data);
    } catch {
      /* 后端不可达时静默 */
    }
  }, []);

  useEffect(() => {
    void loadStats();
  }, [loadStats]);

  useEffect(() => {
    if (anyActive) startWatching();
  }, [anyActive, startWatching]);

  useEffect(() => {
    if (!anyActive && (stats?.pending ?? 0) === 0) return;
    const id = window.setInterval(() => {
      void loadStats();
      void sync();
    }, 12_000);
    return () => window.clearInterval(id);
  }, [anyActive, stats?.pending, loadStats, sync]);

  const queuedCount = countByStatus(stats?.by_status ?? [], "queued");
  const runningCount = countByStatus(stats?.by_status ?? [], "running");
  const pending = stats?.pending ?? 0;

  const kindStatusRows = useMemo(
    () =>
      stats?.by_kind_status && stats.by_kind_status.length > 0
        ? stats.by_kind_status
        : (stats?.by_type_status ?? []).map((r) => ({
            kind: r.task_type,
            status: r.status,
            count: r.count,
          })),
    [stats],
  );

  const { overall, byKind } = useQueueEstimate(
    activeItems,
    queuedCount,
    stats?.worker_concurrency,
    kindStatusRows,
    stats?.queue_throughput,
  );

  const queueSummary = formatQueueEstimateSummary(overall);

  const kindEtaLines = useMemo(() => {
    const rows = kindStatusRows.filter((r) => ["queued", "running"].includes(r.status));
    const kinds = [...new Set(rows.map((r) => r.kind))];
    return kinds
      .map((kind) => {
        const est = byKind[kind];
        const brief = formatQueueEstimateBrief(est);
        if (!brief) return null;
        return `${labelTaskKind(kind)} ${brief}`;
      })
      .filter(Boolean) as string[];
  }, [kindStatusRows, byKind]);

  if (pending === 0) return null;

  return (
    <div className="border-b border-sky-200 bg-sky-50/90">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 text-xs text-sky-950">
        <span className="font-medium">后台任务</span>
        <span className="text-sky-900">
          执行中 {runningCount}
          {queuedCount > 0 ? ` · 排队 ${queuedCount}` : ""}
          {queueSummary ? ` · ${queueSummary}` : ""}
        </span>
        {kindEtaLines.length > 1 && (
          <span className="text-sky-800/90" title="按任务类型分别估算（共用 Worker 池）">
            {kindEtaLines.join(" · ")}
          </span>
        )}
        <Link
          href="/library"
          className="ml-auto shrink-0 font-medium text-sky-900 underline underline-offset-2 hover:text-sky-950"
        >
          文献库查看详情
        </Link>
      </div>
    </div>
  );
}
