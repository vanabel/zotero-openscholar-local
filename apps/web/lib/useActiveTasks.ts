"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiGet, subscribeActiveTasks, type TaskStreamEvent } from "@/lib/api";
import { isTaskActive } from "@/lib/taskKind";

export type ActiveTaskRow = {
  id: string;
  paper_id?: string | null;
  paper_title?: string | null;
  task_type?: string;
  kind?: string;
  payload?: {
    parse_only?: boolean;
    reindex_only?: boolean;
    force?: boolean;
    mineru_download_only?: boolean;
  } | null;
  status: string;
  progress?: {
    phase?: string;
    done?: number;
    total?: number;
    message?: string;
    task_started_at?: string;
    phase_started_at?: string;
    phase_history?: {
      phase: string;
      started_at?: string;
      ended_at?: string;
      duration_sec?: number;
      done?: number;
      total?: number;
    }[];
  } | null;
  error?: string | null;
  created_at?: string;
  updated_at?: string;
};

/** SSE 单条任务更新（不含 snapshot） */
type TaskStreamUpdate = Exclude<TaskStreamEvent, { type: "snapshot" }>;

function applySnapshot(items: ActiveTaskRow[]) {
  const byPaper = new Map<string, ActiveTaskRow>();
  const active: ActiveTaskRow[] = [];
  let anyActive = false;
  for (const t of items) {
    const pid = t.paper_id;
    if (pid) byPaper.set(pid, t);
    if (isTaskActive(t.status)) {
      anyActive = true;
      active.push(t);
    }
  }
  return { byPaper, active, anyActive };
}

function mergeEvent(prev: ActiveTaskRow | undefined, ev: TaskStreamUpdate): ActiveTaskRow {
  const base: ActiveTaskRow =
    prev ?? {
      id: ev.task_id,
      paper_id: ev.paper_id,
      task_type: ev.task_type ?? "index",
      status: ev.status ?? "running",
    };
  const err = ev.type === "task_status" ? ev.error : undefined;
  return {
    ...base,
    id: ev.task_id,
    paper_id: ev.paper_id ?? base.paper_id,
    task_type: ev.task_type ?? base.task_type,
    kind: ev.kind ?? base.kind,
    payload: ev.payload ?? base.payload,
    status: ev.status ?? base.status ?? "running",
    progress: ev.progress ?? base.progress,
    error: err ?? base.error,
  };
}

type Options = {
  /** 为 false 时不拉取、不订阅（默认 true） */
  enabled?: boolean;
  /** 全部任务结束（非 queued/running）时回调 */
  onAllIdle?: () => void;
  /** 单条任务进入终态（completed / failed / cancelled）时回调 */
  onTaskFinished?: (ev: Extract<TaskStreamEvent, { type: "task_status" }>) => void;
};

/**
 * 活动任务 SSE + 按 paper_id 索引；文献库列表与任务监控面板共用，避免重复连接。
 */
export function useActiveTasks({ enabled = true, onAllIdle, onTaskFinished }: Options = {}) {
  const [paperTasks, setPaperTasks] = useState<Map<string, ActiveTaskRow>>(new Map());
  const [activeItems, setActiveItems] = useState<ActiveTaskRow[]>([]);
  const [watching, setWatching] = useState(false);
  const hadActiveRef = useRef(false);

  const ingestSnapshot = useCallback(
    (items: ActiveTaskRow[]) => {
      const { byPaper, active, anyActive } = applySnapshot(items);
      setPaperTasks(byPaper);
      setActiveItems(active);
      if (anyActive) {
        hadActiveRef.current = true;
      } else if (hadActiveRef.current) {
        hadActiveRef.current = false;
        setWatching(false);
        onAllIdle?.();
      } else {
        setWatching(false);
      }
      return anyActive;
    },
    [onAllIdle],
  );

  const sync = useCallback(async () => {
    if (!enabled) return false;
    try {
      const data = await apiGet<{ items: ActiveTaskRow[] }>("/tasks/active");
      return ingestSnapshot(data.items);
    } catch {
      return false;
    }
  }, [enabled, ingestSnapshot]);

  const startWatching = useCallback(() => {
    if (enabled) setWatching(true);
  }, [enabled]);

  useEffect(() => {
    if (!enabled) return;
    void sync().then((any) => {
      if (any) setWatching(true);
    });
  }, [enabled, sync]);

  useEffect(() => {
    if (!enabled || !watching) return;
    const close = subscribeActiveTasks((ev: TaskStreamEvent) => {
      if (ev.type === "snapshot") {
        ingestSnapshot(ev.items as ActiveTaskRow[]);
        return;
      }
      const pid = ev.paper_id;
      if (!pid) return;
      setPaperTasks((prev) => {
        const next = new Map(prev);
        next.set(pid, mergeEvent(next.get(pid), ev));
        return next;
      });
      setActiveItems((prev) => {
        const merged = mergeEvent(
          prev.find((t) => t.paper_id === pid),
          ev,
        );
        const rest = prev.filter((t) => t.paper_id !== pid);
        if (isTaskActive(merged.status)) {
          return [...rest, merged].sort(compareActiveTasks);
        }
        return rest;
      });
      if (ev.type === "task_status" && !isTaskActive(ev.status)) {
        onTaskFinished?.(ev);
        void sync();
      }
    });
    return close;
  }, [enabled, watching, ingestSnapshot, sync, onTaskFinished]);

  const anyActive = useMemo(() => activeItems.length > 0, [activeItems]);

  return {
    paperTasks,
    activeItems,
    watching,
    anyActive,
    startWatching,
    sync,
  };
}

export function compareActiveTasks(a: ActiveTaskRow, b: ActiveTaskRow): number {
  const rank = (s: string) => (s === "running" ? 0 : s === "queued" ? 1 : 2);
  const d = rank(a.status) - rank(b.status);
  if (d !== 0) return d;
  return (a.created_at ?? "").localeCompare(b.created_at ?? "");
}
