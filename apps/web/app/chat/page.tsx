"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import MarkdownKaTeX from "@/components/MarkdownKaTeX";
import {
  apiGet,
  apiPost,
  chatStream,
  translateStream,
  type BilingualLang,
  type BilingualStreamEvent,
  type ChatStreamEvent,
  type ClaimRecord,
  type RetrievalScopeBody,
  type VerificationStatus,
} from "@/lib/api";
import { formatCitationSource } from "@/lib/citationSource";

type Citation = {
  ref: number;
  chunk_id: string;
  paper_id: string;
  title?: string | null;
  section_path?: string | null;
  section_title?: string | null;
  page_start?: number | null;
  page_end?: number | null;
  source?: string | null;
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
    case "invalid_ref":
      return { text: "无效引用", className: "bg-red-100 text-red-800" };
    case "unreferenced":
      return { text: "未标注引用", className: "bg-mist-200 text-ink-700" };
    default:
      return { text: "未使用", className: "bg-mist-100 text-ink-600" };
  }
}

type RecentItem = {
  question: string;
  lang: BilingualLang;
  has_cache: boolean;
  created_at: string;
};

type CachedChatPayload = {
  answer: string;
  citations: Citation[];
  answer_other?: string;
  answer_other_lang?: BilingualLang;
  cached?: boolean;
};

function otherLang(lang: BilingualLang): BilingualLang {
  return lang === "zh" ? "en" : "zh";
}

function applyBilingualEvent(
  ev: BilingualStreamEvent,
  setAnswerOther: React.Dispatch<React.SetStateAction<{ lang: BilingualLang; text: string } | null>>,
  setTranslateTarget: (lang: BilingualLang) => void,
) {
  if (ev.type === "bilingual_start") {
    setTranslateTarget(ev.lang);
    setAnswerOther({ lang: ev.lang, text: "" });
  } else if (ev.type === "bilingual_token") {
    const piece = ev.t ?? "";
    if (!piece) return;
    setTranslateTarget(ev.lang);
    setAnswerOther((prev) => {
      if (prev?.lang !== ev.lang) return { lang: ev.lang, text: piece };
      const combined = prev.text + piece;
      // 若服务端误发累积全文，避免拼接重复
      if (piece.length > 8 && prev.text && combined.endsWith(piece) && prev.text.includes(piece.slice(0, 20))) {
        return { lang: ev.lang, text: piece.length > prev.text.length ? piece : prev.text };
      }
      return { lang: ev.lang, text: combined };
    });
  } else if (ev.type === "bilingual" && ev.text?.trim()) {
    setTranslateTarget(ev.lang);
    setAnswerOther((prev) => {
      if (prev?.lang === ev.lang && prev.text === ev.text) return prev;
      return { lang: ev.lang, text: ev.text };
    });
  }
}

export default function ChatPage() {
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState("");
  const [answerOther, setAnswerOther] = useState<{ lang: BilingualLang; text: string } | null>(null);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [busy, setBusy] = useState(false);
  const [translateBusy, setTranslateBusy] = useState(false);
  const [useStream, setUseStream] = useState(true);
  const [lang, setLang] = useState<BilingualLang>("zh");
  const [translateTarget, setTranslateTarget] = useState<BilingualLang>("en");
  const [recentItems, setRecentItems] = useState<RecentItem[]>([]);
  const [hint, setHint] = useState<string | null>(null);
  const [tagsFilter, setTagsFilter] = useState("");
  const [collectionsFilter, setCollectionsFilter] = useState("");
  const [yearsMin, setYearsMin] = useState("");
  const [yearsMax, setYearsMax] = useState("");
  const [claims, setClaims] = useState<ClaimRecord[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const translateAbortRef = useRef<AbortController | null>(null);

  const handleBilingual = useCallback(
    (ev: BilingualStreamEvent) => {
      applyBilingualEvent(ev, setAnswerOther, setTranslateTarget);
    },
    [],
  );

  useEffect(() => {
    setTranslateTarget(otherLang(lang));
  }, [lang]);

  const loadRecent = useCallback(async () => {
    try {
      const data = await apiGet<{ items: RecentItem[]; cache_enabled: boolean }>(
        `/chat/recent?lang=${lang}&limit=10`,
      );
      setRecentItems(data.cache_enabled ? data.items : []);
    } catch {
      setRecentItems([]);
    }
  }, [lang]);

  useEffect(() => {
    void loadRecent();
  }, [loadRecent]);

  function applyCachedPayload(payload: CachedChatPayload) {
    setAnswer(payload.answer ?? "");
    setCitations((payload.citations ?? []) as Citation[]);
    if (payload.answer_other?.trim() && payload.answer_other_lang) {
      setAnswerOther({ lang: payload.answer_other_lang, text: payload.answer_other });
      setTranslateTarget(payload.answer_other_lang);
    } else {
      setAnswerOther(null);
    }
  }

  async function pickRecent(item: RecentItem) {
    abortRef.current?.abort();
    translateAbortRef.current?.abort();
    setQ(item.question);
    setHint(null);
    if (!item.has_cache) {
      setHint("已填入问题，点击「发送」生成新回答。");
      return;
    }
    setBusy(true);
    setAnswer("");
    setAnswerOther(null);
    setCitations([]);
    try {
      const qs = new URLSearchParams({ question: item.question, lang });
      const hit = await apiGet<CachedChatPayload>(`/chat/cache?${qs.toString()}`);
      applyCachedPayload(hit);
      setHint("已从缓存载入（索引与模型配置未变）。");
    } catch {
      setHint("已填入问题；缓存已失效，请点击「发送」重新生成。");
    } finally {
      setBusy(false);
    }
  }

  async function clearTranslationCache() {
    setAnswerOther(null);
    setHint(null);
    const question = q.trim();
    if (!question) {
      setHint("已清空当前译文显示。");
      return;
    }
    try {
      const res = await apiPost<{ cleared: boolean; cache_enabled: boolean }>(
        "/chat/cache/clear-translation",
        { question, lang },
      );
      if (!res.cache_enabled) {
        setHint("问答缓存未开启，已仅清空页面上的译文。");
      } else if (res.cleared) {
        setHint("已清除该问题在服务端缓存的译文；可点击「重新翻译」生成新译文。");
      } else {
        setHint("缓存中无译文记录，已清空页面显示。");
      }
    } catch (e) {
      setHint(e instanceof Error ? e.message : "清除缓存失败");
    }
  }

  async function retranslate() {
    const src = answer.trim();
    if (!src) return;
    translateAbortRef.current?.abort();
    const ac = new AbortController();
    translateAbortRef.current = ac;
    setTranslateBusy(true);
    setAnswerOther({ lang: translateTarget, text: "" });
    try {
      await translateStream(
        { text: src, target_lang: translateTarget },
        (ev) => {
          if (ev.type === "error") {
            throw new Error(ev.message);
          }
          if (ev.type === "bilingual_start" || ev.type === "bilingual_token" || ev.type === "bilingual") {
            handleBilingual(ev);
          }
        },
        ac.signal,
      );
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setAnswerOther(null);
      window.alert(e instanceof Error ? e.message : "翻译失败");
    } finally {
      setTranslateBusy(false);
      if (translateAbortRef.current === ac) {
        translateAbortRef.current = null;
      }
    }
  }

  async function submit() {
    if (!q.trim()) return;
    abortRef.current?.abort();
    translateAbortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setBusy(true);
    setAnswer("");
    setAnswerOther(null);
    setCitations([]);
    setClaims([]);

    const scope: RetrievalScopeBody = {
      tags: parseScopeList(tagsFilter),
      collections: parseScopeList(collectionsFilter),
      years_min: yearsMin ? Number(yearsMin) : undefined,
      years_max: yearsMax ? Number(yearsMax) : undefined,
    };

    try {
      if (useStream) {
        await chatStream(
          { question: q, lang, ...scope },
          (ev: ChatStreamEvent) => {
            if (ev.type === "citations") {
              setCitations((ev.citations ?? []) as Citation[]);
            } else if (ev.type === "claims") {
              setClaims(ev.claims ?? []);
            } else if (ev.type === "token") {
              setAnswer((prev) => prev + (ev.t ?? ""));
            } else if (
              ev.type === "bilingual_start" ||
              ev.type === "bilingual_token" ||
              ev.type === "bilingual"
            ) {
              handleBilingual(ev);
            } else if (ev.type === "error") {
              setAnswer(ev.message ?? "错误");
            }
          },
          ac.signal,
        );
      } else {
        const res = await apiPost<{
          answer: string;
          citations: Citation[];
          answer_other?: string;
          answer_other_lang?: BilingualLang;
        }>("/chat", {
          question: q,
          lang,
          ...scope,
        });
        setAnswer(res.answer);
        setCitations(res.citations ?? []);
        setClaims((res as { claims?: ClaimRecord[] }).claims ?? []);
        if (res.answer_other?.trim() && res.answer_other_lang) {
          setAnswerOther({ lang: res.answer_other_lang, text: res.answer_other });
          setTranslateTarget(res.answer_other_lang);
        } else {
          setAnswerOther(null);
        }
      }
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setAnswer(e instanceof Error ? e.message : "请求失败");
    } finally {
      setBusy(false);
      abortRef.current = null;
      void loadRecent();
    }
  }

  const showTranslationPlaceholder = !answerOther?.text && (busy || translateBusy);

  return (
    <div className="space-y-4 max-w-3xl">
      <h1 className="text-xl font-semibold text-ink-950">文献问答</h1>
      <p className="text-sm text-ink-700">
        回答会尽量引用检索到的片段，并在正文中使用 [1]、[2] 形式标注。主答与译文均支持<strong>流式输出</strong>（默认开启）。
        正文按 <strong>Markdown + KaTeX</strong> 渲染。
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
          <span className="text-ink-600">主答语言</span>
          <select
            value={lang}
            onChange={(e) => setLang(e.target.value as BilingualLang)}
            className="rounded-md border border-mist-200 bg-white px-2 py-1 text-sm"
          >
            <option value="zh">中文提示</option>
            <option value="en">English prompt</option>
          </select>
        </label>
      </div>
      {recentItems.length > 0 && (
        <div className="rounded-xl border border-mist-200 bg-mist-50 p-3">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-ink-500">最近提问（随机）</span>
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
                key={`${item.created_at}-${item.question.slice(0, 24)}`}
                type="button"
                disabled={busy}
                title={item.question}
                onClick={() => void pickRecent(item)}
                className="max-w-full rounded-lg border border-mist-200 bg-white px-2.5 py-1.5 text-left text-xs text-ink-800 hover:border-accent hover:bg-accent-soft disabled:opacity-50"
              >
                <span className="line-clamp-2">{item.question}</span>
                <span className="mt-0.5 block text-[10px] text-ink-500">
                  {item.has_cache ? "点击载入缓存" : "点击填入"}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="grid gap-2 rounded-xl border border-mist-200 bg-mist-50 p-3 text-sm">
        <span className="text-xs font-semibold uppercase tracking-wide text-ink-500">检索范围（可选）</span>
        <input
          className="w-full rounded-md border border-mist-200 bg-white px-2 py-1.5 text-sm"
          placeholder="Zotero 标签，逗号分隔，例如：几何, PDE"
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
      <textarea
        className="min-h-[120px] w-full rounded-xl border border-mist-200 bg-white p-3 text-sm shadow-inner outline-none focus:border-accent"
        placeholder="例如：总结与 Yang-Mills 能量恒等式相关的主要结论。"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {hint && <p className="text-xs text-ink-600">{hint}</p>}
      <button
        type="button"
        disabled={busy}
        onClick={() => void submit()}
        className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
      >
        {busy ? "生成中…" : "发送"}
      </button>
      {answer && (
        <section className="space-y-3">
          <div className="rounded-xl border border-mist-200 bg-white p-4 text-sm leading-relaxed text-ink-900">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">
              {lang === "zh" ? "主答（中文）" : "Main answer (English)"}
            </div>
            <MarkdownKaTeX content={answer} />
          </div>

          <div className="rounded-xl border border-mist-200 bg-mist-50 p-4 text-sm leading-relaxed text-ink-900">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-ink-500">译文（流式）</span>
              <select
                value={translateTarget}
                onChange={(e) => setTranslateTarget(e.target.value as BilingualLang)}
                className="rounded-md border border-mist-200 bg-white px-2 py-1 text-xs"
                aria-label="翻译目标语言"
              >
                <option value="zh">译为中文</option>
                <option value="en">译为 English</option>
              </select>
              <button
                type="button"
                disabled={translateBusy || busy}
                onClick={() => void retranslate()}
                className="rounded-md border border-mist-300 bg-white px-3 py-1 text-xs font-medium text-ink-800 hover:bg-mist-100 disabled:opacity-50"
              >
                {translateBusy ? "翻译中…" : "重新翻译"}
              </button>
              <button
                type="button"
                disabled={translateBusy || busy}
                onClick={() => void clearTranslationCache()}
                className="rounded-md border border-mist-300 bg-white px-3 py-1 text-xs font-medium text-ink-600 hover:bg-mist-100 disabled:opacity-50"
                title="从问答缓存中删除译文，避免再次载入旧译文"
              >
                清除翻译缓存
              </button>
              <span className="text-xs text-ink-500">保留 [1][2] 引用编号</span>
            </div>
            {answerOther?.text ? (
              <MarkdownKaTeX content={answerOther.text} />
            ) : showTranslationPlaceholder ? (
              <p className="text-xs text-ink-600 animate-pulse">
                {translateBusy ? "译文生成中…" : "主答结束后将自动流式翻译…"}
              </p>
            ) : (
              <p className="text-xs text-ink-600">
                选择目标语言后点击「重新翻译」。需配置 <code className="text-[11px]">TRANSLATION_OLLAMA_MODEL</code> 与{" "}
                <code className="text-[11px]">BILINGUAL_ANSWER=1</code>（自动双语）。
              </p>
            )}
          </div>
        </section>
      )}
      {citations.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-ink-950">引用来源</h2>
          <div className="grid gap-2">
            {citations.map((c) => {
              const badge = verificationLabel(c.verification_status);
              return (
                <div key={c.chunk_id} className="rounded-lg border border-mist-200 bg-white p-3 text-xs text-ink-800">
                  <div className="flex flex-wrap items-center gap-2 font-semibold text-ink-950">
                    <span>
                      [{c.ref}] {c.title || c.paper_id}
                    </span>
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${badge.className}`}>
                      {badge.text}
                    </span>
                  </div>
                  {formatCitationSource(c) ? (
                    <div className="text-ink-500">{formatCitationSource(c)}</div>
                  ) : null}
                  {c.preview && <div className="mt-2 text-ink-700">{c.preview}</div>}
                </div>
              );
            })}
          </div>
        </section>
      )}
      {claims.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-ink-950">论断核验</h2>
          <div className="grid gap-2">
            {claims.map((cl, i) => {
              const badge = verificationLabel(cl.status);
              return (
                <div
                  key={`${i}-${cl.claim_text.slice(0, 24)}`}
                  className="rounded-lg border border-mist-200 bg-mist-50 p-3 text-xs"
                >
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${badge.className}`}>
                      {badge.text}
                    </span>
                    {cl.ref_num != null && <span className="text-ink-500">→ [{cl.ref_num}]</span>}
                  </div>
                  <p className="text-ink-800">{cl.claim_text}</p>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
