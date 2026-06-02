"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { resolveTaskKind } from "@/lib/taskKind";
import {
  computeQueueEstimate,
  computeQueueEstimatesByKind,
  createQueueThroughputWindow,
  mergeQueueThroughputWindow,
  recordQueueCompletion,
  touchTaskTimings,
  type KindStatusCount,
  type QueueEstimate,
  type QueueThroughputFromApi,
  type QueueThroughputWindow,
  type TaskTimingSnapshot,
} from "@/lib/taskMonitorMetrics";
import type { ActiveTaskRow } from "@/lib/useActiveTasks";

export type QueueEstimateResult = {
  overall: QueueEstimate;
  byKind: Record<string, QueueEstimate>;
};

/**
 * 根据当前队列已完成任务的真实耗时均值估算剩余时间。
 * serverThroughput 来自 GET /tasks/stats，刷新/恢复队列后可恢复均速。
 */
export function useQueueEstimate(
  items: ActiveTaskRow[],
  queuedCount: number,
  workerConcurrency: number | undefined,
  byKindStatus: KindStatusCount[] = [],
  serverThroughput: QueueThroughputFromApi | null | undefined = null,
): QueueEstimateResult {
  const [now, setNow] = useState(() => Date.now());
  const [localWindow, setLocalWindow] = useState<QueueThroughputWindow>(
    createQueueThroughputWindow,
  );
  const timingsRef = useRef<Map<string, TaskTimingSnapshot>>(new Map());
  const prevRunningRef = useRef<Map<string, ActiveTaskRow>>(new Map());

  const running = useMemo(
    () => items.filter((t) => t.status === "running"),
    [items],
  );
  const workers = Math.max(1, workerConcurrency ?? 1);
  const pending = running.length + Math.max(0, queuedCount);

  const effectiveWindow = useMemo(() => {
    if (pending === 0) return createQueueThroughputWindow();
    return mergeQueueThroughputWindow(localWindow, serverThroughput);
  }, [pending, localWindow, serverThroughput]);

  useEffect(() => {
    touchTaskTimings(timingsRef.current, items, Date.now());
  }, [items]);

  useEffect(() => {
    if (pending === 0) {
      setLocalWindow(createQueueThroughputWindow());
      prevRunningRef.current = new Map();
    }
  }, [pending]);

  useEffect(() => {
    const ts = Date.now();
    const currentIds = new Set(running.map((t) => t.id));
    const finished: { kind: string; durationMs?: number }[] = [];

    for (const [id, t] of prevRunningRef.current) {
      if (currentIds.has(id)) continue;
      const snap = timingsRef.current.get(id);
      finished.push({
        kind: resolveTaskKind(t),
        durationMs: snap ? ts - snap.runningSince : undefined,
      });
      timingsRef.current.delete(id);
    }

    if (finished.length > 0) {
      setLocalWindow((prev) => {
        let next = prev;
        for (const { kind, durationMs } of finished) {
          next = recordQueueCompletion(next, kind, ts, durationMs);
        }
        return next;
      });
    }
    prevRunningRef.current = new Map(running.map((t) => [t.id, t]));
  }, [running]);

  useEffect(() => {
    if (pending === 0) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [pending]);

  return useMemo(
    () => ({
      overall: computeQueueEstimate({
        running,
        queuedCount,
        now,
        window: effectiveWindow,
        workerConcurrency: workers,
      }),
      byKind: computeQueueEstimatesByKind({
        running,
        byKindStatus,
        now,
        window: effectiveWindow,
        workerConcurrency: workers,
      }),
    }),
    [running, queuedCount, workers, now, effectiveWindow, byKindStatus],
  );
}
