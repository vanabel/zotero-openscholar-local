# Roadmap v2 — 质量目标驱动

**定位**：单人使用的个人科研知识库（Zotero Research Knowledge Base）。核心场景为**文献问答**、**文献综述**、**项目申请书素材整理**。

**投入重点**（第一年不做生成模型微调）：

1. 解析质量  
2. Chunk 质量  
3. 检索质量  
4. 引用可靠性  
5. 综述结构模板  

与 [README.md](../README.md)、[ARCHITECTURE.md](./ARCHITECTURE.md) 交叉维护。

**图例**：`[x]` 已实现；`[~]` 部分实现；`[ ]` 未做。

---

## 架构（六层）

见 [ARCHITECTURE.md](./ARCHITECTURE.md)。

---

## 基线能力（v0.1 MVP，已提交 main）

以下在 `quality-roadmap-v2` 之前的主线已实现，作为质量迭代的起点：

| 领域 | 状态 |
|------|------|
| Zotero 扫描 + 题录同步 | `[x]` |
| MinerU / pypdf 解析、cloud 切片 | `[x]` |
| Markdown 分块 + FTS5 + 嵌入 + OpenScholar dense | `[x]` |
| FTS + RRF + Reranker / Ollama 重排 | `[x]` |
| 问答 / 综述流式、`[n]` 提示、缓存 | `[x]` |
| 双语检索 / 答案（可选） | `[x]` |
| Next.js：概览、文献库、问答、综述、设置 | `[x]` |
| `CHAT_PROVIDER` / `EMBED_PROVIDER` 分离 + `OPENAI_EMBED_MODEL` | `[x]` 见 `.env.example` 组合表 |
| 文献库索引：后台任务队列 + SSE 进度 | `[x]` 见 P6 |
| 文献库 AI 摘要展示 + 任务队列管理面板 | `[x]` 见 P5 / P6 |

---

## P0 — 工程稳定性

**目标**：坏了能发现，错了能定位。

| 任务 | 状态 |
|------|------|
| 统一错误 JSON（LLM / MinerU / OpenScholar / 无 document.md） | `[x]` `app/errors.py` + 全局 handler |
| 文献库：parse/index 失败原因、重试、仅重建索引 | `[x]` `status_message`（含解析降级提示）、`GET /parse-meta`、重试索引/重试解析 |
| document.md / chunk / AI 摘要预览 | `[x]` `GET /papers/{id}/document`、`/chunks`、`/summary` + 文献库展开预览 |
| 最小回归集 fixture（3 英 + 3 中 + 扫描 + 公式 + 图表） | `[x]` 见 [QUALITY_BASELINE.md](./QUALITY_BASELINE.md) |
| CI：`pnpm test` 默认绿，Ollama/MinerU 标 optional | `[x]` `.github/workflows/ci.yml`；`@pytest.mark.optional`；`pnpm test:api:optional` |
| pytest 与开发库 `DATA_DIR` 隔离 | `[x]` `tests/conftest.py` + `test_data_dir_isolation.py` |
| 启动时 SQLite VACUUM（可配置） | `[x]` `db_maintenance.py`；见 [OPERATIONS.md](./OPERATIONS.md) |

**验收**：不启 Ollama 时 API 返回明确 JSON；`pnpm test` 默认通过；pytest 不写入 `apps/api/data`。

---

## P1 — 解析质量

**目标**：`document.md` 可信、可评分、可修复。

| 任务 | 状态 |
|------|------|
| `parse_reports` 表 + `parse_quality_score` | `[x]` `parse_quality.py` + `papers.parse_quality_score` |
| 统计：页数、章节、公式/表/图、OCR 比例、乱码比例 | `[x]` 写入 `parse_reports` |
| Markdown 清洗（页眉页脚、断行、参考文献区） | `[x]` `clean_markdown.py`；解析后写入 `document.md` |
| 前端：section tree、质量分、警告、低质量筛选 | `[x]` 文献库质量徽章、`/papers/quality-summary`、低质量/未评分筛选 |
| 低分重试（cloud / OCR） | `[x]` `parse_retry.py`；云端备用 `MINERU_CLOUD_MODEL_VERSION_RETRY` |

### 「质量 未评分」何时更新

`papers.parse_quality_score` 为 `NULL` 时，文献库显示 **未评分**。写入路径**唯一**：`indexing.index_paper` 在 **`need_parse=true`**（实际跑 MinerU / cloud / pypdf）成功后调用 `analyze_markdown` + `save_parse_report`（`parse_quality.py`）。

| 用户操作 / 条件 | 质量分 |
|-----------------|--------|
| 仅扫描、未索引 | 保持未评分 |
| 建立索引（含首次解析） | 写入 |
| `force=true` 强制重建 | 重新解析后写入（新分覆盖旧分；低于旧分会 `plog` 提示但仍保存） |
| `reindex_only=true` 仅重建索引 | **不**更新（复用 `document.md`，只重做 chunk / 嵌入） |
| 索引复用缓存 Markdown（PDF 未变、`need_parse=false`） | 不重新评分（历史上从未评分的仍为未评分） |
| 升级前已索引的旧数据 | 仍为未评分；可用 **未评分补分**（`POST /papers/rescore-unscored`）或带解析的索引 / `force` |

筛选：`parse_quality_missing` → `parse_quality_score IS NULL`（`zotero_scanner.list_papers`）。低分默认 `parse_quality_lte=0.65`。详见 [CONFIGURATION.md](./CONFIGURATION.md)。

**验收**：可筛低质量与未评分文献；带解析的索引可生成/刷新分；`reindex_only` 不改变质量分。  
**待办**：`force` 解析若低于历史分仍覆盖 — 可选改为「仅当新分更高时更新 `papers.parse_quality_score`」。

---

## P2 — Chunk 质量

**目标**：chunk 为可引用、可检索、可综合的知识单元。

| 任务 | 状态 |
|------|------|
| `chunk_type`（abstract / theorem / proof / references …） | `[x]` `chunk_quality.py` |
| `chunk_quality_score`、`content_hash` | `[x]` 索引时写入 |
| `section_path` 结构化（JSON 路径） | `[x]` `section_path_json` 列 + 层级标题栈；`section_path` 仍为显示串 |
| Chunk 去重（页眉页脚、切片重复） | `[x]` `dedupe_chunk_drafts` 索引级 |
| references-only 不参与普通问答 | `[x]` 检索默认排除 `chunk_type=references` |
| 前端：chunk 来源（标题 + section + 页码） | `[x]` API `source` 字段；问答/综述引用卡片展示章节·页码 |

**验收**：同段不重复进 top-k；定理类可单独检索。

---

## P3 — 检索质量

**目标**：检索准、覆盖全、跨文献均衡。

| 任务 | 状态 |
|------|------|
| 跨篇配额 `RETRIEVE_MAX_CHUNKS_PER_PAPER` | `[x]` |
| 最多文献数 `RETRIEVE_MAX_PAPERS` | `[x]` |
| Chunk 内容去重（检索结果级） | `[x]` `dedupe_chunks_by_text`（`retriever.py`） |
| 查询扩展 / 专名同义词 | `[x]` Hy-MT 双语 + `data/query_synonyms.json` 规则扩展 |
| `eval_queries.jsonl` + 评测脚本 | `[x]` `tests/eval/eval_queries.jsonl`；`scripts/eval_retrieval.py` |
| LanceDB 替代 SQLite 全表 dense 扫描 | `[x]` `lance_store.py`；`LANCEDB_ENABLED`；未安装时回退 SQLite |
| `POST /papers/index-missing` | `[x]` 另含 `parse-missing`、`summarize-missing` |

**验收**：top-k 不被单篇垄断；评测集可回归。

---

## P4 — 引用可靠性

**目标**：关键判断有证据，证据支持判断。

| 任务 | 状态 |
|------|------|
| Evidence locking（`[CHUNK:id]`） | `[x]` prompt 强制 `[CHUNK:id]`；校验后规范为 `[n]` |
| `CitationVerifier`（存在性、关键词、无引用断言） | `[x]` claim 拆分 + 关键词重叠 |
| `answer_citations` 表 + claim 拆分 | `[x]` 生成后写入；API 返回 `claims` |
| 无证据固定降级话术 | `[x]` 无检索片段时固定回复 + 生成后 `[n]` 校验 |
| 前端：verified / insufficient 状态 | `[x]` 问答/综述引用卡片徽章 + 论断核验列表 |

**验收**：每个关键论断可点开 chunk；无证据不编造。

---

## P5 — 综述结构模板

**目标**：科研写作辅助（综述 + 申请书）。

| 模板 | 状态 |
|------|------|
| A. 快速综述 | `[x]` `template=quick_review` |
| B. 结构化综述（研究现状） | `[x]` `template=literature_review` |
| C. 对比综述（表格） | `[x]` `template=comparative_review`（Markdown 表） |
| D. 项目申请书（现状 / 科学问题 / 切入点 / 创新性） | `[x]` `template=grant_proposal` |
| `summaries` 表参与综述（先 summary 再 chunk） | `[x]` `summaries.py` 综述检索优先 |
| 文献库展示 `paper_summary` | `[x]` `GET /papers/{id}/summary`；列表 `has_paper_summary`；展开详情 + 生成摘要 |
| 按标签 / 集合 / 年份限定文献范围 | `[x]` `RetrievalScope` + 问答/综述请求体 |
| 导出 Markdown / DOCX | `[x]` `export-markdown` + `export-docx`（python-docx） |

**验收**：一键出申请书「研究现状」初稿；段段有 `[n]`；可导出。

---

## P6 — 异步与规模化

文献量显著增大（建议 >200 篇）时优先完善；**索引入队与进度查询已起步**。

| 任务 | 状态 |
|------|------|
| SQLite `tasks` 表 + 单 Worker（API 进程内） | `[x]` `enqueue_index_task`；`POST …/index` 返回 `202` + `task_id` |
| 索引进度字段（parse / embed / scholar_embed / save） | `[x]` `progress_json`；`GET /tasks/active`、`GET /tasks/{id}` |
| 文献库前端轮询进度 | `[x]` 索引徽章 `indexing` + 阶段文案 |
| 服务重启恢复未完成任务 | `[x]` 启动时 `queued`/`running` 重新入队 |
| 同步索引（脚本 / 调试） | `[x]` `?wait=true` 或 CLI `reindex_library.py` 直调 `index_paper` |
| 进度 SSE / WebSocket | `[x]` `GET /tasks/active/stream`；文献库 EventSource |
| 任务队列统计与管理 | `[x]` `GET /tasks/stats`；`POST /tasks/cancel-queued`、`cancel-orphans`；文献库 `TaskStatsPanel` |
| `parse-missing` / `index-missing` / `summarize-missing` | `[x]` `POST /papers/*-missing`；摘要任务 `task_type=summarize` |
| 单篇摘要入队 | `[x]` `POST /papers/{id}/summarize` |
| MinerU / 嵌入并发限制（M4 24G） | `[x]` `MINERU_PARSE_CONCURRENCY`、`INDEX_EMBED_CONCURRENCY`、`TASK_WORKER_CONCURRENCY` |
| 独立 Worker 进程 / API 与慢任务分离 | `[x]` `TASK_WORKER_MODE=external` + `scripts/run_task_worker.py`；`pnpm run dev:external` |
| 超算批量向量（SLURM） | `[x]` `chunk_batch` / `embed_batch`（OpenAI API）/ `scholar_embed_batch` + `submit_vectors.slurm`；见 [HPC.md](./HPC.md) |

**索引嵌入说明**（与 `EMBED_PROVIDER` 独立）：

- 始终写入 `embedding_json`（Ollama 或 OpenAI 兼容 API）。
- `OPENSCHOLAR_RETRIEVER_ENABLED=1` 且依赖可用时，额外写入 `scholar_embedding_json`（本机 Retriever）。
- Reranker **不参与**建索引，仅检索阶段使用。

**验收（当前）**：点索引后 API 立即返回；文献库可见阶段进度；批量索引不长时间阻塞 HTTP。  
**验收（完整 P6）**：全库索引时 API 稳定；SSE/WS 进度；失败可重试；并发可配置不拖垮 M4。

---

## P7 — 明确延后

- ScholarQA 大规模评测  
- Transformers 直连 OpenScholar-8B（Ollama 够用）  
- 多用户、shadcn 全面换皮  

### Mano-P / Cider GUI 自动化

**定位**（延后）：端侧 GUI-VLA（[Mano-P](https://github.com/Mininglamp-AI/Mano-P)）+ MLX 推理加速（[Cider](https://github.com/Mininglamp-AI/cider)），通过截图—推理—点击循环操作**无 API** 的桌面/Web 界面。**不替代**本库 `ZOTERO_STORAGE_PATH` + `zotero.sqlite` + MinerU/API 的主数据与索引路径。

| 组件 | 职责 |
|------|------|
| **Mano-P** | 视觉语言动作模型；本地或云推理后驱动键鼠 |
| **Cider** | Apple MLX 量化加速，降低端侧推理延迟 |
| **Mano-Skill / mano-cua** | 对外入口（Agent Skill、CLI；Python SDK 仍开发中） |

**难度评估**（2026-05）：

| 场景 | 难度 | 说明 |
|------|------|------|
| 个人试用、偶发点桌面 | 中～中高 | 需 macOS 辅助功能/录屏权限；官方建议 M4 + **32GB**（本机 P6 按 **24GB** 调并发，叠 GUI-VLA 易抢内存） |
| 稳定接入 `task_queue` / 无人值守批量 | **高** | OSWorld 专项约 58% 成功率；逐步非确定、难回归；CLI/SDK 与本地模型分阶段开源 |
| 替代现有 Zotero/解析/检索链路 | 不推荐 | 与 P1～P5 API/文件路径重叠，可观测性与性价比均劣于现状 |

**与本库关系**：文献扫描、解析、索引、问答/综述均已程序化；GUI 自动化仅在有「必须点客户端、且无 API」的具体场景时值得单独立项（如某投稿站、某桌面插件），且须接受人工兜底。

**若接入时的实现约束**（待做）：

| 任务 | 状态 |
|------|------|
| 明确 1～2 个无 API 替代方案的目标场景与验收 | `[ ]` |
| 与 P6 并发隔离（MinerU / 嵌入 / Ollama 不同时满载） | `[ ]` |
| 程序化调用面稳定（mano-client 或 CLI 落地后再接 Worker） | `[ ]` |
| 失败状态机、日志与半完成回滚（勿并入主 `index` 任务） | `[ ]` |

**参考**：[Mano-P README](https://github.com/Mininglamp-AI/Mano-P)、[Cider](https://github.com/Mininglamp-AI/cider)、[mano-skill](https://github.com/Mininglamp-AI/mano-skill)。

### 外部元数据：Semantic Scholar / OpenAlex

**定位**（延后）：补全 DOI/题录、作者与机构、引用关系、开放获取链接等；**不替代**本库解析 + LanceDB + 本地 Retriever 的主检索路径。

| | **OpenAlex** | **Semantic Scholar (S2)** |
|---|---|---|
| API 费用 | 免费（网站、API、月度快照） | 免费公开 API（无订阅费） |
| 数据许可 | **[CC0](https://creativecommons.org/publicdomain/zero/1.0/)**，可自由使用与再分发 | 字段/来源各异，常见 **CC BY-NC**、**ODC-BY**；第三方内容另有许可 |
| 免费 API 限额 | **10 万次/天**，最高 **10 QPS** | 无 key：与所有未认证用户共享配额；**有 key：全端点约 1 QPS**（可申请略提高） |
| 超额 / 大规模 | Premium / Institutional（更高限额、小时级同步） | 建议 [Datasets API](https://api.semanticscholar.org/api-docs/datasets) 本地下载，勿猛打 REST |
| 商用 | CC0 对商用较友好 | 须核对 **BY-NC** 等；[API 协议](https://www.semanticscholar.org/product/api/license) 禁止转售/再包装 API |
| 合规要点 | 遵守 [ToS](https://openalex.org/OpenAlex_termsofservice.pdf)；避免滥用与过高负载 | 须署名「Semantic Scholar」；遵守速率限制；API 可随时变更或终止（无商业 SLA） |

**若接入时的实现约束**（待做）：

| 任务 | 状态 |
|------|------|
| 优先 OpenAlex：元数据 / 作者 / 机构补全 | `[ ]` |
| S2：引用、推荐、摘要等；注意 NC 许可与低 QPS | `[ ]` |
| 客户端：速率限制、本地缓存、失败重试、来源标注 | `[ ]` |
| 全库批量前评估配额（OpenAlex 10 万/天、S2 1 QPS 或 dataset） | `[ ]` |

**参考**：[OpenAlex Pricing](https://ourresearch.gitbook.io/help.openalex.org/pricing)、[S2 API 教程](https://www.semanticscholar.org/product/api/tutorial)、[S2 API License](https://www.semanticscholar.org/product/api/license)。

---

## 优先级（执行顺序）

```text
P0  错误面 + 文献库 UX + 测试基线 + 数据隔离
P1  解析质量评分 + Markdown 预览
P2  chunk 类型、去重、references 过滤
P3  检索调参 + 评测集（配额已起步）→ LanceDB
P4  citation verifier + no-evidence-no-claim
P5  四类综述模板 + summaries + 导出
P6  异步队列完善（SSE、missing-*、并发限制、独立 Worker）
P7  外部源与实验性功能
```

---

## 模块命名（实现参考）

```text
SourceManager      # Zotero PDF + sqlite
ParseManager       # MinerU + parse_reports
CleanMarkdown      # 清洗
ChunkManager       # 分块与类型
EmbeddingManager   # embedding_json + scholar_embedding_json
TaskManager        # tasks 队列（index）；见 app/services/task_queue.py
RetrievalManager   # FTS + dense + RRF + quota
EvidenceManager    # 证据锁定
CitationVerifier   # 引用校验
SummaryManager     # 论文摘要
ReviewWriter       # 综述生成
ExportManager      # Markdown / DOCX
```

---

## 文档维护

变更实现时请同步：

- 本文件对应阶段的 `[x]` / `[ ]` / `[~]`  
- [README.md](../README.md) 功能概览  
- [CONFIGURATION.md](./CONFIGURATION.md)、[API.md](./API.md)、[OPERATIONS.md](./OPERATIONS.md)（若行为变更）  
- `apps/api/.env.example`  
- [QUALITY_BASELINE.md](./QUALITY_BASELINE.md) 回归集与评测查询  
