import Link from "next/link";
import { apiGet } from "@/lib/api";

type Stats = { papers: number; indexed_papers: number; chunks: number };

export default async function HomePage() {
  let stats: Stats | null = null;
  let err: string | null = null;
  try {
    stats = await apiGet<Stats>("/stats");
  } catch (e) {
    err = e instanceof Error ? e.message : "无法连接后端";
  }

  return (
    <div className="space-y-8">
      <section className="rounded-2xl border border-mist-200 bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-semibold text-ink-950">本地文献智能体（MVP）</h1>
        <p className="mt-3 text-ink-700 leading-relaxed">
          从 Zotero 存储目录扫描 PDF，解析为文本/Markdown 后分块入库，使用 FTS5
          与可选的 Ollama/OpenAI 嵌入做检索，并以「
          <a
            href="https://arxiv.org/abs/2411.14199"
            className="text-accent underline underline-offset-2 hover:opacity-90"
            rel="noreferrer"
            target="_blank"
          >
            OpenScholar
          </a>
          」式带引用提示生成回答或综述（自管模型与本地库，非官方 OpenScholar 服务）。
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <Link
            href="/library"
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90"
          >
            打开文献库
          </Link>
          <Link
            href="/settings"
            className="rounded-lg border border-mist-200 px-4 py-2 text-sm text-ink-800 hover:bg-mist-100"
          >
            配置路径与模型
          </Link>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-3">
        <StatCard title="文献条目" value={stats?.papers} error={err} />
        <StatCard title="已建立索引" value={stats?.indexed_papers} error={err} />
        <StatCard title="文本片段" value={stats?.chunks} error={err} />
      </section>

      <section className="rounded-2xl border border-mist-200 bg-white p-6 text-sm text-ink-700">
        <h2 className="text-lg font-semibold text-ink-950">推荐流程</h2>
        <ol className="mt-3 list-decimal space-y-2 pl-5 leading-relaxed">
          <li>在「设置」中确认 Zotero PDF 目录（默认 ~/Zotero/storage）。</li>
          <li>在「文献库」点击「扫描磁盘」，发现新增/变更的 PDF。</li>
          <li>对单篇文献点击「建立索引」（解析 + 分块 + 嵌入；MinerU 未安装时自动降级为 pypdf）。</li>
          <li>使用「问答」或「综述」；回答中的 [1][2] 对应下方引用卡片。</li>
        </ol>
      </section>
    </div>
  );
}

function StatCard({ title, value, error }: { title: string; value?: number; error: string | null }) {
  return (
    <div className="rounded-xl border border-mist-200 bg-white p-4 shadow-sm">
      <div className="text-xs uppercase tracking-wide text-ink-500">{title}</div>
      <div className="mt-2 text-3xl font-semibold text-ink-950">
        {error ? "—" : value ?? 0}
      </div>
      {error && <div className="mt-2 text-xs text-red-600">{error}</div>}
    </div>
  );
}
