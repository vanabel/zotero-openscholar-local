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
| `TASK_WORKER_CONCURRENCY` | `1` | 同时执行的任务数（1–16）；摘要与索引共用同一队列 |

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

首次运行会从 Hugging Face 下载约 16GB；Apple Silicon 建议 `mps`，约需 16GB+ 统一内存。可与 `EMBED_PROVIDER=openai` 混用。

Retriever/Reranker 与对话模型独立，均在 `apps/api/.venv` 用 PyTorch 加载。

## 解析质量分

`papers.parse_quality_score`（0–1）仅在**带解析的索引**或 **force 重建**时写入；`reindex_only` 不更新。低质量筛选阈值默认 **0.65**。详见 [ROADMAP.md](./ROADMAP.md) P1 与根 README 快速说明。
