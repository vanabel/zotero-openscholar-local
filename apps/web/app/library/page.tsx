"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiGet, apiPost, API_BASE } from "@/lib/api";

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
  sha256: string;
  deleted: number;
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
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [batchBusy, setBatchBusy] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [previewDoc, setPreviewDoc] = useState<DocumentPreview | null>(null);
  const [previewChunks, setPreviewChunks] = useState<ChunkPreviewRow[]>([]);
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
      const qs = new URLSearchParams({ limit: "5000" });
      if (searchQ) qs.set("q", searchQ);
      const data = await apiGet<PapersResponse>(`/papers?${qs.toString()}`);
      setItems(data.items);
      setTotal(data.total);
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
  }, [searchQ]);

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
    try {
      const [doc, chunks] = await Promise.all([
        apiGet<DocumentPreview>(`/papers/${encodeURIComponent(id)}/document?max_chars=8000`),
        apiGet<{ items: ChunkPreviewRow[] }>(`/papers/${encodeURIComponent(id)}/chunks?limit=12`),
      ]);
      setPreviewDoc(doc);
      setPreviewChunks(chunks.items ?? []);
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

  async function indexSelected(force: boolean) {
    const ids = [...selected];
    if (ids.length === 0) {
      setMsg("请先勾选要索引的文献。");
      return;
    }
    setBatchBusy(true);
    setMsg(`提交批量索引（${ids.length} 篇）…`);
    try {
      const res = await apiPost<{
        queued?: number;
        failed?: number;
        tasks?: { task_id?: string; paper_id?: string; error?: string; deduped?: boolean }[];
      }>("/papers/index-batch", { paper_ids: ids, force });
      const errs = (res.tasks ?? []).filter((t) => t.error);
      const errHint =
        errs.length > 0
          ? `；无法入队 ${errs.length} 篇：${errs
              .slice(0, 2)
              .map((f) => f.error ?? "")
              .join("；")}`
          : "";
      setTaskPolling(true);
      setMsg(`已提交 ${res.queued ?? ids.length} 篇到后台队列，请查看各文献索引状态${errHint}。`);
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
        <strong className="ml-1">批量：</strong>勾选后点「批量 MinerU 索引」；单篇可在卡片底部操作。
      </p>
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
              搜索「{searchQ}」：显示 {items.length} / 共 {total} 篇
            </>
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
                        <button
                          type="button"
                          onClick={() => {
                            if (expanded) {
                              setExpandedId(null);
                              setPreviewDoc(null);
                              setPreviewChunks([]);
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
                            <p className="text-xs text-ink-600">加载 document.md / chunks…</p>
                          ) : previewDoc ? (
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
              {searchQ ? `没有匹配「${searchQ}」的文献。` : "暂无文献。请先确认 Zotero 路径，然后点击「扫描磁盘」。"}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
