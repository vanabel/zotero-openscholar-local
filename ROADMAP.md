# Roadmap

按**当前实现**与可验收里程碑排列。与 [README.md](./README.md) 交叉维护。

**图例**：`[x]` = 已在主线实现；`[ ]` = 未做或仅占位；`[~]` = 部分实现（见条目说明）。

---

## 当前能力（2026-05）

### 已可用 `[x]`

| 领域 | 状态 |
|------|------|
| **前端** | `[x]` Next.js 14：概览、文献库（搜索、多选、批量索引）、问答、综述、设置 |
| **后端** | `[x]` FastAPI：`/health`、`/stats`、`/scan`、`/papers`、`/papers/{id}/index`、`/papers/index-batch`、`/chat`、`/chat/stream`、`/review`、`/review/stream`、`/settings`、`/chunks/{id}` |
| **存储** | `[x]` SQLite：`papers`、`chunks`、`summaries`、`tasks`、`app_settings`、`chat_cache`；片段 **FTS5**；`scholar_embedding_json` |
| **Zotero** | `[x]` 扫描 `storage` 下 PDF；增量 `sha256` / 大小 / `mtime`；`deleted` 标记 |
| **Zotero 题录** | `[x]` 只读 `zotero.sqlite` → `papers`（标题、作者、年份、期刊、DOI、标签、集合）；扫描后自动同步；`POST /papers/sync-zotero-metadata` |
| **解析** | `[x]` MinerU CLI / 常驻 `mineru-api` / **cloud API**；超页数 **自动切片 + 断点续传**；zip 下载重试；pypdf 降级；`dev-mineru-api.sh` |
| **索引** | `[x]` Markdown 分块；Ollama/OpenAI 嵌入；**OpenScholar Retriever 稠密向量**（可选）；`reindex_only`；非 force 复用 `document.md` |
| **检索** | `[x]` FTS + 多查询合并；**RRF**（FTS + OpenScholar dense）；**OpenScholar Reranker** 或 Ollama 余弦；可配置 `RETRIEVE_TOP_K_*` |
| **生成** | `[x]` 引用式 `[n]` 问答与综述；SSE 流式 |
| **双语** | `[x]` `BILINGUAL_RETRIEVAL` / `BILINGUAL_ANSWER` + Hy-MT（`translation.py`）；流式 `bilingual*`（问答侧） |
| **缓存** | `[x]` 问答 / 综述缓存；`/chat/recent`、`/review/recent` |
| **展示** | `[x]` Markdown + KaTeX（`/chat`、`/review`） |
| **状态校准** | `[x]` 列表/详情加载时根据 `document.md` 与 `chunks` 回写 `parse_status` / `index_status` |
| **配置** | `[x]` 固定加载 `apps/api/.env`（不依赖 cwd）；设置页展示生效值与相对仓库根路径 |
| **运维脚本** | `[x]` `reindex` / `reindex:all`；`download:mineru-models` |
| **测试** | `[x]` pytest：健康检查、检索词、RRF、缓存、翻译 sanitize、Zotero sqlite 同步、MinerU 切片路径、可选 Ollama 翻译冒烟 |
| **工程** | `[x]` pnpm workspace + `concurrently`；`PIPELINE_LOG`；可选 PM2 |

### 近期已完成（相对初版 MVP）

- [x] **OpenScholar Retriever + Reranker**（PyTorch，`openscholar_retrieval.py` + `retriever.py` RRF）
- [x] **`scholar_embedding_json`** 建索引与全库 dense 召回
- [x] **`POST /chat/stream`**、双语 SSE、问答缓存
- [x] **文献库**：标题/路径/作者/标签/集合搜索、批量 `index-batch`、强制重建
- [x] **MinerU cloud**（`MINERU_MODE=cloud`）
- [x] **MinerU cloud 大 PDF**：按页切片、合并 Markdown、**分段断点续传**（`_mineru_cloud_chunks/_progress.json`）
- [x] **`reindex_only`** API 与 CLI `pnpm run reindex[:all]`
- [x] **非 force 复用**已有 `document.md` / 已有索引
- [x] **综述 / 问答**流式与缓存、`/review/recent`
- [x] **Zotero 题录同步**（`zotero_sqlite_sync.py` + 文献库展示作者/标签/集合）
- [x] **设置页**：真实生效配置 + `apps/api/.env` 路径说明（非硬编码示例块）
- [x] **解析完成后**将 `index_status` 置为 `pending`，避免与旧 chunk 误显示为已索引

### 明确未做或仅占位 `[ ]`

- [ ] **LanceDB / Qdrant** 等专用向量库（当前 dense 存 SQLite `scholar_embedding_json`）
- [ ] **异步任务队列**（Celery/RQ）与索引进度 WebSocket/SSE
- [ ] **「仅索引未 indexed」** 一键 API（需自写脚本或手动筛选 `index_status`）
- [ ] **跨篇配额**（每篇最多 k chunk）、chunk 去重策略
- [ ] **综述双语**流式、导出 Markdown/DOCX、`summaries` 表用于综述聚合
- [ ] **前端**暴露 OpenScholar / 双语开关（主要靠 `.env`）
- [ ] **Transformers 直连** OpenScholar-8B（无 Ollama）
- [ ] **ScholarQA 评测**、外部 Semantic Scholar / OpenAlex 补全文
- [ ] **CI**（GitHub Actions）
- [ ] **shadcn/ui** 组件库统一
- [ ] **文献库 UX**：索引进度条、失败重试入口、解析预览（`document.md` 片段）
- [ ] **错误面**：LLM/嵌入/Ollama/OpenScholar 不可用时的统一 JSON 与前端提示

---

## Phase 0 — 稳定 MVP（短期）

目标：新环境少踩坑、核心路径可回归。

- [x] README / ROADMAP 与实现同步
- [x] API 冒烟与检索/缓存单元测试；可选 Ollama 翻译冒烟
- [x] OpenScholar 检索接入与回退路径
- [x] 批量索引 API + 文献库 UI
- [x] 固定从 **`apps/api/.env`** 加载配置（与启动 cwd 无关）
- [x] 设置 API/UI：路径相对仓库根展示、`.env` 生效说明
- [x] 文献库 **parse/index 状态**与磁盘/chunks 校准
- [~] **`DATA_DIR` 行为**文档化（README 有说明；可选进一步锚定到仓库根 `data/`）
- [ ] **索引 / 扫描** fixture 集成测试（mock LLM）
- [ ] **错误面**：LLM/嵌入/Ollama/OpenScholar 不可用时的统一 JSON 与前端提示
- [ ] **文献库 UX**：索引进度、失败重试、解析预览（`document.md` 片段）
- [ ] **CI**：`pnpm test`（无 Ollama 跳过集成）

**验收**：README 流程「扫描 → 索引 1 篇 → 问答（含流式）」可完成；`pnpm test` 默认全绿。

---

## Phase 1 — Zotero 题录（2–4 周）

- [x] 只读 **`zotero.sqlite`** → `papers`（标题、作者、年份、期刊、DOI、标签、集合）
- [x] 文献库展示题录（作者、年份、venue、DOI、标签、集合）
- [x] 扫描磁盘后自动尝试题录同步；手动 `POST /papers/sync-zotero-metadata`
- [~] **按标签/年份/集合筛选**（当前为统一 `q` 模糊搜索，含上述字段，无独立筛选项）
- [ ] PDF 与 Zotero item 稳定关联；多附件策略文档化

**验收**：题录与 Zotero 一致；扫描增量仍正确。

---

## Phase 2 — 检索质量（3–6 周）

**部分已有**：FTS + OpenScholar dense + RRF + Reranker；`scholar_embedding_json` 存 SQLite。

**待做**：

- [ ] **LanceDB / Qdrant** 向量持久化（替代全表 dense 扫描）
- [ ] **嵌入抽象**：`bge-m3` 等可切换，维度归一化统一
- [ ] **融合调参**、跨篇配额、chunk 去重
- [ ] **批量「仅补未 indexed」** API

**验收**：千级 chunk 延迟可接受；引用相关性优于纯 FTS。

---

## Phase 3 — 异步管线（2–4 周）

- [ ] 任务队列：`parse` / `index` / `reindex-all`
- [ ] Worker 与 API 分离；MinerU/嵌入并发限制
- [ ] 进度 SSE/WebSocket
- [ ] 结构化日志 / 可选 OpenTelemetry

**验收**：全库重建不拖死 API；前端可见队列与失败原因。

---

## Phase 4 — 综述深化（持续）

**已完成**

- [x] 引用式提示、`build_citation_prompt`
- [x] 流式问答 + 可选双语答案（`BILINGUAL_ANSWER`）
- [x] Markdown/KaTeX
- [x] OpenScholar-8B 经 `OLLAMA_CHAT_MODEL` 切换

**待做**

- [ ] 综述模板（快速 / 结构化 / 对比 / 申请书）
- [ ] 综述双语（与问答一致的 `review_other` / 流式）
- [ ] 导出 Markdown / DOCX；引用表与 chunk 链接
- [ ] `summaries` 表落地，综述先聚合摘要
- [ ] 无证据不断言、引用与 `chunk_id` 对齐校验
- [ ] 针对 OpenScholar-8B 的英文 system 模板调优

---

## Phase 5 — 外部源与深度集成（中长期）

- [ ] Semantic Scholar / OpenAlex / Crossref（DOI 补全，注意条款）
- [ ] **vLLM / Transformers** 直连 OpenScholar-8B（不经 Ollama）
- [ ] ScholarQA 式评测与回归集
- [ ] 魔搭/HF 一键下载脚本维护
- [ ] Mano-P / Cider 等 GUI 自动化（可选）

> **说明**：OpenScholar **Retriever/Reranker** 已在主线实现（Phase 2 子集）；Phase 5 侧重生成侧直连、外部文献源与评测。

---

## 建议优先级

1. **Phase 0 剩余**（CI、错误面、文献库 UX）  
2. **Phase 1 收尾**（标签/集合独立筛选、多附件策略）  
3. **Phase 2**（向量库 + 仅补未索引批量）— 与 PDF 量增长并行  
4. **Phase 3** — PDF 明显增多时  
5. **Phase 4 / 5** — 按需迭代  

主对话已可通过 **`OLLAMA_CHAT_MODEL`** 使用 OpenScholar-8B GGUF；检索已可选官方 Retriever/Reranker。

---

## 模型速查

| 用途 | 推荐 | 配置 |
|------|------|------|
| 主对话 | OpenScholar-8B GGUF 或 qwen 等 | `OLLAMA_CHAT_MODEL` |
| 检索稠密/精排 | OpenScholar Retriever / Reranker | `OPENSCHOLAR_*_ENABLED` |
| 嵌入（回退） | `nomic-embed-text` 等 | `OLLAMA_EMBED_MODEL` |
| 双语翻译 | Hy-MT Q4_K_M GGUF | `TRANSLATION_OLLAMA_MODEL` |

详见 README「模型与检索」。

---

## 文档维护

更新实现时请同步：

- 本文件对应阶段的 **`[x]` / `[ ]` / `[~]`** 与「当前能力」表  
- `README.md` 的功能表、API 表与配置说明  
