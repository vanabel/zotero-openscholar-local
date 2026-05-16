# zotero-openscholar-local

**单人**个人科研知识库：将 **Zotero 本地 PDF** 解析、分块、检索，用于**文献问答**、**文献综述**与**项目申请书素材**。核心投入在解析 / chunk / 检索 / 引用 / 综述模板五类质量（见 **[ROADMAP.md](./ROADMAP.md)**）。

技术上：MinerU 或 pypdf 降级 → Markdown 分块 → **FTS5** + 可选 **OpenScholar Retriever/Reranker**（含 **RRF** 与**跨篇配额**）→ 带 `[n]` 引用的问答与综述。与 **[OpenScholar](https://arxiv.org/abs/2411.14199)** 同类「证据检索 + 可核查引用」；**LLM 与索引均为本机/自管**。

---

## 功能概览

| 能力 | 说明 |
|------|------|
| Zotero PDF 扫描 | 递归 `storage` 目录，`sha256` / 大小 / `mtime` 增量；删除文件标记 `deleted` |
| 解析 | MinerU 3.x（CLI / 常驻 `mineru-api` / **在线 cloud**）或 **pypdf** 降级 |
| 索引 | Markdown 标题分块；Ollama/OpenAI 嵌入；可选 **OpenScholar 稠密向量**（`scholar_embedding_json`） |
| 检索 | FTS5 召回；多查询合并（双语扩展）；**RRF** 融合 FTS + dense；OpenScholar **Reranker** 或 Ollama 余弦重排 |
| 问答 / 综述 | 引用式提示 `[1][2]`；**SSE 流式**；可选**双语**检索与答案 |
| 缓存 | 问答 / 综述 SQLite 缓存；近期问题 / 主题快捷填入 |
| 前端 | Next.js 14：概览、文献库（搜索、批量索引）、问答、综述、设置 |
| 工程 | 根目录 `pnpm`/`npm` + `concurrently`；`pytest`；可选 PM2 |

---

## 与 OpenScholar 的关系

| | 本仓库 | OpenScholar 论文 |
|---|--------|------------------|
| 文献来源 | Zotero **本地 PDF** | 大规模远程论文库（OSDS） |
| 检索 | FTS + 本机向量（Ollama 或 **OpenScholar Retriever/Reranker**） | 官方 datastore + 专用检索/重排 |
| 生成 | 自管 LLM（Ollama GGUF / OpenAI 兼容）；提示约束「只据证据 + `[n]`」 | 官方流水线与评测 |
| 主模型 | 可选 **[OpenScholar-8B](https://huggingface.co/QuantFactory/Llama-3.1_OpenScholar-8B-GGUF)**（`OLLAMA_CHAT_MODEL`） | [Llama-3.1_OpenScholar-8B](https://huggingface.co/OpenSciLM/Llama-3.1_OpenScholar-8B) |

论文：*[OpenScholar: Synthesizing Scientific Literature with Retrieval-augmented LMs](https://arxiv.org/abs/2411.14199)*。

---

## 快速开始

在**仓库根目录**：

```bash
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local   # 可选
```

### pnpm（推荐）

```bash
corepack enable
pnpm install
pnpm run setup    # apps/api/.venv + pip install -e ".[dev,hf,openscholar]"
pnpm dev          # mineru-api + API :8000 + Web :3000
```

未安装 MinerU 时：`pnpm run dev:no-mineru`（仅 API + Web）。

```bash
pnpm test                              # API pytest
RUN_OLLAMA_TRANSLATION_TEST=1 pnpm test   # 可选：Hy-MT 翻译冒烟（需本机 Ollama）
```

### npm

```bash
npm install && npm run setup && npm run dev
# 或 npm run dev:no-mineru
```

浏览器：<http://localhost:3000> · API：<http://127.0.0.1:8000>

### 推荐流程

1. **设置** — 确认 Zotero PDF 目录（默认 `~/Zotero/storage`）。
2. **文献库** — 「扫描磁盘」→ 勾选文献 → 「批量 MinerU 索引」（或单篇「建立索引」）。
3. **问答 / 综述** — 正文中的 `[1][2]` 对应引用卡片。

---

## 项目结构

| 路径 | 说明 |
|------|------|
| `apps/api` | FastAPI + SQLite + FTS5 |
| `apps/web` | Next.js 14 + Tailwind |
| 仓库根 | `concurrently` 开发编排；`scripts/dev-mineru-api.sh` |

**Python 隔离**：依赖只装在 **`apps/api/.venv`**。请用 `apps/api/.venv/bin/python` 或根目录脚本（`pnpm dev:api` 等），**不要**往系统 `python3` 全局 `pip install`。MinerU 可装在另一 venv，通过 `MINERU_CLI` 指向其可执行文件。

---

## 配置要点

完整变量见 **`apps/api/.env.example`**。常用项：

| 变量 | 含义 |
|------|------|
| `DATA_DIR` | 数据目录（默认 `./data`，相对 API 启动 cwd） |
| `ZOTERO_STORAGE_PATH` | PDF 扫描根目录 |
| `OLLAMA_CHAT_MODEL` / `OLLAMA_EMBED_MODEL` | 对话与可选嵌入 |
| `OPENSCHOLAR_RETRIEVER_ENABLED` / `OPENSCHOLAR_RERANKER_ENABLED` | 启用官方检索/精排（PyTorch，见下节） |
| `RETRIEVE_TOP_K_FTS` / `RETRIEVE_TOP_K_FINAL` | FTS 召回数 / 交给 LLM 的最终条数 |
| `RETRIEVE_MAX_CHUNKS_PER_PAPER` / `RETRIEVE_MAX_PAPERS` | 单篇最多 chunk 数 / 最多文献篇数（`0` = 不限制） |
| `BILINGUAL_RETRIEVAL` / `BILINGUAL_ANSWER` | 双语检索扩展 / 第二语言答案 |
| `TRANSLATION_OLLAMA_MODEL` | Hy-MT 等翻译模型（Ollama） |
| `MINERU_MODE` | `cli`（本机）或 `cloud`（[mineru.net](https://mineru.net) + `MINERU_API_TOKEN`） |
| `MINERU_API_URL` | 常驻 mineru-api 地址（`pnpm dev` 默认 `127.0.0.1:8001`） |
| `LOG_LEVEL` / `PIPELINE_LOG` / `LOG_STAGES` | 流水线调试日志 |

### 调试日志

| `PIPELINE_LOG` | 效果 |
|----------------|------|
| `0` | 关闭流水线专用日志 |
| `1` | 各阶段简要（INFO） |
| `2` | 含检索词、上下文预览等（DEBUG） |

`LOG_STAGES` 可选：`retrieve,embed,rag,llm,review,scan,index,parse,translate,cache`（留空 = 全部）。

---

## 模型与检索

### 主对话（问答 / 综述）

默认 Ollama（如 `qwen2.5:7b`）。若使用 **OpenScholar-8B**：

- Ollama 需 **GGUF**，不能直接挂载魔搭/HF 的 safetensors 目录。
- 推荐：`ollama run hf.co/QuantFactory/Llama-3.1_OpenScholar-8B-GGUF:Q4_K_M`，再在 `.env` 设置 `OLLAMA_CHAT_MODEL=...`。
- 魔搭完整权重 [OpenScholar/Llama-3.1_OpenScholar-8B](https://modelscope.cn/models/OpenScholar/Llama-3.1_OpenScholar-8B) 需自行转 GGUF，或改用上述 QuantFactory GGUF。

### OpenScholar Retriever + Reranker（检索，非 Ollama）

| 角色 | 默认模型 | 运行环境 |
|------|----------|----------|
| 稠密召回 | `OpenSciLM/OpenScholar_Retriever` | `apps/api/.venv` + PyTorch |
| 精排 | `OpenSciLM/OpenScholar_Reranker` | 同上（`transformers` 序列分类） |

与 8B / Hy-MT **不同**：不必 `ollama pull`；`pnpm run setup` 安装 `[openscholar]` 后，**首次检索或建索引**时从 Hugging Face 下载（缓存默认 `~/.cache/huggingface/hub/`，可用 `HF_HOME` / `HF_ENDPOINT` / `HF_TOKEN`）。

```env
OPENSCHOLAR_RETRIEVER_ENABLED=1
OPENSCHOLAR_RERANKER_ENABLED=1
OPENSCHOLAR_DEVICE=auto
RETRIEVE_TOP_K_FTS=80
RETRIEVE_TOP_K_FINAL=24
```

**启用 Retriever 后**请对文献重新「建立索引」，以写入 `scholar_embedding_json`。未装 `[openscholar]` 时回退 **FTS + Ollama 嵌入重排**。

**国内预下载（魔搭）** — 下载到本地目录后，`.env` 中改为**绝对路径**（勿再用 `OpenSciLM/...` HF ID）：

- [OpenScholar/OpenScholar_Retriever](https://modelscope.cn/models/OpenScholar/OpenScholar_Retriever)
- [OpenScholar/OpenScholar_Reranker](https://modelscope.cn/models/OpenScholar/OpenScholar_Reranker)

或在 venv 中：`huggingface-cli download OpenSciLM/OpenScholar_Retriever`（可设 `HF_ENDPOINT=https://hf-mirror.com`）。

### 中英双语（可选）

需 Ollama 加载 **Hy-MT**（推荐魔搭 `HY-MT1.5-1.8B-Q4_K_M.gguf` + 官方 `TEMPLATE` 的 Modelfile）。API 已按官方 **ZH⇄XX** 提示包装（`translation.py`）。**勿**用 1.25bit 等超小 GGUF（Ollama 常报 `invalid ggml type`）。

```env
TRANSLATION_OLLAMA_MODEL=hy-mt:1.5
BILINGUAL_RETRIEVAL=1
BILINGUAL_ANSWER=1
```

向量重排仍仅用**原始用户问题**的 embedding。流式：正文结束后 SSE `bilingual`；非流式：`answer_other` / `answer_other_lang`。

### 仅重建索引（不跑 MinerU）

已有 `data/parsed/{paper_id}/document.md` 时：

```bash
pnpm run reindex:all
pnpm run reindex -- --paper-id <id>
```

等价 API：`POST /papers/{id}/index?reindex_only=true`（**不要**与 `force=true` 同用）。

---

## MinerU

| 模式 | 配置 |
|------|------|
| CLI + mineru-api | `MINERU_MODE=cli`（默认）；`pnpm dev` 经 `scripts/dev-mineru-api.sh` 拉起 API |
| 在线 | `MINERU_MODE=cloud` + `MINERU_API_TOKEN` |
| 降级 | 未安装或失败时 **pypdf** |

- 进程找不到 `mineru`：`.env` 设 **`MINERU_CLI` 绝对路径**。
- 旧版 CLI：`MINERU_CLI_STYLE=legacy`。
- **本地权重**：`MINERU_MODEL_SOURCE=local` + `MINERU_TOOLS_CONFIG_JSON` 指向 `mineru.json`（示例 `apps/api/config/mineru.json.example`）。权重须在 **mineru-api 进程**生效。

```bash
# 官方（在含 mineru 的 venv 中）
mineru-models-download -s huggingface -m all

# 或本仓库脚本（apps/api/.venv）
pnpm run download:mineru-models
```

---

## API 参考

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/stats` | 文献 / 索引 / 片段统计 |
| POST | `/scan` | 扫描 Zotero storage（增量） |
| GET | `/papers?q=` | 文献列表（标题、路径、作者字段搜索） |
| POST | `/papers/{id}/index` | 解析 + 分块 + 嵌入 + FTS；`force=true` 清空 parsed 后重跑 |
| POST | `/papers/{id}/index?reindex_only=true` | 仅重建分块/嵌入/FTS，复用 Markdown |
| POST | `/papers/index-batch` | 批量索引；body 可含 `reindex_only` |
| POST | `/chat` | 问答（JSON） |
| POST | `/chat/stream` | 问答流式（SSE：`citations` → `token` → 可选 `bilingual*` → `done`） |
| GET | `/chat/recent` | 近期提问 |
| POST | `/review` | 综述 |
| POST | `/review/stream` | 综述流式 |
| GET | `/review/recent` | 近期综述主题 |
| GET/PUT | `/settings` | Zotero 路径等 |
| GET | `/chunks/{id}` | 片段详情 |

数据默认写入 `./data`（`DATA_DIR`）。

---

## 测试与常驻部署

```bash
pnpm test
RUN_OLLAMA_TRANSLATION_TEST=1 pnpm test   # 需 Ollama + Hy-MT
```

**PM2**（长期运行，非热重载开发）：

```bash
npm run setup
npx pm2 start ecosystem.config.cjs
```

---

## 手动分终端启动

**后端**

```bash
cd apps/api
python3 -m venv .venv && .venv/bin/pip install -e ".[dev,hf,openscholar]"
cp .env.example .env
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

**前端**

```bash
cd apps/web && npm install && cp .env.example .env.local && npm run dev
```

需本机 **Ollama**（或 OpenAI 兼容 API）。OpenScholar Retriever/Reranker 与 Ollama **并行、互不替代**。
