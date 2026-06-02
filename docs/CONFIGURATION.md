# 配置

复制模板后编辑：

```bash
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local   # 可选
```

完整变量与组合表见 **`apps/api/.env.example`**。

## 路径

| 变量 | 默认 | 说明 |
|------|------|------|
| `DATA_DIR` | `./data`（相对 API 启动 cwd） | SQLite、`parsed/`、缓存 |
| `ZOTERO_STORAGE_PATH` | `~/Zotero/storage` | PDF 扫描根目录 |
| `ZOTERO_SQLITE_PATH` | `~/Zotero/zotero.sqlite` | 题录同步；空字符串关闭 |

## Provider

| 变量 | 说明 |
|------|------|
| `CHAT_PROVIDER` / `EMBED_PROVIDER` | `auto` \| `ollama` \| `openai` \| `transformers`（仅 CHAT），可混用 |
| `OLLAMA_*` | 本机对话与嵌入 |
| `OPENAI_*` / `OPENAI_EMBED_MODEL` | OpenAI 兼容网关 |

## 检索

| 变量 | 说明 |
|------|------|
| `RETRIEVE_TOP_K_FTS` / `RETRIEVE_TOP_K_FINAL` | FTS 召回 / 交给 LLM 的条数 |
| `RETRIEVE_MAX_CHUNKS_PER_PAPER` / `RETRIEVE_MAX_PAPERS` | 跨篇配额（`0` = 不限制） |
| `OPENSCHOLAR_RETRIEVER_ENABLED` / `OPENSCHOLAR_RERANKER_ENABLED` | 稠密召回与精排（PyTorch） |
| `OPENSCHOLAR_*_MODEL` | 本地目录或 HF ID |
| `BILINGUAL_RETRIEVAL` / `BILINGUAL_ANSWER` | 双语扩展 |
| `TRANSLATION_OLLAMA_MODEL` | Hy-MT 等 |

启用 Retriever 后需对文献**重新建立索引**以写入 `scholar_embedding_json`。

## MinerU

| 模式 | 配置 |
|------|------|
| CLI + mineru-api | `MINERU_MODE=cli`；`pnpm dev` 经 `scripts/dev-mineru-api.sh` |
| 云端 | `MINERU_MODE=cloud` + `MINERU_API_TOKEN`；不启动本机 mineru-api |
| 降级 | 失败时用 **pypdf** |

- `MINERU_CLI`：可执行文件绝对路径  
- `MINERU_CLI_STYLE=legacy`：旧版 CLI  
- `MINERU_MODEL_SOURCE=local` + `MINERU_TOOLS_CONFIG_JSON`：本地权重  

```bash
pnpm run download:mineru-models   # 默认从 ~/mineru.json 符号链接；`:copy` 为物理复制
# pnpm run download:mineru-models:hf   # 无本地权重时才从 Hugging Face 下载
```

## 任务 Worker

| 变量 | 默认 | 说明 |
|------|------|------|
| `TASK_WORKER_MODE` | `embedded` | `embedded`：API 进程内消费队列；`external`：仅入队，另开 Worker |
| `TASK_WORKER_CONCURRENCY` | `1` | 同时**从队列取走**、状态为 `running` 的任务数（1–16）；摘要与索引共用同一队列 |
| `INDEX_EMBED_CONCURRENCY` | `2` | **全局** BGE / OpenScholar 嵌入批次的并行上限（1–8），与 Worker 数独立 |
| `MINERU_PARSE_CONCURRENCY` | `1` | **全局** MinerU 解析并行上限（1–128） |

说明：界面「执行中 N」= 数据库里 `running` 的任务数，理论上 N ≤ `TASK_WORKER_CONCURRENCY`。若 Worker=4 但嵌入阶段只有 2 路在跑 API，多半是 `INDEX_EMBED_CONCURRENCY=2` 限制了嵌入；其余 `running` 任务可能在分块、写库或等待嵌入槽位。要让 4 篇同时嵌入，需把 `INDEX_EMBED_CONCURRENCY` 提到 4（注意 Ollama/GPU 负载）。修改后需**重启 API**。

`external` 时：

```bash
# apps/api/.env
TASK_WORKER_MODE=external
pnpm run dev:external   # 或 API + pnpm run dev:worker
```

文献库 **任务队列概览** 可取消全部 `queued`、清理指向已删文献的孤儿任务（见 [API.md](./API.md)）。

## 数据库维护

| 变量 | 默认 | 说明 |
|------|------|------|
| `DB_VACUUM_FREELIST_RATIO` | `0.25` | 启动时 `freelist/page_count` ≥ 阈值则 `VACUUM` |
| `DB_VACUUM_ON_STARTUP` | `0` | `1` 时每次启动强制 `VACUUM` |

详见 [OPERATIONS.md](./OPERATIONS.md)。

## 日志

| `PIPELINE_LOG` | 效果 |
|----------------|------|
| `0` | 关闭流水线日志 |
| `1` | 各阶段简要 |
| `2` | 含检索词、上下文预览 |

`LOG_STAGES`：`retrieve,embed,rag,llm,review,scan,index,parse,translate,cache,db,task,summary`（留空 = 全部）。

`LOG_CONTEXT`（默认 `1`）：在每条日志前附加当前 `task=` / `paper=` 前缀（取 id 前 8 位），便于 `TASK_WORKER_CONCURRENCY` / `INDEX_EMBED_CONCURRENCY` 并发时按文献过滤，例如：

```bash
# 终端里只看某篇文献的流水线日志（paper_id 前 8 位）
pnpm run dev 2>&1 | grep 'paper=51e99e0a'
```

设为 `0` 可恢复旧版纯时间戳格式。

文献库页在批量索引等任务运行时会显示 **「正在处理 · 按文献」** 面板（SSE `/tasks/active/stream`）：仅列出 `running` 的文献（排队中的在标题栏显示数量，不展开）；每行按流水线列出各阶段（解析 / 分块 / 嵌入等）：已完成阶段显示耗时与均速，当前阶段实时更新，未开始为「待处理」，未启用步骤（如未开 OpenScholar 嵌入）为「跳过」。阶段历史由后端写入 `progress_json.phase_history`。MinerU 云端轮询的页码进度（如 `114/200 页`）会写入 `progress_json` 并推送 SSE，与终端日志同步。列表行上的解析/索引徽章仍包含排队任务。终端亦可轮询 `GET /tasks/active`。

## 主对话模型（OpenScholar-8B）

### 方式 A：Ollama（GGUF，省显存）

```bash
ollama run hf.co/QuantFactory/Llama-3.1_OpenScholar-8B-GGUF:Q4_K_M
```

```env
CHAT_PROVIDER=ollama
OLLAMA_CHAT_MODEL=hf.co/QuantFactory/Llama-3.1_OpenScholar-8B-GGUF:Q4_K_M
```

### 方式 B：Transformers 直连（Ollama 不够用 / 需完整 HF 权重）

需先安装可选依赖：

```bash
cd apps/api && pip install -e '.[openscholar]'
```

```env
CHAT_PROVIDER=transformers
OPENSCHOLAR_CHAT_MODEL=OpenSciLM/Llama-3.1_OpenScholar-8B   # transformers 只读这一项（可改为本地目录）
OPENSCHOLAR_CHAT_DEVICE=auto
OPENSCHOLAR_CHAT_MAX_NEW_TOKENS=4096
```

`OLLAMA_CHAT_MODEL`（如 `hf.co/QuantFactory/Llama-3.1_OpenScholar-8B-GGUF:Q4_K_M`）是 **Ollama 里的 GGUF 量化包**，Transformers **不能**直接加载该字符串。同一套 OpenScholar-8B 在 Transformers 侧对应 HF 全量权重 `OpenSciLM/Llama-3.1_OpenScholar-8B`。

若未设置 `OPENSCHOLAR_CHAT_MODEL`，会按顺序选择：

1. `~/models/openscholar-ms-8b`（或同目录下其它 HF 布局，且根目录有 `model.safetensors` / `pytorch_model.bin`）
2. 由 `OLLAMA_CHAT_MODEL` 的 OpenScholar GGUF 名映射到 `OpenSciLM/Llama-3.1_OpenScholar-8B`

`~/models/openscholar-retriever` / `openscholar-reranker` 仅用于检索，与对话权重无关。`openscholar-q4` 为 Ollama 侧缓存占位；GGUF 在 Ollama 内由 `OLLAMA_CHAT_MODEL` 引用。若 `openscholar-ms-8b` 只有 tokenizer、权重在 `._____temp` 且约 450MB，说明 **ModelScope 下载未完成**，需补全后再走本地路径。

首次运行若未配置本地路径，会从 Hugging Face 下载约 16GB。国内建议先用魔搭下载到 `~/models/openscholar-ms-8b` 再指定 `OPENSCHOLAR_CHAT_MODEL`：

```bash
cd apps/api && .venv/bin/pip install modelscope
npm run download:openscholar-chat
# 或：.venv/bin/python scripts/download_openscholar_chat_model.py --force
```

```env
OPENSCHOLAR_CHAT_MODEL=/Users/<you>/models/openscholar-ms-8b
CHAT_PROVIDER=transformers
```

备选：`HF_ENDPOINT=https://hf-mirror.com`（仍走 HF 模型 id，见 `apps/api/.env.example`）。Apple Silicon 建议 `mps`，约需 16GB+ 统一内存。可与 `EMBED_PROVIDER=openai` 混用。

**GPU 利用率（MPS）**：日志中 `device=mps:0` 表示权重在 Apple GPU；自回归生成一次只出一个 token，活动监视器里 GPU 占用率常明显低于 100%，属正常现象。**无法通过 `TASK_WORKER_CONCURRENCY>1` 并行加速**（进程内共享一把推理锁）；并发>1 时只会连续刷 `chat 开始`，GPU 仍一次只算一篇。请保持 `TASK_WORKER_CONCURRENCY=1`；批量摘要优先 `OPENSCHOLAR_SUMMARY_MAX_NEW_TOKENS=768`、检索模型 `OPENSCHOLAR_DEVICE=cpu`，或改用 Ollama GGUF。日志应成对出现：`推理开始` → `推理完成 … 均速=XX tok/s` → `chat 完成`。探测：`cd apps/api && .venv/bin/python scripts/probe_openscholar_mps.py`。

Retriever/Reranker 与对话模型独立，均在 `apps/api/.venv` 用 PyTorch 加载。

## 解析质量分

`papers.parse_quality_score`（0–1）仅在**带解析的索引**或 **force 重建**时写入；`reindex_only` 不更新。低质量筛选阈值默认 **0.65**。详见 [ROADMAP.md](./ROADMAP.md) P1 与根 README 快速说明。
