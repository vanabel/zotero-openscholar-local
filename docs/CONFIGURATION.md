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
| `CHAT_PROVIDER` / `EMBED_PROVIDER` | `auto` \| `ollama` \| `openai`，可混用 |
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
pnpm run download:mineru-models   # 或 mineru-models-download
```

## 任务 Worker

| 变量 | 默认 | 说明 |
|------|------|------|
| `TASK_WORKER_MODE` | `embedded` | `embedded`：API 进程内消费队列；`external`：仅入队，另开 Worker |
| `TASK_WORKER_CONCURRENCY` | `1` | 同时执行的任务数（1–4）；摘要与索引共用同一队列 |

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

Ollama 需 **GGUF**，例如：

```bash
ollama run hf.co/QuantFactory/Llama-3.1_OpenScholar-8B-GGUF:Q4_K_M
```

`.env`：`OLLAMA_CHAT_MODEL=...`

Retriever/Reranker 在 `apps/api/.venv` 用 PyTorch 加载，**不必** `ollama pull`。

## 解析质量分

`papers.parse_quality_score`（0–1）仅在**带解析的索引**或 **force 重建**时写入；`reindex_only` 不更新。低质量筛选阈值默认 **0.65**。详见 [ROADMAP.md](./ROADMAP.md) P1 与根 README 快速说明。
