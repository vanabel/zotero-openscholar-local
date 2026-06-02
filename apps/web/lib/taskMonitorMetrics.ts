import { labelPhase, pipelinePhasesForKind } from "@/lib/taskPipeline";
import { resolveTaskKind } from "@/lib/taskKind";
import type { ActiveTaskRow } from "@/lib/useActiveTasks";

export type PhaseHistoryEntry = {
  phase: string;
  started_at?: string;
  ended_at?: string;
  duration_sec?: number;
  done?: number;
  total?: number;
};

/** 任务真正开始计时的锚点（勿用 updated_at，会随进度刷新跳动）。 */
export function taskRunningSinceMs(t: ActiveTaskRow): number | null {
  const progress = t.progress;
  const fromTask = parseIsoMs(progress?.task_started_at);
  if (fromTask != null) return fromTask;

  const history = progress?.phase_history ?? [];
  let earliest: number | null = null;
  for (const h of history) {
    const s = parseIsoMs(h.started_at);
    if (s != null && (earliest == null || s < earliest)) earliest = s;
  }
  if (earliest != null) return earliest;

  const fromPhase = parseIsoMs(progress?.phase_started_at);
  if (fromPhase != null) return fromPhase;

  return parseIsoMs(t.created_at);
}

function historyElapsedMs(hist: PhaseHistoryEntry): number {
  if (hist.duration_sec != null && hist.duration_sec > 0) {
    return Math.round(hist.duration_sec * 1000);
  }
  const start = parseIsoMs(hist.started_at);
  const end = parseIsoMs(hist.ended_at);
  if (start != null && end != null) return Math.max(0, end - start);
  return 0;
}

export type TaskTimingSnapshot = {
  runningSince: number;
};

export type PhaseRowStatus = "pending" | "running" | "done" | "skipped";

export type PhaseRowView = {
  phase: string;
  label: string;
  status: PhaseRowStatus;
  duration: string | null;
  rate: string | null;
  progress: string | null;
  eta: string | null;
};

export function formatDuration(ms: number): string {
  if (ms < 1000) return "<1 秒";
  const sec = Math.max(0, Math.floor(ms / 1000));
  if (sec < 60) return `${sec} 秒`;
  const min = Math.floor(sec / 60);
  const s = sec % 60;
  if (min < 60) return s > 0 ? `${min} 分 ${s} 秒` : `${min} 分`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m > 0 ? `${h} 时 ${m} 分` : `${h} 时`;
}

export function formatRate(perSec: number, unit: string): string {
  if (!Number.isFinite(perSec) || perSec <= 0) return "—";
  if (perSec >= 10) return `${perSec.toFixed(0)} ${unit}/秒`;
  if (perSec >= 1) return `${perSec.toFixed(1)} ${unit}/秒`;
  const perMin = perSec * 60;
  if (perMin >= 1) return `${perMin.toFixed(1)} ${unit}/分`;
  return `<1 ${unit}/分`;
}

/** 队列均速：每完成 1 单位所需时间，如「3 分 25 秒/篇」。 */
export function formatPacePerItem(perSec: number, unit = "篇"): string {
  if (!Number.isFinite(perSec) || perSec <= 0) return "—";
  return `${formatDuration(1000 / perSec)}/${unit}`;
}

export function progressUnit(phase: string): string {
  if (phase === "embed" || phase === "scholar_embed") return "块";
  if (phase === "chunk" || phase === "save") return "步";
  if (phase === "parse" || phase === "summarize") return "步";
  return "项";
}

export function parseIsoMs(iso: string | undefined): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isFinite(t) ? t : null;
}

function averageSpeed(done: number, startDone: number, elapsedMs: number, minSec = 1): number | null {
  const elapsedSec = elapsedMs / 1000;
  if (elapsedSec < minSec) return null;
  const completed = done - startDone;
  if (completed <= 0) return null;
  return completed / elapsedSec;
}

function formatProgress(done: number, total: number): string | null {
  if (total <= 0) return null;
  return `${done}/${total}`;
}

function metricsFromSpan(
  phase: string,
  done: number,
  total: number,
  elapsedMs: number,
  startDone = 0,
): { duration: string; rate: string | null; progress: string | null; eta: string | null } {
  const unit = progressUnit(phase);
  const perSec = averageSpeed(done, startDone, elapsedMs);
  const rate = perSec != null ? formatRate(perSec, unit) : null;
  let eta: string | null = null;
  if (perSec != null && total > 0) {
    const left = total - done;
    if (left <= 0) eta = null;
    else eta = `约 ${formatDuration((left / perSec) * 1000)}`;
  }
  return {
    duration: formatDuration(elapsedMs),
    rate,
    progress: formatProgress(done, total),
    eta,
  };
}

/** 未启用 OpenScholar Retriever 时后端会跳过 scholar_embed，从模板中去掉以免显示「跳过」。 */
export function pipelinePhasesForTask(kind: string, t: ActiveTaskRow): string[] {
  let phases = pipelinePhasesForKind(kind);
  if (!phases.includes("scholar_embed")) return phases;

  const progress = t.progress;
  const history = progress?.phase_history ?? [];
  const current = progress?.phase;
  const hadScholar =
    history.some((h) => h.phase === "scholar_embed") || current === "scholar_embed";
  if (hadScholar) return phases;

  const pastEmbed =
    history.some((h) => h.phase === "embed") || current === "save" || current === "done";
  if (pastEmbed) {
    phases = phases.filter((p) => p !== "scholar_embed");
  }
  return phases;
}

export function buildPhaseRows(t: ActiveTaskRow, now: number): PhaseRowView[] {
  const kind = resolveTaskKind(t);
  const template = pipelinePhasesForTask(kind, t);
  const progress = t.progress;
  const history = (progress?.phase_history ?? []) as PhaseHistoryEntry[];
  const historyMap = new Map(history.map((h) => [h.phase, h]));
  const historyPhases = new Set(history.map((h) => h.phase));
  const current = progress?.phase;
  const currentIdx = current ? template.indexOf(current) : -1;

  return template.map((phase, idx) => {
    const label = labelPhase(phase);
    const hist = historyMap.get(phase);
    if (hist) {
      const done = hist.done ?? 0;
      const total = hist.total ?? 0;
      const elapsedMs = historyElapsedMs(hist);
      const m = metricsFromSpan(phase, done, total, elapsedMs, 0);
      return {
        phase,
        label,
        status: "done" as const,
        duration: m.duration,
        rate: m.rate,
        progress: m.progress,
        eta: null,
      };
    }
    if (phase === current) {
      const start = parseIsoMs(progress?.phase_started_at) ?? now;
      const done = progress?.done ?? 0;
      const total = progress?.total ?? 0;
      const m = metricsFromSpan(phase, done, total, now - start, 0);
      const liveMsg = progress?.message?.trim();
      const progressText =
        liveMsg || m.progress || (total > 0 ? `${done}/${total}` : null);
      return {
        phase,
        label,
        status: "running" as const,
        duration: m.duration,
        rate: m.rate,
        progress: progressText,
        eta: m.eta,
      };
    }
    if (currentIdx >= 0 && idx < currentIdx && !historyPhases.has(phase)) {
      return {
        phase,
        label,
        status: "skipped" as const,
        duration: null,
        rate: null,
        progress: null,
        eta: null,
      };
    }
    return {
      phase,
      label,
      status: "pending" as const,
      duration: null,
      rate: null,
      progress: null,
      eta: null,
    };
  });
}

export function touchTaskTimings(
  store: Map<string, TaskTimingSnapshot>,
  tasks: ActiveTaskRow[],
  now: number,
): void {
  const running = tasks.filter((t) => t.status === "running");
  const ids = new Set(running.map((t) => t.id));
  for (const id of store.keys()) {
    if (!ids.has(id)) store.delete(id);
  }
  for (const t of running) {
    const apiStart = taskRunningSinceMs(t) ?? now;
    const existing = store.get(t.id);
    if (!existing || apiStart < existing.runningSince) {
      store.set(t.id, { runningSince: apiStart });
    }
  }
}

export function totalElapsedForTask(t: ActiveTaskRow, snap: TaskTimingSnapshot | undefined, now: number): string {
  const start = snap?.runningSince ?? taskRunningSinceMs(t) ?? now;
  return formatDuration(now - start);
}

export type OverallProgress = {
  percent: number;
  /** 多阶段时如「3/5 阶段」；单阶段为空 */
  phaseSummary: string | null;
  currentLabel: string | null;
  currentDetail: string | null;
};

function phaseFraction(row: PhaseRowView, t: ActiveTaskRow): number {
  if (row.status === "done" || row.status === "skipped") return 1;
  if (row.status === "pending") return 0;
  if (row.status === "running") {
    const p = t.progress;
    if (p?.phase === row.phase && p.total != null && p.total > 0) {
      const frac = (p.done ?? 0) / p.total;
      // 无中间计数时（如 summarize 0/1）将该阶段视为进行中 50%，避免总进度长期 0%
      if (frac <= 0) return 0.5;
      return Math.min(1, Math.max(0, frac));
    }
    return 0.05;
  }
  return 0;
}

/** 各阶段等权汇总：已完成/跳过=100%，进行中=本阶段 done/total，待处理=0% */
/** 阶段右侧单行摘要（1 行展示用） */
export function formatPhaseDetail(row: PhaseRowView): string {
  if (row.status === "skipped") return "跳过";
  if (row.status === "pending") return "待处理";
  const parts: string[] = [];
  if (row.duration != null) parts.push(row.duration);
  if (row.progress != null) {
    const m = row.progress.match(/^(\d+)\/(\d+)$/);
    if (row.status === "done" && m && Number(m[1]) < Number(m[2])) {
      parts.push(`共 ${m[2]}`);
    } else {
      parts.push(row.progress);
    }
  }
  if (row.rate != null) parts.push(`均速 ${row.rate}`);
  if (row.eta != null) parts.push(`剩余 ${row.eta}`);
  return parts.length > 0 ? parts.join(" · ") : "—";
}

export function computeOverallProgress(t: ActiveTaskRow, now: number): OverallProgress {
  const rows = buildPhaseRows(t, now);
  if (rows.length === 0) {
    return { percent: 0, phaseSummary: null, currentLabel: null, currentDetail: null };
  }
  let sum = 0;
  let currentLabel: string | null = null;
  let currentDetail: string | null = null;
  for (const row of rows) {
    sum += phaseFraction(row, t);
    if (row.status === "running") {
      currentLabel = row.label;
      currentDetail = row.progress;
    }
  }
  const percent = Math.min(100, Math.max(0, Math.round((sum / rows.length) * 100)));
  const finished = rows.filter((r) => r.status === "done" || r.status === "skipped").length;
  const phaseSummary =
    rows.length > 1 ? `${finished}/${rows.length} 阶段` : null;
  return { percent, phaseSummary, currentLabel, currentDetail };
}

const MIN_QUEUE_ELAPSED_MS = 5000;
const MIN_QUEUE_COMPLETED = 1;

export type QueueEstimate = {
  /** 剩余工作量（篇·当量：排队 1 + 进行中未完成比例） */
  remainingTasks: number;
  etaMs: number | null;
  etaLabel: string | null;
  throughputLabel: string | null;
  reliable: boolean;
  /** 当前窗口内已完成篇数（用于展示） */
  completedCount: number;
};

export type QueueThroughputWindow = {
  /** 本批次首次完成时刻（墙钟均速备用，非入队时刻） */
  startedAt: number | null;
  completedCount: number;
  completedByKind: Record<string, number>;
  kindStartedAt: Record<string, number>;
  /** 已完成任务真实耗时均值（毫秒） */
  avgDurationMs: number | null;
  avgDurationMsByKind: Record<string, number>;
};

export function createQueueThroughputWindow(): QueueThroughputWindow {
  return {
    startedAt: null,
    completedCount: 0,
    completedByKind: {},
    kindStartedAt: {},
    avgDurationMs: null,
    avgDurationMsByKind: {},
  };
}

/** 后端 GET /tasks/stats 的 queue_throughput 字段 */
export type QueueThroughputFromApi = {
  batch_started_at: string;
  batch_ended_at: string;
  throughput_started_at?: string | null;
  completed_count: number;
  completed_by_kind: Record<string, number>;
  kind_first_completed_at: Record<string, string>;
  avg_duration_sec?: number | null;
  avg_duration_sec_by_kind?: Record<string, number>;
};

function mergeWeightedAvgMs(
  aMs: number | null,
  aCount: number,
  bMs: number | null,
  bCount: number,
): number | null {
  if (aMs == null && bMs == null) return null;
  if (aCount <= 0) return bMs ?? aMs;
  if (bCount <= 0) return aMs ?? bMs;
  if (aMs == null) return bMs;
  if (bMs == null) return aMs;
  return (aMs * aCount + bMs * bCount) / (aCount + bCount);
}

export function queueWindowFromApi(api: QueueThroughputFromApi): QueueThroughputWindow {
  const throughputStart = parseIsoMs(api.throughput_started_at ?? undefined);
  return {
    startedAt: throughputStart,
    completedCount: api.completed_count,
    completedByKind: { ...api.completed_by_kind },
    kindStartedAt: Object.fromEntries(
      Object.entries(api.kind_first_completed_at)
        .map(([kind, iso]) => [kind, parseIsoMs(iso)])
        .filter((entry): entry is [string, number] => entry[1] != null),
    ),
    avgDurationMs:
      api.avg_duration_sec != null && api.avg_duration_sec > 0
        ? Math.round(api.avg_duration_sec * 1000)
        : null,
    avgDurationMsByKind: Object.fromEntries(
      Object.entries(api.avg_duration_sec_by_kind ?? {})
        .filter(([, sec]) => sec > 0)
        .map(([kind, sec]) => [kind, Math.round(sec * 1000)]),
    ),
  };
}

/** 合并本地 SSE 计数与后端批次统计（取较大 completed、合并耗时均值）。 */
export function mergeQueueThroughputWindow(
  local: QueueThroughputWindow,
  server: QueueThroughputFromApi | null | undefined,
): QueueThroughputWindow {
  if (!server?.batch_started_at) return local;

  const fromApi = queueWindowFromApi(server);
  const completedByKind = { ...fromApi.completedByKind };
  for (const [kind, count] of Object.entries(local.completedByKind)) {
    completedByKind[kind] = Math.max(completedByKind[kind] ?? 0, count);
  }

  const kindStartedAt = { ...fromApi.kindStartedAt };
  for (const [kind, ts] of Object.entries(local.kindStartedAt)) {
    const prev = kindStartedAt[kind];
    kindStartedAt[kind] = prev == null ? ts : Math.min(prev, ts);
  }

  const avgDurationMsByKind = { ...fromApi.avgDurationMsByKind };
  for (const kind of new Set([
    ...Object.keys(fromApi.avgDurationMsByKind),
    ...Object.keys(local.avgDurationMsByKind),
  ])) {
    avgDurationMsByKind[kind] =
      mergeWeightedAvgMs(
        fromApi.avgDurationMsByKind[kind] ?? null,
        fromApi.completedByKind[kind] ?? 0,
        local.avgDurationMsByKind[kind] ?? null,
        local.completedByKind[kind] ?? 0,
      ) ?? avgDurationMsByKind[kind] ?? local.avgDurationMsByKind[kind] ?? 0;
    if (!avgDurationMsByKind[kind]) delete avgDurationMsByKind[kind];
  }

  const completedCount = Math.max(fromApi.completedCount, local.completedCount);
  const avgDurationMs = mergeWeightedAvgMs(
    fromApi.avgDurationMs,
    fromApi.completedCount,
    local.avgDurationMs,
    local.completedCount,
  );

  const startedAt =
    local.startedAt == null
      ? fromApi.startedAt
      : fromApi.startedAt == null
        ? local.startedAt
        : Math.min(local.startedAt, fromApi.startedAt);

  return {
    startedAt,
    completedCount,
    completedByKind,
    kindStartedAt,
    avgDurationMs,
    avgDurationMsByKind,
  };
}

function remainingTaskEquivalents(running: ActiveTaskRow[], queuedCount: number, now: number): number {
  let remainingEq = 0;
  for (const t of running) {
    const { percent } = computeOverallProgress(t, now);
    remainingEq += 1 - Math.min(1, Math.max(0, percent / 100));
  }
  return remainingEq + Math.max(0, queuedCount);
}

function emptyQueueEstimate(remainingEq: number): QueueEstimate {
  return {
    remainingTasks: remainingEq,
    etaMs: null,
    etaLabel: null,
    throughputLabel: null,
    reliable: false,
    completedCount: 0,
  };
}

/**
 * 优先用已完成任务真实耗时均值；否则用自首次完成起的墙钟吞吐（均不用入队时刻）。
 */
export function computeQueueEstimate(params: {
  running: ActiveTaskRow[];
  queuedCount: number;
  now: number;
  window: QueueThroughputWindow;
  workerConcurrency?: number;
}): QueueEstimate {
  const { running, queuedCount, now, window, workerConcurrency } = params;
  const workers = Math.max(1, workerConcurrency ?? 1);
  const remainingEq = remainingTaskEquivalents(running, queuedCount, now);

  if (remainingEq <= 0) {
    return {
      remainingTasks: 0,
      etaMs: null,
      etaLabel: null,
      throughputLabel: null,
      reliable: false,
      completedCount: window.completedCount,
    };
  }

  const { completedCount, startedAt, avgDurationMs } = window;
  if (completedCount < MIN_QUEUE_COMPLETED) {
    return { ...emptyQueueEstimate(remainingEq), completedCount };
  }

  if (avgDurationMs != null && avgDurationMs > 0) {
    const etaMs = (remainingEq * avgDurationMs) / workers;
    return {
      remainingTasks: remainingEq,
      etaMs,
      etaLabel: `约 ${formatDuration(etaMs)}`,
      throughputLabel: `${formatDuration(avgDurationMs)}/篇`,
      reliable: true,
      completedCount,
    };
  }

  if (startedAt == null) {
    return { ...emptyQueueEstimate(remainingEq), completedCount };
  }

  const elapsedMs = now - startedAt;
  if (elapsedMs < MIN_QUEUE_ELAPSED_MS) {
    return { ...emptyQueueEstimate(remainingEq), completedCount };
  }

  const throughputPerSec = completedCount / (elapsedMs / 1000);
  if (!Number.isFinite(throughputPerSec) || throughputPerSec <= 0) {
    return { ...emptyQueueEstimate(remainingEq), completedCount };
  }

  const etaMs = (remainingEq / throughputPerSec) * 1000;

  return {
    remainingTasks: remainingEq,
    etaMs,
    etaLabel: `约 ${formatDuration(etaMs)}`,
    throughputLabel: formatPacePerItem(throughputPerSec, "篇"),
    reliable: true,
    completedCount,
  };
}

export function formatQueueEstimateSummary(est: QueueEstimate): string | null {
  if (est.reliable && est.etaLabel && est.throughputLabel) {
    const doneHint =
      est.completedCount > 0 ? `（已完成 ${est.completedCount} 篇均速）` : "";
    return `队列剩余 ${est.etaLabel} · 均速 ${est.throughputLabel}${doneHint}`;
  }
  if (est.remainingTasks > 0) {
    const n = Math.round(est.remainingTasks * 10) / 10;
    if (est.completedCount > 0) {
      return `剩余 ${n} 篇当量 · 已完成 ${est.completedCount} 篇，样本不足`;
    }
    return `剩余 ${n} 篇当量 · 等待队列中首批任务完成`;
  }
  return null;
}

/** 类型标签旁紧凑展示（如「约 2 时」） */
export function formatQueueEstimateBrief(est: QueueEstimate | undefined): string | null {
  if (!est) return null;
  if (est.reliable && est.etaLabel) return est.etaLabel;
  if (est.remainingTasks > 0) return "估算中…";
  return null;
}

export type KindStatusCount = { kind: string; status: string; count: number };

export function queuedCountByKind(rows: KindStatusCount[]): Record<string, number> {
  const m: Record<string, number> = {};
  for (const r of rows) {
    if (r.status !== "queued") continue;
    m[r.kind] = (m[r.kind] ?? 0) + r.count;
  }
  return m;
}

/** 按任务类型（索引 / 摘要 / 解析等）分别估算队列剩余时间。 */
export function computeQueueEstimatesByKind(params: {
  running: ActiveTaskRow[];
  byKindStatus: KindStatusCount[];
  now: number;
  window: QueueThroughputWindow;
  workerConcurrency?: number;
}): Record<string, QueueEstimate> {
  const { running, byKindStatus, now, window, workerConcurrency } = params;
  const queuedByKind = queuedCountByKind(byKindStatus);
  const kinds = new Set<string>([
    ...Object.keys(queuedByKind),
    ...running.map((t) => resolveTaskKind(t)),
  ]);
  const result: Record<string, QueueEstimate> = {};
  for (const kind of kinds) {
    const kindRunning = running.filter((t) => resolveTaskKind(t) === kind);
    const kindQueued = queuedByKind[kind] ?? 0;
    if (kindRunning.length === 0 && kindQueued === 0) continue;
    const kindCompleted = window.completedByKind[kind] ?? 0;
    result[kind] = computeQueueEstimate({
      running: kindRunning,
      queuedCount: kindQueued,
      now,
      workerConcurrency,
      window: {
        startedAt: window.kindStartedAt[kind] ?? window.startedAt,
        completedCount: kindCompleted,
        completedByKind: window.completedByKind,
        kindStartedAt: window.kindStartedAt,
        avgDurationMs: window.avgDurationMsByKind[kind] ?? null,
        avgDurationMsByKind: window.avgDurationMsByKind,
      },
    });
  }
  return result;
}

function updateRunningAvgMs(
  prevAvg: number | null,
  prevCount: number,
  durationMs: number,
): number {
  if (prevCount <= 0 || prevAvg == null) return durationMs;
  return (prevAvg * prevCount + durationMs) / (prevCount + 1);
}

/** 任务完成时更新队列吞吐窗口（累计所有已完成，非滑动样本）。 */
export function recordQueueCompletion(
  window: QueueThroughputWindow,
  kind: string,
  now: number,
  durationMs?: number,
): QueueThroughputWindow {
  const prevKindCount = window.completedByKind[kind] ?? 0;
  const nextCount = window.completedCount + 1;
  const nextKindCount = prevKindCount + 1;
  let avgDurationMs = window.avgDurationMs;
  let avgDurationMsByKind = window.avgDurationMsByKind;

  if (durationMs != null && durationMs >= MIN_QUEUE_ELAPSED_MS) {
    avgDurationMs = updateRunningAvgMs(window.avgDurationMs, window.completedCount, durationMs);
    avgDurationMsByKind = {
      ...window.avgDurationMsByKind,
      [kind]: updateRunningAvgMs(
        window.avgDurationMsByKind[kind] ?? null,
        prevKindCount,
        durationMs,
      ),
    };
  }

  return {
    startedAt: window.startedAt ?? now,
    completedCount: nextCount,
    completedByKind: {
      ...window.completedByKind,
      [kind]: nextKindCount,
    },
    kindStartedAt: {
      ...window.kindStartedAt,
      [kind]: window.kindStartedAt[kind] ?? now,
    },
    avgDurationMs,
    avgDurationMsByKind,
  };
}
