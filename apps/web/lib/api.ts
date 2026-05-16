const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

function parseApiErrorText(raw: string, status: number): string {
  try {
    const j = JSON.parse(raw) as {
      error?: { message?: string; code?: string };
      detail?: string | { message?: string };
    };
    if (j?.error?.message) {
      const code = j.error.code ? `[${j.error.code}] ` : "";
      return `${code}${j.error.message}`;
    }
    if (typeof j.detail === "string") return j.detail;
    if (j.detail && typeof j.detail === "object" && "message" in j.detail) {
      return String((j.detail as { message?: string }).message);
    }
  } catch {
    /* 非 JSON */
  }
  return raw.trim() || `HTTP ${status}`;
}

async function handle(res: Response) {
  if (!res.ok) {
    const t = await res.text();
    throw new Error(parseApiErrorText(t, res.status));
  }
  return res.json();
}

export async function apiGet<T = unknown>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  return handle(res);
}

export async function apiPost<T = unknown>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle(res);
}

export async function apiPut<T = unknown>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle(res);
}

export { BASE as API_BASE };

export type TaskStreamEvent =
  | { type: "snapshot"; items: unknown[] }
  | {
      type: "task_progress";
      task_id: string;
      paper_id?: string | null;
      task_type?: string;
      status?: string;
      progress?: { phase?: string; done?: number; total?: number; message?: string };
    }
  | {
      type: "task_status";
      task_id: string;
      paper_id?: string | null;
      task_type?: string;
      status: string;
      error?: string | null;
      progress?: { phase?: string; done?: number; total?: number; message?: string };
    };

/** SSE 订阅活动任务；浏览器端使用 EventSource。 */
export function subscribeActiveTasks(
  onEvent: (ev: TaskStreamEvent) => void,
  onError?: (err: Event) => void,
): () => void {
  const es = new EventSource(`${BASE}/tasks/active/stream`);
  es.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data) as TaskStreamEvent);
    } catch {
      /* ignore malformed */
    }
  };
  es.onerror = (e) => {
    onError?.(e);
  };
  return () => es.close();
}

export type BilingualLang = "zh" | "en";

export type BilingualStreamEvent =
  | { type: "bilingual_start"; lang: BilingualLang }
  | { type: "bilingual_token"; lang: BilingualLang; t: string }
  | { type: "bilingual"; lang: BilingualLang; text: string };

export type VerificationStatus = "verified" | "insufficient" | "unused" | "invalid_ref" | "unreferenced";

export type ClaimRecord = {
  claim_text: string;
  chunk_id?: string | null;
  ref_num?: number | null;
  verified?: boolean;
  verifier_score?: number;
  status: VerificationStatus | string;
};

export type ChatStreamEvent =
  | { type: "citations"; citations: unknown[]; contexts_used?: number }
  | { type: "citation_check"; citation_check?: unknown }
  | { type: "claims"; claims?: ClaimRecord[] }
  | { type: "token"; t: string }
  | BilingualStreamEvent
  | { type: "done" }
  | { type: "error"; message: string };

export type RetrievalScopeBody = {
  paper_ids?: string[] | null;
  tags?: string[] | null;
  collections?: string[] | null;
  years_min?: number | null;
  years_max?: number | null;
};

export type TranslateStreamEvent = BilingualStreamEvent | { type: "done" } | { type: "error"; message: string };

async function consumeSse<T>(res: Response, onEvent: (ev: T) => void): Promise<void> {
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || res.statusText);
  }
  const reader = res.body?.getReader();
  if (!reader) {
    throw new Error("响应无 body");
  }
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    for (;;) {
      const idx = buf.indexOf("\n\n");
      if (idx < 0) break;
      const block = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 2);
      for (const line of block.split("\n")) {
        const s = line.trim();
        if (!s.startsWith("data:")) continue;
        const raw = s.startsWith("data: ") ? s.slice(6) : s.slice(5).trim();
        if (!raw) continue;
        try {
          onEvent(JSON.parse(raw) as T);
        } catch {
          /* 非 JSON 行忽略 */
        }
      }
    }
  }
}

/** POST /chat/stream（SSE） */
export async function chatStream(
  body: { question: string; lang: string } & RetrievalScopeBody,
  onEvent: (ev: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  await consumeSse<ChatStreamEvent>(res, onEvent);
}

export type ReviewTemplate =
  | "literature_review"
  | "grant_proposal"
  | "quick_review"
  | "comparative_review";

export type ReviewStreamEvent =
  | { type: "citations"; citations: unknown[]; contexts_used?: number }
  | { type: "token"; t: string }
  | { type: "citation_check"; citation_check?: unknown }
  | { type: "claims"; claims?: ClaimRecord[] }
  | { type: "done" }
  | { type: "error"; message: string; code?: string };

/** POST /review/stream（SSE） */
export async function downloadReviewMarkdown(
  body: {
    topic: string;
    focus?: string | null;
    lang: string;
    template?: ReviewTemplate;
    use_cache?: boolean;
  } & RetrievalScopeBody,
): Promise<{ blob: Blob; filename: string }> {
  const res = await fetch(`${BASE}/review/export-markdown`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/markdown" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(parseApiErrorText(t, res.status));
  }
  const disp = res.headers.get("Content-Disposition") || "";
  const m = /filename="([^"]+)"/.exec(disp);
  const filename = m?.[1] ?? "review.md";
  const blob = await res.blob();
  return { blob, filename };
}

export async function downloadReviewDocx(
  body: {
    topic: string;
    focus?: string | null;
    lang: string;
    template?: ReviewTemplate;
    use_cache?: boolean;
  } & RetrievalScopeBody,
): Promise<{ blob: Blob; filename: string }> {
  const res = await fetch(`${BASE}/review/export-docx`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(parseApiErrorText(t, res.status));
  }
  const disp = res.headers.get("Content-Disposition") || "";
  const m = /filename="([^"]+)"/.exec(disp);
  const filename = m?.[1] ?? "review.docx";
  const blob = await res.blob();
  return { blob, filename };
}

export async function reviewStream(
  body: {
    topic: string;
    focus?: string | null;
    lang: string;
    use_cache?: boolean;
    template?: ReviewTemplate;
  } & RetrievalScopeBody,
  onEvent: (ev: ReviewStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE}/review/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  await consumeSse<ReviewStreamEvent>(res, onEvent);
}

/** POST /chat/translate/stream（SSE） */
export async function translateStream(
  body: { text: string; target_lang: BilingualLang },
  onEvent: (ev: TranslateStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE}/chat/translate/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  await consumeSse<TranslateStreamEvent>(res, onEvent);
}
