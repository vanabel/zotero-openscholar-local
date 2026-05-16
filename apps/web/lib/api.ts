const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

async function handle(res: Response) {
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || res.statusText);
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

export type ReviewStreamEvent =
  | { type: "citations"; citations: unknown[]; contexts_used?: number }
  | { type: "token"; t: string }
  | { type: "done" }
  | { type: "error"; message: string };

/** POST /review/stream（SSE） */
export async function reviewStream(
  body: { topic: string; focus?: string | null; lang: string; use_cache?: boolean },
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
