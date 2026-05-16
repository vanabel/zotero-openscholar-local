"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import MarkdownKaTeX from "@/components/MarkdownKaTeX";
import {
  apiGet,
  apiPost,
  downloadReviewDocx,
  downloadReviewMarkdown,
  reviewStream,
  type ClaimRecord,
  type ReviewStreamEvent,
  type ReviewTemplate,
  type RetrievalScopeBody,
  type VerificationStatus,
} from "@/lib/api";

type Citation = {
  ref: number;
  chunk_id: string;
  paper_id: string;
  title?: string | null;
  section_path?: string | null;
  preview?: string;
  verification_status?: VerificationStatus | string;
};

function parseScopeList(raw: string): string[] | undefined {
  const items = raw
    .split(/[,，;；]/)
    .map((s) => s.trim())
    .filter(Boolean);
  return items.length ? items : undefined;
}

function verificationLabel(status?: string): { text: string; className: string } {
  switch (status) {
    case "verified":
      return { text: "已核验", className: "bg-emerald-100 text-emerald-800" };
    case "insufficient":
      return { text: "证据不足", className: "bg-amber-100 text-amber-900" };
    default:
      return { text: "未使用", className: "bg-mist-100 text-ink-600" };
  }
}

type RecentItem = {
  topic: string;
  focus: string;
  lang: string;
  has_cache: boolean;
  created_at: string;
};

type CachedReviewPayload = {
  review: string;
  citations: Citation[];
  cached?: boolean;
};

export default function ReviewPage() {
  const [topic, setTopic] = useState("");
  const [focus, setFocus] = useState("");
  const [lang, setLang] = useState<"zh" | "en">("zh");
  const [template, setTemplate] = useState<ReviewTemplate>("literature_review");
  const [review, setReview] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [busy, setBusy] = useState(false);
  const [useStream, setUseStream] = useState(true);
  const [recentItems, setRecentItems] = useState<RecentItem[]>([]);
  const [hint, setHint] = useState<string | null>(null);
  const [tagsFilter, setTagsFilter] = useState("");
  const [collectionsFilter, setCollectionsFilter] = useState("");
  const [yearsMin, setYearsMin] = useState("");
  const [yearsMax, setYearsMax] = useState("");
  const [claims, setClaims] = useState<ClaimRecord[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  function scopeBody(): RetrievalScopeBody {
    return {
      tags: parseScopeList(tagsFilter),
      collections: parseScopeList(collectionsFilter),
      years_min: yearsMin ? Number(yearsMin) : undefined,
      years_max: yearsMax ? Number(yearsMax) : undefined,
    };
  }

  const loadRecent = useCallback(async () => {
    try {
      const data = await apiGet<{ items: RecentItem[]; cache_enabled: boolean }>(
        `/review/recent?lang=${lang}&limit=10`,
      );
      setRecentItems(data.cache_enabled ? data.items : []);
    } catch {
      setRecentItems([]);
    }
  }, [lang]);

  useEffect(() => {
    void loadRecent();
  }, [loadRecent]);

  function applyCachedPayload(payload: CachedReviewPayload) {
    setReview(payload.review ?? "");
    setCitations((payload.citations ?? []) as Citation[]);
  }

  async function pickRecent(item: RecentItem) {
    abortRef.current?.abort();
    setTopic(item.topic);
    setFocus(item.focus || "");
    setHint(null);
    if (!item.has_cache) {
      setHint("已填入主题，点击「生成综述」撰写。");
      return;
    }
    setBusy(true);
    setReview("");
    setCitations([]);
    try {
      const qs = new URLSearchParams({
        topic: item.topic,
        lang: item.lang,
        focus: item.focus || "",
      });
      const hit = await apiGet<CachedReviewPayload>(`/review/cache?${qs.toString()}`);
      applyCachedPayload(hit);
      setHint("已从缓存载入（索引与模型配置未变）。");
    } catch {
      setHint("已填入主题；缓存已失效，请点击「生成综述」重新撰写。");
    } finally {
      setBusy(false);
    }
  }

  async function exportMd() {
    if (!topic.trim()) return;
    setBusy(true);
    setHint(null);
    try {
      const { blob, filename } = await downloadReviewMarkdown({
        topic,
        focus: focus || null,
        lang,
        template,
        use_cache: true,
        ...scopeBody(),
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      setHint("已下载 Markdown 文件。");
    } catch (e) {
      setHint(e instanceof Error ? e.message : "导出失败");
    } finally {
      setBusy(false);
    }
  }

  async function exportDocx() {
    if (!topic.trim()) return;
    setBusy(true);
    setHint(null);
    try {
      const { blob, filename } = await downloadReviewDocx({
        topic,
        focus: focus || null,
        lang,
        template,
        use_cache: true,
        ...scopeBody(),
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      setHint("已下载 DOCX 文件。");
    } catch (e) {
      setHint(e instanceof Error ? e.message : "DOCX 导出失败");
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    if (!topic.trim()) return;
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setBusy(true);
    setReview("");
    setCitations([]);
    setClaims([]);
    setHint(null);

    try {
      if (useStream) {
        await reviewStream(
          { topic, focus: focus || null, lang, template, use_cache: true, ...scopeBody() },
          (ev: ReviewStreamEvent) => {
            if (ev.type === "citations") {
              setCitations((ev.citations ?? []) as Citation[]);
            } else if (ev.type === "claims") {
              setClaims(ev.claims ?? []);
            } else if (ev.type === "token") {
              setReview((prev) => prev + (ev.t ?? ""));
            } else if (ev.type === "error") {
              setReview(ev.message ?? "错误");
            }
          },
          ac.signal,
        );
      } else {
        const res = await apiPost<{ review: string; citations: Citation[]; claims?: ClaimRecord[] }>(
          "/review",
          {
            topic,
            focus: focus || null,
            lang,
            template,
            use_cache: true,
            ...scopeBody(),
          },
        );
        setReview(res.review);
        setCitations(res.citations ?? []);
        setClaims(res.claims ?? []);
      }
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setReview(e instanceof Error ? e.message : "请求失败");
    } finally {
      setBusy(false);
      abortRef.current = null;
      void loadRecent();
    }
  }

  return (
    <div className="space-y-4 max-w-3xl">
      <h1 className="text-xl font-semibold text-ink-950">文献综述</h1>
      <p className="text-sm text-ink-700">
        基于本地索引的多篇片段自动检索，生成结构化综述草稿，并附带引用编号。支持<strong>流式输出</strong>与
        <strong>问答同款缓存</strong>（<code className="text-[11px]">CHAT_CACHE_ENABLED</code>）。
      </p>
      <p className="text-xs text-ink-500">
        综述提示与引用方式对齐{" "}
        <a
          href="https://arxiv.org/abs/2411.14199"
          className="text-accent underline underline-offset-2"
          rel="noreferrer"
          target="_blank"
        >
          OpenScholar
        </a>{" "}
        式证据链；语料为您的 Zotero PDF。
      </p>
      <div className="flex flex-wrap items-center gap-4 text-sm text-ink-800">
        <label className="inline-flex cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            checked={useStream}
            onChange={(e) => setUseStream(e.target.checked)}
            className="rounded border-mist-300"
          />
          流式输出（SSE）
        </label>
        <label className="inline-flex items-center gap-2">
          <span className="text-ink-600">综述语言</span>
          <select
            value={lang}
            onChange={(e) => setLang(e.target.value as "zh" | "en")}
            className="rounded-md border border-mist-200 bg-white px-2 py-1 text-sm"
          >
            <option value="zh">中文</option>
            <option value="en">English</option>
          </select>
        </label>
        <label className="inline-flex items-center gap-2">
          <span className="text-ink-600">模板</span>
          <select
            value={template}
            onChange={(e) => setTemplate(e.target.value as ReviewTemplate)}
            className="rounded-md border border-mist-200 bg-white px-2 py-1 text-sm"
          >
            <option value="literature_review">结构化综述</option>
            <option value="grant_proposal">项目申请书 · 研究现状</option>
          </select>
        </label>
      </div>
      {recentItems.length > 0 && (
        <div className="rounded-xl border border-mist-200 bg-mist-50 p-3">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-ink-500">最近主题（随机）</span>
            <button
              type="button"
              className="text-xs text-accent hover:underline"
              onClick={() => void loadRecent()}
            >
              换一批
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {recentItems.map((item) => (
              <button
                key={`${item.created_at}-${item.topic.slice(0, 24)}`}
                type="button"
                disabled={busy}
                title={item.focus ? `${item.topic}\n${item.focus}` : item.topic}
                onClick={() => void pickRecent(item)}
                className="max-w-full rounded-lg border border-mist-200 bg-white px-2.5 py-1.5 text-left text-xs text-ink-800 hover:border-accent hover:bg-accent-soft disabled:opacity-50"
              >
                <span className="line-clamp-2">{item.topic}</span>
                {item.focus ? (
                  <span className="mt-0.5 block line-clamp-1 text-[10px] text-ink-500">{item.focus}</span>
                ) : null}
                <span className="mt-0.5 block text-[10px] text-ink-500">
                  {item.has_cache ? "点击载入缓存" : "点击填入"}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
      <input
        className="w-full rounded-xl border border-mist-200 bg-white p-3 text-sm shadow-inner outline-none focus:border-accent"
        placeholder="综述主题，例如：分数阶微分方程数值方法进展"
        value={topic}
        onChange={(e) => setTopic(e.target.value)}
      />
      <textarea
        className="min-h-[90px] w-full rounded-xl border border-mist-200 bg-white p-3 text-sm shadow-inner outline-none focus:border-accent"
        placeholder="可选：重点问题、时间范围、方法偏好等"
        value={focus}
        onChange={(e) => setFocus(e.target.value)}
      />
      <div className="grid gap-2 rounded-xl border border-mist-200 bg-mist-50 p-3 text-sm">
        <span className="text-xs font-semibold uppercase tracking-wide text-ink-500">检索范围（可选）</span>
        <input
          className="w-full rounded-md border border-mist-200 bg-white px-2 py-1.5 text-sm"
          placeholder="Zotero 标签，逗号分隔"
          value={tagsFilter}
          onChange={(e) => setTagsFilter(e.target.value)}
        />
        <input
          className="w-full rounded-md border border-mist-200 bg-white px-2 py-1.5 text-sm"
          placeholder="Zotero 集合名，逗号分隔"
          value={collectionsFilter}
          onChange={(e) => setCollectionsFilter(e.target.value)}
        />
        <div className="flex flex-wrap gap-2">
          <input
            className="w-28 rounded-md border border-mist-200 bg-white px-2 py-1.5 text-sm"
            placeholder="年份 ≥"
            value={yearsMin}
            onChange={(e) => setYearsMin(e.target.value)}
            inputMode="numeric"
          />
          <input
            className="w-28 rounded-md border border-mist-200 bg-white px-2 py-1.5 text-sm"
            placeholder="年份 ≤"
            value={yearsMax}
            onChange={(e) => setYearsMax(e.target.value)}
            inputMode="numeric"
          />
        </div>
      </div>
      {hint && <p className="text-xs text-ink-600">{hint}</p>}
      <button
        type="button"
        disabled={busy}
        onClick={() => void submit()}
        className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
      >
        {busy ? "撰写中…" : "生成综述"}
      </button>
      <button
        type="button"
        disabled={busy || !topic.trim()}
        onClick={() => void exportMd()}
        className="ml-2 rounded-lg border border-mist-200 px-4 py-2 text-sm text-ink-800 hover:bg-mist-50 disabled:opacity-50"
      >
        导出 Markdown
      </button>
      <button
        type="button"
        disabled={busy || !topic.trim()}
        onClick={() => void exportDocx()}
        className="ml-2 rounded-lg border border-mist-200 px-4 py-2 text-sm text-ink-800 hover:bg-mist-50 disabled:opacity-50"
      >
        导出 DOCX
      </button>
      {review && (
        <section className="rounded-xl border border-mist-200 bg-white p-4 text-sm leading-relaxed text-ink-900">
          <MarkdownKaTeX content={review} />
        </section>
      )}
      {citations.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-ink-950">参考文献线索</h2>
          <div className="grid gap-2">
            {citations.map((c) => (
              <div key={c.chunk_id} className="rounded-lg border border-mist-200 bg-white p-3 text-xs text-ink-800">
                <div className="font-semibold text-ink-950">
                  [{c.ref}] {c.title || c.paper_id}
                </div>
                {c.preview && <div className="mt-2 text-ink-700">{c.preview}</div>}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
