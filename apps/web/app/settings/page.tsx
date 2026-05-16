"use client";

import { useEffect, useState } from "react";
import { API_BASE, apiGet, apiPut } from "@/lib/api";

type Settings = {
  repo_root: string;
  env_file_used: string;
  env_file_exists: boolean;
  zotero_storage_path: string;
  zotero_storage_path_rel: string | null;
  zotero_sqlite_path: string | null;
  zotero_sqlite_path_rel: string | null;
  data_dir: string;
  data_dir_rel: string | null;
  ollama_base_url: string;
  ollama_chat_model: string;
  ollama_embed_model: string;
  openai_configured: boolean;
  mineru_mode: string;
  mineru_api_base_url: string;
  mineru_cloud_configured: boolean;
};

function PathRow({
  label,
  rel,
  abs,
}: {
  label: string;
  rel: string | null;
  abs: string | null;
}) {
  if (!abs) {
    return (
      <div className="text-xs text-ink-600">
        <span className="font-semibold text-ink-500">{label}</span>：未配置
      </div>
    );
  }
  const showRel = rel && rel !== abs;
  return (
    <div className="text-xs text-ink-700">
      <div className="font-semibold text-ink-500">{label}</div>
      {showRel ? (
        <>
          <code className="mt-0.5 block break-all rounded bg-mist-100 px-2 py-1 text-[11px] text-ink-900">
            {rel}
          </code>
          <div className="mt-1 text-[11px] text-ink-500">绝对路径：{abs}</div>
        </>
      ) : (
        <code className="mt-0.5 block break-all rounded bg-mist-100 px-2 py-1 text-[11px]">{abs}</code>
      )}
    </div>
  );
}

export default function SettingsPage() {
  const [s, setS] = useState<Settings | null>(null);
  const [path, setPath] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const data = await apiGet<Settings>("/settings");
        setS(data);
        setPath(data.zotero_storage_path);
      } catch (e) {
        setMsg(e instanceof Error ? e.message : "加载失败");
      }
    })();
  }, []);

  async function save() {
    setMsg("保存中…");
    try {
      const data = await apiPut<Settings>("/settings", { zotero_storage_path: path });
      setS(data);
      setPath(data.zotero_storage_path);
      setMsg("已保存。");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "保存失败");
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-ink-950">设置</h1>
      <div className="rounded-xl border border-mist-200 bg-white p-4 text-sm text-ink-800 space-y-3">
        <div>
          <div className="text-xs font-semibold uppercase text-ink-500">后端地址（前端环境变量）</div>
          <code className="mt-1 block rounded bg-mist-100 px-2 py-1 text-xs">{API_BASE}</code>
          <p className="mt-1 text-xs text-ink-600">在 apps/web/.env.local 中设置 NEXT_PUBLIC_API_URL（相对仓库根）。</p>
        </div>
        {s && (
          <>
            <PathRow label="仓库根（后端判定）" rel={null} abs={s.repo_root} />
            <label className="block">
              <div className="text-xs font-semibold uppercase text-ink-500">Zotero PDF 目录（可编辑）</div>
              <p className="mt-0.5 text-[11px] text-ink-500">
                保存为绝对路径；若在仓库根下，下方「当前生效」会同时显示相对路径。
              </p>
              <input
                className="mt-1 w-full rounded-lg border border-mist-200 p-2 text-sm"
                value={path}
                onChange={(e) => setPath(e.target.value)}
              />
            </label>
            <div className="rounded-lg border border-mist-100 bg-mist-50/80 p-3 space-y-2">
              <div className="text-xs font-semibold text-ink-600">当前生效（后端解析后）</div>
              <PathRow label="Zotero PDF 目录" rel={s.zotero_storage_path_rel} abs={s.zotero_storage_path} />
              <PathRow label="数据目录 DATA_DIR" rel={s.data_dir_rel} abs={s.data_dir} />
              <PathRow label="Zotero 题录库（只读）" rel={s.zotero_sqlite_path_rel} abs={s.zotero_sqlite_path} />
            </div>
            <div className="text-xs text-ink-600">
              Ollama：{s.ollama_base_url}，对话模型 {s.ollama_chat_model}，嵌入模型 {s.ollama_embed_model}
            </div>
            <div className="text-xs text-ink-600">OpenAI 兼容接口：{s.openai_configured ? "已配置" : "未配置（将使用 Ollama）"}</div>
            <div className="text-xs text-ink-600">
              MinerU：模式 <code>{s.mineru_mode}</code>
              {s.mineru_mode === "cloud" && (
                <>
                  ，API <code>{s.mineru_api_base_url}</code>，密钥{" "}
                  {s.mineru_cloud_configured ? "已配置" : "未配置（请在 apps/api/.env 设置 MINERU_API_TOKEN）"}
                </>
              )}
            </div>
          </>
        )}
        <button
          type="button"
          onClick={() => void save()}
          className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white hover:opacity-90"
        >
          保存路径
        </button>
      </div>
      {msg && <div className="text-sm text-ink-800">{msg}</div>}
      <section className="rounded-xl border border-mist-200 bg-white p-4 text-sm text-ink-700 space-y-2">
        <h2 className="font-semibold text-ink-950">后端环境变量（apps/api/.env）</h2>
        {s && (
          <div className="space-y-2 text-xs text-ink-600 leading-relaxed">
            <p>
              本页「Ollama / MinerU / DATA_DIR」等<strong>生效值</strong>来自：进程环境变量 +{" "}
              <strong>固定读取</strong>的 <code className="rounded bg-mist-100 px-1">{s.env_file_used}</code>
              {s.env_file_exists ? (
                <>（文件存在，已参与加载）。</>
              ) : (
                <span className="text-amber-800">
                  （<strong>文件不存在</strong>，仅使用默认值与系统环境变量；请在该路径创建 .env 或复制
                  apps/api/.env.example。）
                </span>
              )}
            </p>
            <p>
              此前若从<strong>仓库根目录</strong>启动 API，相对路径的 <code>.env</code> 可能指到仓库根的
              .env，与 apps/api/.env 混淆；现已改为<strong>始终优先加载 apps/api/.env</strong>（若存在），与启动
              cwd 无关。
            </p>
            <p>
              下方示例块仅为<strong>说明常见变量名</strong>，不是从你磁盘读取的文件内容；真实键值请以{" "}
              <code className="rounded bg-mist-100 px-1">apps/api/.env</code> 为准，或对照{" "}
              <code className="rounded bg-mist-100 px-1">apps/api/.env.example</code>。
            </p>
          </div>
        )}
        <pre className="overflow-x-auto rounded-lg bg-mist-100 p-3 text-xs leading-relaxed text-ink-800">
          {`# 示例（与 .env.example 一致；修改请编辑 apps/api/.env）
DATA_DIR=./data
ZOTERO_STORAGE_PATH=~/Zotero/storage
ZOTERO_SQLITE_PATH=~/Zotero/zotero.sqlite

OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_CHAT_MODEL=qwen2.5:7b
OLLAMA_EMBED_MODEL=nomic-embed-text

# MINERU_MODE=cloud
# MINERU_API_TOKEN=

# OPENAI_API_BASE=
# OPENAI_API_KEY=`}
        </pre>
      </section>
    </div>
  );
}
