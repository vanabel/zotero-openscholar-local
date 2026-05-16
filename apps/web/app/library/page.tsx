"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiGet, apiPost, API_BASE } from "@/lib/api";

const LOW_QUALITY_THRESHOLD = 0.65;

type Paper = {
  id: string;
  zotero_key?: string | null;
  title: string | null;
  authors?: string | null;
  year?: number | null;
  venue?: string | null;
  doi?: string | null;
  zotero_tags?: string | null;
  zotero_collections?: string | null;
  pdf_path: string;
  file_name?: string | null;
  parse_status: string;
  index_status: string;
  status_message?: string | null;
  parse_quality_score?: number | null;
  sha256: string;
  deleted: number;
};

type QualityFilter = "all" | "low" | "unscored" | "high";
type SortMode = "updated" | "quality_asc" | "quality_desc";

type ParseReport = {
  parse_quality_score?: number | null;
  text_length?: number | null;
  page_count?: number | null;
  detected_sections?: number | null;
  formula_blocks?: number | null;
  table_blocks?: number | null;
  image_blocks?: number | null;
  ocr_ratio?: number | null;
  suspicious_garbled_ratio?: number | null;
  references_detected?: number | boolean | null;
  warnings?: string[];
  parser?: string | null;
  parser_mode?: string | null;
  created_at?: string | null;
};

type QualitySummary = {
  total: number;
  unscored: number;
  low_quality: number;
  high_quality: number;
  low_quality_threshold: number;
};

type DocumentPreview = {
  markdown: string;
  chars: number;
  truncated: boolean;
};

type ChunkPreviewRow = {
  id: string;
  section_path?: string | null;
  chunk_index: number;
  text_preview?: string | null;
};

type PapersResponse = {
  items: Paper[];
  total: number;
  q: string | null;
};

const WARNING_LABELS: Record<string, string> = {
  markdown_too_short: "Markdown 过短",
  high_garbled_ratio: "乱码比例偏高",
  high_ocr_fragment_ratio: "OCR 碎片偏多",
  few_sections: "章节结构过少",
};

function formatQualityScore(score: number | null | undefined): string {
  if (score == null || Number.isNaN(score)) return "未评分";
  return `${Math.round(score * 100)}%`;
}

function qualityTone(score: number | null | undefined): {
  label: string;
  className: string;
} {
  if (score == null || Number.isNaN(score)) {
    return { label: "未评分", className: "bg-mist-100 text-ink-600" };
  }
  if (score >= 0.85) return { label: formatQualityScore(score), className: "bg-emerald-50 text-emerald-800" };
  if (score >= LOW_QUALITY_THRESHOLD) {
    return { label: formatQualityScore(score), className: "bg-amber-50 text-amber-900" };
  }
  return { label: formatQualityScore(score), className: "bg-red-50 text-red-800" };
}

function ParseQualityBadge({ score }: { score: number | null | undefined }) {
  const tone = qualityTone(score);
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${tone.className}`}
      title="解析质量分（索引后由 MinerU Markdown 统计）"
    >
      质量 {tone.label}
    </span>
  );
}

function warningLabel(code: string): string {
  return WARNING_LABELS[code] ?? code;
}

function parseJsonStringList(raw: string | null | undefined): string[] {
  if (!raw || !String(raw).trim()) return [];
  try {
    const v = JSON.parse(String(raw)) as unknown;
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function doiHref(doi: string): string {
  const d = doi.trim();
  if (!d) return "#";
  const clean = d.replace(/^https?:\/\/(dx\.)?doi\.org\//i, "");
  return `https://doi.org/${encodeURIComponent(clean)}`;
}

function PaperMetaLines({ p }: { p: Paper }) {
  const tags = parseJsonStringList(p.zotero_tags);
  const cols = parseJsonStringList(p.zotero_collections);
  const bits: string[] = [];
  if (p.authors?.trim()) bits.push(p.authors.trim());
  if (p.year != null && p.year > 0) bits.push(String(p.year));
  if (p.venue?.trim()) bits.push(p.venue.trim());
  const metaLine = bits.join(" · ");

  return (
    <div className="mt-1.5 space-y-1.5 text-xs text-ink-600 leading-relaxed">
      {metaLine ? <p className="line-clamp-2">{metaLine}</p> : null}
      {p.doi?.trim() ? (
        <p>
          <span className="text-ink-500">DOI </span>
          <a
            href={doiHref(p.doi)}
            target="_blank"
            rel="noreferrer"
            className="text-accent underline underline-offset-2 break-all hover:opacity-90"
          >
            {p.doi.trim()}
          </a>
        </p>
      ) : null}
      {tags.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          <span className="text-ink-500 shrink-0">标签</span>
          {tags.map((t) => (
            <span key={t} className="rounded bg-mist-100 px-1.5 py-0.5 text-ink-800">
              {t}
            </span>
          ))}
        </div>
      ) : null}
      {cols.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          <span className="text-ink-500 shrink-0">集合</span>
          {cols.map((c) => (
            <span key={c} className="rounded border border-mist-200 px-1.5 py-0.5 text-ink-700">
              {c}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

type IndexTaskRow = {
  id: string;
  paper_id?: string | null;
  status: string;
  progress?: { phase?: string; done?: number; total?: number; message?: string } | null;
  error?: string | null;
};

function StatusBadge({ label, value, hint }: { label: string; value: string; hint?: string }) {
  const ok = value === "parsed" || value === "indexed";
  const indexing = value === "indexing";
  const failed = value === "failed";
  const cls = ok
    ? "bg-emerald-50 text-emerald-800"
    : failed
      ? "bg-red-50 text-red-800"
      : indexing
        ? "bg-sky-50 text-sky-900"
        : "bg-amber-50 text-amber-900";
  return (
    <span className={`inline-flex flex-wrap items-center gap-1 rounded-md px-2 py-0.5 text-xs ${cls}`}>
      <span>
        {label}: {value}
      </span>
      {hint ? <span className="text-[11px] opacity-90">({hint})</span> : null}
    </span>
  );
}

export default function LibraryPage() {
  const [items, setItems] = useState<Paper[]>([]);
  const [total, setTotal] = useState(0);
  const [searchInput, setSearchInput] = useState("");
  const [searchQ, setSearchQ] = useState("");
  const [qualityFilter, setQualityFilter] = useState<QualityFilter>("all");
  const [sortMode, setSortMode] = useState<SortMode>("updated");
  const [qualitySummary, setQualitySummary] = useState<QualitySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [batchBusy, setBatchBusy] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [previewDoc, setPreviewDoc] = useState<DocumentPreview | null>(null);
  const [previewChunks, setPreviewChunks] = useState<ChunkPreviewRow[]>([]);
  const [previewReport, setPreviewReport] = useState<ParseReport | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [paperTasks, setPaperTasks] = useState<Map<string, IndexTaskRow>>(new Map());
  const [taskPolling, setTaskPolling] = useState(false);

  useEffect(() => {
    const t = window.setTimeout(() => setSearchQ(searchInput.trim()), 300);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ limit: "5000", sort: sortMode });
      if (searchQ) qs.set("q", searchQ);
      if (qualityFilter === "low") qs.set("parse_quality_lte", String(LOW_QUALITY_THRESHOLD));
      else if (qualityFilter === "unscored") qs.set("parse_quality_missing", "true");
      else if (qualityFilter === "high") qs.set("parse_quality_gte", "0.85");
      const [data, summary] = await Promise.all([
        apiGet<PapersResponse>(`/papers?${qs.toString()}`),
        apiGet<QualitySummary>("/papers/quality-summary"),
      ]);
      setItems(data.items);
      setTotal(data.total);
      setQualitySummary(summary);
      setSelected((prev) => {
        const ids = new Set(data.items.map((p) => p.id));
        const next = new Set<string>();
        for (const id of prev) {
          if (ids.has(id)) next.add(id);
        }
        return next;
      });
      setMsg(null);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [searchQ, qualityFilter, sortMode]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const syncActiveTasks = useCallback(async () => {
    try {
      const data = await apiGet<{ items: IndexTaskRow[] }>("/tasks/active");
      const m = new Map<string, IndexTaskRow>();
      let anyActive = false;
      for (const t of data.items) {
        const pid = t.paper_id;
        if (pid) m.set(pid, t);
        if (t.status === "queued" || t.status === "running") anyActive = true;
      }
      setPaperTasks(m);
      if (!anyActive) {
        setTaskPolling(false);
        await refresh();
      }
      return anyActive;
    } catch {
      return false;
    }
  }, [refresh]);

  useEffect(() => {
    void syncActiveTasks().then((active) => {
      if (active) setTaskPolling(true);
    });
  }, [syncActiveTasks]);

  useEffect(() => {
    if (!taskPolling) return;
    const iv = window.setInterval(() => void syncActiveTasks(), 1500);
    return () => window.clearInterval(iv);
  }, [taskPolling, syncActiveTasks]);

  const allSelected = useMemo(
    () => items.length > 0 && items.every((p) => selected.has(p.id)),
    [items, selected],
  );

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(items.map((p) => p.id)));
    }
  }

  async function scan() {
    setMsg("扫描中…");
    try {
      const res = await apiPost<Record<string, unknown>>("/scan", {});
      const skip = Number(res.skipped_non_file ?? 0);
      const skipMsg = skip > 0 ? `（已跳过 ${skip} 个名为 .pdf 的非常规路径/目录）` : "";
      const zm = res.zotero_metadata as { skipped?: string; updated?: number; unmatched?: number } | undefined;
      let zmsg = "";
      if (zm && typeof zm.updated === "number" && !zm.skipped) {
        zmsg = ` Zotero 题录已更新 ${zm.updated} 条（未匹配 ${zm.unmatched ?? 0}）。`;
      } else if (zm?.skipped) {
        zmsg = `（题录：${zm.skipped}）`;
      }
      setMsg(`扫描完成：发现 ${String(res.found ?? 0)} 个 PDF${skipMsg}。${zmsg}`);
      await refresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "扫描失败");
    }
  }

  async function loadPreview(id: string) {
    setPreviewLoading(true);
    setPreviewDoc(null);
    setPreviewChunks([]);
    setPreviewReport(null);
    try {
      const [doc, chunks, report] = await Promise.all([
        apiGet<DocumentPreview>(`/papers/${encodeURIComponent(id)}/document?max_chars=8000`),
        apiGet<{ items: ChunkPreviewRow[] }>(`/papers/${encodeURIComponent(id)}/chunks?limit=12`),
        apiGet<ParseReport>(`/papers/${encodeURIComponent(id)}/parse-report`).catch(() => null),
      ]);
      setPreviewDoc(doc);
      setPreviewChunks(chunks.items ?? []);
      setPreviewReport(report);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "预览加载失败");
    } finally {
      setPreviewLoading(false);
    }
  }

  async function indexPaper(id: string, force: boolean, reindexOnly = false) {
    setMsg(`提交索引 ${id.slice(0, 8)}…`);
    try {
      const res = await apiPost<{
        task_id?: string;
        status?: string;
        deduped?: boolean;
        error?: string;
      }>(
        reindexOnly
          ? `/papers/${id}/reindex-only`
          : `/papers/${id}/index?force=${force}`,
        {},
      );
      setTaskPolling(true);
      setMsg(
        res.deduped
          ? `该文献已在索引队列中（task ${res.task_id?.slice(0, 8) ?? ""}）。`
          : `已加入后台索引队列，可在下方状态栏查看进度。`,
      );
      await syncActiveTasks();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "提交索引失败");
    }
  }

  async function syncZoteroMeta() {
    setMsg("正在从 zotero.sqlite 同步题录…");
    try {
      const res = await apiPost<{
        ok?: boolean;
        skipped?: string;
        updated?: number;
        unmatched?: number;
        errors?: number;
        error?: string;
      }>("/papers/sync-zotero-metadata", {});
      if (res.skipped) {
        setMsg(`未同步：${res.skipped}`);
      } else if (res.error) {
        setMsg(`同步失败：${res.error}`);
      } else {
        setMsg(
          `题录同步完成：已更新 ${String(res.updated ?? 0)} 条，未匹配 ${String(res.unmatched ?? 0)}，错误 ${String(res.errors ?? 0)}。`,
        );
      }
      await refresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "同步失败");
    }
  }

  const INDEX_BATCH_CHUNK = 500;

  async function enqueueMissing(
    path: "/papers/index-missing" | "/papers/parse-missing" | "/papers/summarize-missing",
    label: string,
  ) {
    setBatchBusy(true);
    setMsg(`正在提交：${label}…`);
    try {
      const res = await apiPost<{
        matched?: number;
        queued?: number;
        failed?: number;
      }>(path, {});
      setTaskPolling(path !== "/papers/summarize-missing");
      setMsg(
        `${label}：匹配 ${res.matched ?? 0} 篇，已入队 ${res.queued ?? 0} 篇` +
          (res.failed ? `，失败 ${res.failed} 篇` : "") +
          "。",
      );
      await syncActiveTasks();
      await refresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : `${label}失败`);
    } finally {
      setBatchBusy(false);
    }
  }

  async function indexSelected(force: boolean) {
    const ids = [...selected];
    if (ids.length === 0) {
      setMsg("请先勾选要索引的文献。");
      return;
    }
    setBatchBusy(true);
    let totalQueued = 0;
    let totalFailed = 0;
    const errSamples: string[] = [];
    try {
      for (let i = 0; i < ids.length; i += INDEX_BATCH_CHUNK) {
        const chunk = ids.slice(i, i + INDEX_BATCH_CHUNK);
        const from = i + 1;
        const to = i + chunk.length;
        setMsg(
          ids.length > INDEX_BATCH_CHUNK
            ? `提交批量索引（共 ${ids.length} 篇，第 ${from}–${to} 篇）…`
            : `提交批量索引（${ids.length} 篇）…`,
        );
        const res = await apiPost<{
          queued?: number;
          failed?: number;
          tasks?: { task_id?: string; paper_id?: string; error?: string; deduped?: boolean }[];
        }>("/papers/index-batch", { paper_ids: chunk, force });
        totalQueued += res.queued ?? 0;
        totalFailed += res.failed ?? 0;
        for (const t of res.tasks ?? []) {
          if (t.error && errSamples.length < 3) {
            errSamples.push(t.error);
          }
        }
      }
      const errHint =
        totalFailed > 0
          ? `；无法入队 ${totalFailed} 篇${errSamples.length > 0 ? `：${errSamples.join("；")}` : ""}`
          : "";
      setTaskPolling(true);
      setMsg(`已提交 ${totalQueued} 篇到后台队列，请查看各文献索引状态${errHint}。`);
      setSelected(new Set());
      await syncActiveTasks();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "批量提交失败");
    } finally {
      setBatchBusy(false);
    }
  }

  return (
    <div className="space-y-4 max-w-4xl">
      <p className="text-sm text-ink-700 leading-relaxed">
        <strong>检索：</strong>按标题、文件名、路径、作者、标签或集合过滤。
        <strong className="ml-1">质量：</strong>索引后可看解析质量分；可筛低质量（&lt;
        {Math.round(LOW_QUALITY_THRESHOLD * 100)}%）或未评分文献。
        <strong className="ml-1">批量：</strong>勾选后点「批量 MinerU 索引」。
      </p>
      {qualitySummary && !loading && (
        <div className="flex flex-wrap gap-2 text-xs text-ink-700">
          <span className="rounded-md bg-mist-100 px-2 py-1">全库 {qualitySummary.total} 篇</span>
          <span className="rounded-md bg-red-50 px-2 py-1 text-red-900">
            低质量 {qualitySummary.low_quality} 篇
          </span>
          <span className="rounded-md bg-mist-100 px-2 py-1">未评分 {qualitySummary.unscored} 篇</span>
          <span className="rounded-md bg-emerald-50 px-2 py-1 text-emerald-800">
            高质量 {qualitySummary.high_quality} 篇
          </span>
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-ink-950">文献库</h1>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void scan()}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white hover:opacity-90"
          >
            扫描磁盘
          </button>
          <button
            type="button"
            onClick={() => void syncZoteroMeta()}
            className="rounded-lg border border-mist-200 px-3 py-2 text-sm hover:bg-mist-100"
          >
            同步 Zotero 题录
          </button>
          <button
            type="button"
            onClick={() => void refresh()}
            className="rounded-lg border border-mist-200 px-3 py-2 text-sm hover:bg-mist-100"
          >
            刷新
          </button>
          <button
            type="button"
            disabled={batchBusy}
            onClick={() => void enqueueMissing("/papers/index-missing", "索引未建立")}
            className="rounded-lg border border-mist-200 px-3 py-2 text-sm hover:bg-mist-50 disabled:opacity-50"
            title="为 index_status 非 indexed 的文献批量入队"
          >
            索引未建立
          </button>
          <button
            type="button"
            disabled={batchBusy}
            onClick={() => void enqueueMissing("/papers/parse-missing", "解析缺失")}
            className="rounded-lg border border-mist-200 px-3 py-2 text-sm hover:bg-mist-50 disabled:opacity-50"
            title="为尚无 document.md 的文献批量入队解析"
          >
            解析缺失
          </button>
          <button
            type="button"
            disabled={batchBusy}
            onClick={() => void enqueueMissing("/papers/summarize-missing", "摘要缺失")}
            className="rounded-lg border border-mist-200 px-3 py-2 text-sm hover:bg-mist-50 disabled:opacity-50"
            title="为已索引但无 paper_summary 的文献生成摘要"
          >
            摘要缺失
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <label className="block">
          <span className="text-xs font-semibold uppercase text-ink-500">搜索文献</span>
          <input
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="标题、作者、文件名或路径关键词…"
            className="mt-1 w-full rounded-lg border border-mist-200 px-3 py-2 text-sm"
          />
        </label>
        <div className="flex flex-wrap gap-3">
          <label className="block min-w-[10rem] flex-1">
            <span className="text-xs font-semibold uppercase text-ink-500">解析质量</span>
            <select
              value={qualityFilter}
              onChange={(e) => setQualityFilter(e.target.value as QualityFilter)}
              className="mt-1 w-full rounded-lg border border-mist-200 bg-white px-3 py-2 text-sm"
            >
              <option value="all">全部</option>
              <option value="low">仅低质量（&lt; {Math.round(LOW_QUALITY_THRESHOLD * 100)}%）</option>
              <option value="unscored">仅未评分</option>
              <option value="high">高质量（≥ 85%）</option>
            </select>
          </label>
          <label className="block min-w-[10rem] flex-1">
            <span className="text-xs font-semibold uppercase text-ink-500">排序</span>
            <select
              value={sortMode}
              onChange={(e) => setSortMode(e.target.value as SortMode)}
              className="mt-1 w-full rounded-lg border border-mist-200 bg-white px-3 py-2 text-sm"
            >
              <option value="updated">最近更新</option>
              <option value="quality_asc">质量分从低到高</option>
              <option value="quality_desc">质量分从高到低</option>
            </select>
          </label>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={batchBusy || selected.size === 0}
            onClick={() => void indexSelected(false)}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            批量 MinerU 索引{selected.size > 0 ? `（${selected.size}）` : ""}
          </button>
          <button
            type="button"
            disabled={batchBusy || selected.size === 0}
            onClick={() => void indexSelected(true)}
            className="rounded-lg border border-mist-200 px-3 py-2 text-sm hover:bg-mist-50 disabled:opacity-50"
          >
            批量强制重建
          </button>
        </div>
      </div>

      {!loading && (
        <p className="text-xs text-ink-600">
          {searchQ ? (
            <>
              搜索「{searchQ}」：显示 {items.length} / 匹配 {total} 篇
            </>
          ) : qualityFilter === "low" ? (
            <>低质量文献：{total} 篇</>
          ) : qualityFilter === "unscored" ? (
            <>未评分解析质量：{total} 篇</>
          ) : qualityFilter === "high" ? (
            <>高质量文献：{total} 篇</>
          ) : (
            <>共 {total} 篇文献</>
          )}
          {selected.size > 0 && <> · 已选 {selected.size} 篇</>}
        </p>
      )}

      {msg && <div className="rounded-lg border border-mist-200 bg-white px-3 py-2 text-sm text-ink-800">{msg}</div>}

      {loading ? (
        <p className="text-sm text-ink-600">加载中…</p>
      ) : (
        <div className="rounded-xl border border-mist-200 bg-white shadow-sm overflow-hidden">
          {items.length > 0 && (
            <div className="flex items-center gap-3 border-b border-mist-200 bg-mist-50 px-4 py-2.5">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={toggleAll}
                aria-label="全选当前列表"
                className="rounded border-mist-300"
              />
              <span className="text-xs font-medium text-ink-600">全选当前列表</span>
            </div>
          )}

          <ul className="divide-y divide-mist-200">
            {items.map((p) => {
              const displayTitle = p.title || p.pdf_path.split("/").pop() || "未命名";
              const expanded = expandedId === p.id;
              const task = paperTasks.get(p.id);
              const indexHint =
                task?.progress?.message ||
                (task?.status === "queued" ? "排队中" : task?.status === "running" ? "处理中" : undefined);
              const indexValue =
                p.index_status === "indexing" || task?.status === "queued" || task?.status === "running"
                  ? "indexing"
                  : p.index_status;
              const failMsg =
                (p.status_message && p.status_message.trim()) ||
                (task?.status === "failed" && task.error ? task.error : null);
              return (
                <li key={p.id} className="px-4 py-3">
                  <div className="flex gap-3">
                    <input
                      type="checkbox"
                      checked={selected.has(p.id)}
                      onChange={() => toggleOne(p.id)}
                      aria-label={`选择 ${displayTitle}`}
                      className="mt-1 shrink-0 rounded border-mist-300"
                    />
                    <div className="min-w-0 flex-1">
                      <h2 className="font-medium leading-snug break-words">
                        <a
                          href={`${API_BASE}/papers/${encodeURIComponent(p.id)}/pdf`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-ink-950 hover:text-accent underline-offset-2 hover:underline"
                        >
                          {displayTitle}
                        </a>
                      </h2>
                      <PaperMetaLines p={p} />
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        <StatusBadge label="解析" value={p.parse_status} />
                        <StatusBadge label="索引" value={indexValue} hint={indexHint} />
                        <ParseQualityBadge score={p.parse_quality_score} />
                        <button
                          type="button"
                          onClick={() => {
                            if (expanded) {
                              setExpandedId(null);
                              setPreviewDoc(null);
                              setPreviewChunks([]);
                              setPreviewReport(null);
                            } else {
                              setExpandedId(p.id);
                              void loadPreview(p.id);
                            }
                          }}
                          className="text-xs text-ink-500 underline-offset-2 hover:text-ink-700 hover:underline"
                        >
                          {expanded ? "收起详情" : "预览 / 详情"}
                        </button>
                      </div>
                      {failMsg && (
                        <p className="mt-2 rounded-md border border-red-200 bg-red-50 px-2.5 py-2 text-xs text-red-900 leading-relaxed">
                          {failMsg}
                        </p>
                      )}
                      {expanded && (
                        <div className="mt-2 space-y-3">
                          <div className="space-y-1 rounded bg-mist-100 px-2 py-1.5 font-mono text-[11px] text-ink-700">
                          <div>
                            <span className="text-ink-500">paper_id </span>
                            {p.id}
                          </div>
                          {p.zotero_key ? (
                            <div>
                              <span className="text-ink-500">zotero_key </span>
                              {p.zotero_key}
                            </div>
                          ) : null}
                          </div>
                          {previewLoading ? (
                            <p className="text-xs text-ink-600">加载解析报告 / document.md / chunks…</p>
                          ) : previewReport ? (
                            <div className="rounded-lg border border-mist-200 bg-white p-3 text-xs text-ink-800">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="font-semibold text-ink-950">解析质量报告</span>
                                <ParseQualityBadge score={previewReport.parse_quality_score} />
                              </div>
                              <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] sm:grid-cols-3">
                                {previewReport.text_length != null && (
                                  <>
                                    <dt className="text-ink-500">正文长度</dt>
                                    <dd>{previewReport.text_length}</dd>
                                  </>
                                )}
                                {previewReport.detected_sections != null && (
                                  <>
                                    <dt className="text-ink-500">章节数</dt>
                                    <dd>{previewReport.detected_sections}</dd>
                                  </>
                                )}
                                {previewReport.formula_blocks != null && (
                                  <>
                                    <dt className="text-ink-500">公式块</dt>
                                    <dd>{previewReport.formula_blocks}</dd>
                                  </>
                                )}
                                {previewReport.table_blocks != null && (
                                  <>
                                    <dt className="text-ink-500">表格</dt>
                                    <dd>{previewReport.table_blocks}</dd>
                                  </>
                                )}
                                {previewReport.image_blocks != null && (
                                  <>
                                    <dt className="text-ink-500">图片</dt>
                                    <dd>{previewReport.image_blocks}</dd>
                                  </>
                                )}
                                {previewReport.ocr_ratio != null && (
                                  <>
                                    <dt className="text-ink-500">OCR 碎片比</dt>
                                    <dd>{(previewReport.ocr_ratio * 100).toFixed(1)}%</dd>
                                  </>
                                )}
                                {previewReport.suspicious_garbled_ratio != null && (
                                  <>
                                    <dt className="text-ink-500">乱码比</dt>
                                    <dd>{(previewReport.suspicious_garbled_ratio * 100).toFixed(2)}%</dd>
                                  </>
                                )}
                              </dl>
                              {(previewReport.warnings?.length ?? 0) > 0 && (
                                <ul className="mt-2 flex flex-wrap gap-1">
                                  {previewReport.warnings!.map((w) => (
                                    <li
                                      key={w}
                                      className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-900"
                                    >
                                      {warningLabel(w)}
                                    </li>
                                  ))}
                                </ul>
                              )}
                              {!previewReport.warnings?.length &&
                                (previewReport.parse_quality_score ?? 1) < LOW_QUALITY_THRESHOLD && (
                                  <p className="mt-2 text-[11px] text-red-800">
                                    质量分偏低，可尝试「强制重建」或检查 PDF 是否为扫描件。
                                  </p>
                                )}
                            </div>
                          ) : p.parse_status === "parsed" || p.index_status === "indexed" ? (
                            <p className="text-xs text-ink-600">
                              尚无解析质量报告；请执行「建立索引」或「强制重建」（需重新解析 PDF）。「仅重建索引」不会写入质量分。
                            </p>
                          ) : null}
                          {!previewLoading && previewDoc ? (
                            <div className="rounded-lg border border-mist-200 bg-mist-50 p-2">
                              <p className="text-[11px] font-medium text-ink-600">
                                document.md
                                {previewDoc.truncated
                                  ? `（前 8000 / ${previewDoc.chars} 字）`
                                  : `（${previewDoc.chars} 字）`}
                              </p>
                              <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap text-[11px] text-ink-800 leading-relaxed">
                                {previewDoc.markdown}
                              </pre>
                            </div>
                          ) : null}
                          {previewChunks.length > 0 && (
                            <ul className="space-y-1.5 text-[11px] text-ink-700">
                              {previewChunks.map((ch) => (
                                <li key={ch.id} className="rounded border border-mist-200 bg-white px-2 py-1.5">
                                  <span className="font-medium text-ink-900">
                                    #{ch.chunk_index} {ch.section_path || ch.id.slice(0, 10)}
                                  </span>
                                  {ch.text_preview ? (
                                    <p className="mt-0.5 line-clamp-3 text-ink-600">{ch.text_preview}</p>
                                  ) : null}
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      )}
                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          type="button"
                          className="rounded-md bg-accent-soft px-3 py-1.5 text-xs font-medium text-accent hover:opacity-90"
                          onClick={() => void indexPaper(p.id, false)}
                        >
                          建立索引
                        </button>
                        <button
                          type="button"
                          className="rounded-md border border-mist-200 px-3 py-1.5 text-xs text-ink-800 hover:bg-mist-50"
                          onClick={() => void indexPaper(p.id, false, true)}
                        >
                          仅重建索引
                        </button>
                        <button
                          type="button"
                          className="rounded-md border border-mist-200 px-3 py-1.5 text-xs text-ink-800 hover:bg-mist-50"
                          onClick={() => void indexPaper(p.id, true)}
                        >
                          强制重建
                        </button>
                        {(p.index_status === "failed" || p.parse_status === "failed") && (
                          <button
                            type="button"
                            className="rounded-md border border-red-200 px-3 py-1.5 text-xs text-red-800 hover:bg-red-50"
                            onClick={() => void indexPaper(p.id, false)}
                          >
                            重试索引
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>

          {items.length === 0 && (
            <p className="px-4 py-8 text-center text-sm text-ink-600">
              {searchQ
                ? `没有匹配「${searchQ}」的文献。`
                : qualityFilter === "low"
                  ? `当前没有质量分低于 ${Math.round(LOW_QUALITY_THRESHOLD * 100)}% 的文献。`
                  : qualityFilter === "unscored"
                    ? "所有文献均已有解析质量分。"
                    : qualityFilter === "high"
                      ? "暂无高质量（≥85%）文献。"
                      : "暂无文献。请先确认 Zotero 路径，然后点击「扫描磁盘」。"}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
