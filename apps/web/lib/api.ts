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

export type BilingualLang = "zh" | "en";

export type BilingualStreamEvent =
  | { type: "bilingual_start"; lang: BilingualLang }
  | { type: "bilingual_token"; lang: BilingualLang; t: string }
  | { type: "bilingual"; lang: BilingualLang; text: string };

export type ChatStreamEvent =
  | { type: "citations"; citations: unknown[]; contexts_used?: number }
  | { type: "token"; t: string }
  | BilingualStreamEvent
  | { type: "done" }
  | { type: "error"; message: string };

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
  body: { question: string; lang: string },
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

export type ReviewTemplate = "literature_review" | "grant_proposal";

export type ReviewStreamEvent =
  | { type: "citations"; citations: unknown[]; contexts_used?: number }
  | { type: "token"; t: string }
  | { type: "citation_check"; citation_check?: unknown }
  | { type: "done" }
  | { type: "error"; message: string; code?: string };

/** POST /review/stream（SSE） */
export async function downloadReviewMarkdown(
  body: { topic: string; focus?: string | null; lang: string; template?: ReviewTemplate; use_cache?: boolean },
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

export async function reviewStream(
  body: {
    topic: string;
    focus?: string | null;
    lang: string;
    use_cache?: boolean;
    template?: ReviewTemplate;
  },
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
