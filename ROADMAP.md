# Roadmap v2 — 质量目标驱动

**定位**：单人使用的个人科研知识库（Zotero Research Knowledge Base）。核心场景为**文献问答**、**文献综述**、**项目申请书素材整理**。

**投入重点**（第一年不做生成模型微调）：

1. 解析质量  
2. Chunk 质量  
3. 检索质量  
4. 引用可靠性  
5. 综述结构模板  

与 [README.md](./README.md) 交叉维护。历史功能向规划见 [chatgpt.md](./chatgpt.md)；本版路线细节见 [chatgpt2.md](./chatgpt2.md)。

**图例**：`[x]` 已实现；`[~]` 部分实现；`[ ]` 未做。

---

## 架构（六层）

```text
┌─────────────────────────────────────────┐
│ 6. 应用层：问答 / 综述 / 申请书 / 导出   │
└─────────────────────────────────────────┘
                    ▲
┌─────────────────────────────────────────┐
│ 5. 生成与引用：Evidence + CitationVerifier│
└─────────────────────────────────────────┘
                    ▲
┌─────────────────────────────────────────┐
│ 4. 检索：FTS + dense + RRF + quota + rerank│
└─────────────────────────────────────────┘
                    ▲
┌─────────────────────────────────────────┐
│ 3. 知识组织：chunks + summaries          │
└─────────────────────────────────────────┘
                    ▲
┌─────────────────────────────────────────┐
│ 2. 解析与清洗：MinerU + parse_reports    │
└─────────────────────────────────────────┘
                    ▲
┌─────────────────────────────────────────┐
│ 1. 数据源：Zotero storage + zotero.sqlite │
└─────────────────────────────────────────┘
```

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
| 文献库索引：后台任务队列 + 轮询进度 | `[~]` 见 P6 |

---

## P0 — 工程稳定性

**目标**：坏了能发现，错了能定位。

| 任务 | 状态 |
|------|------|
| 统一错误 JSON（LLM / MinerU / OpenScholar / 无 document.md） | `[x]` `app/errors.py` + 全局 handler |
| 文献库：parse/index 失败原因、重试、仅重建索引 | `[~]` `status_message`、重试/仅重建索引按钮；parse 失败仍弱 |
| document.md / chunk 预览 | `[x]` `GET /papers/{id}/document`、`/chunks` + 文献库展开预览 |
| 最小回归集 fixture（3 英 + 3 中 + 扫描 + 公式 + 图表） | `[x]` 见 [docs/QUALITY_BASELINE.md](./docs/QUALITY_BASELINE.md) |
| CI：`pnpm test` 默认绿，Ollama/MinerU 标 optional | `[ ]` |

**验收**：不启 Ollama 时 API 返回明确 JSON；`pnpm test` 默认通过。

---

## P1 — 解析质量

**目标**：`document.md` 可信、可评分、可修复。

| 任务 | 状态 |
|------|------|
| `parse_reports` 表 + `parse_quality_score` | `[ ]` |
| 统计：页数、章节、公式/表/图、OCR 比例、乱码比例 | `[ ]` |
| Markdown 清洗（页眉页脚、断行、参考文献区） | `[ ]` |
| 前端：section tree、质量分、警告、低质量筛选 | `[ ]` |
| 低分重试（cloud / OCR） | `[ ]` |

**验收**：可筛低质量 PDF；`force` 不覆盖更高分结果。

---

## P2 — Chunk 质量

**目标**：chunk 为可引用、可检索、可综合的知识单元。

| 任务 | 状态 |
|------|------|
| `chunk_type`（abstract / theorem / proof / references …） | `[ ]` |
| `chunk_quality_score`、`content_hash` | `[ ]` |
| `section_path` 结构化（JSON 路径） | `[~]` 已有字符串 `section_path` |
| Chunk 去重（页眉页脚、切片重复） | `[ ]` |
| references-only 不参与普通问答 | `[ ]` |
| 前端：chunk 来源（标题 + section + 页码） | `[~]` 引用卡片有部分字段 |

**验收**：同段不重复进 top-k；定理类可单独检索。

---

## P3 — 检索质量

**目标**：检索准、覆盖全、跨文献均衡。

| 任务 | 状态 |
|------|------|
| 跨篇配额 `RETRIEVE_MAX_CHUNKS_PER_PAPER` | `[x]` |
| 最多文献数 `RETRIEVE_MAX_PAPERS` | `[x]` |
| Chunk 内容去重（检索结果级） | `[x]` `dedupe_chunks_by_text` in `retriever.py` |
| 查询扩展 / 专名同义词 | `[~]` 双语 Hy-MT 扩展已有 |
| `eval_queries.jsonl` + 评测脚本 | `[ ]` |
| LanceDB 替代 SQLite 全表 dense 扫描 | `[ ]` |
| `POST /papers/index-missing` | `[ ]` |

**验收**：top-k 不被单篇垄断；评测集可回归。

---

## P4 — 引用可靠性

**目标**：关键判断有证据，证据支持判断。

| 任务 | 状态 |
|------|------|
| Evidence locking（`[CHUNK:id]`） | `[~]` prompt 含 chunk_id，未强制对齐 |
| `CitationVerifier`（存在性、关键词、无引用断言） | `[~]` `citation_verifier.py`：`[n]` 越界校验；claim 拆分未做 |
| `answer_citations` 表 + claim 拆分 | `[ ]` |
| 无证据固定降级话术 | `[x]` 无检索片段时固定回复 + 生成后 `[n]` 校验 |
| 前端：verified / insufficient 状态 | `[ ]` |

**验收**：每个关键论断可点开 chunk；无证据不编造。

---

## P5 — 综述结构模板

**目标**：科研写作辅助（综述 + 申请书）。

| 模板 | 状态 |
|------|------|
| A. 快速综述 | `[ ]` |
| B. 结构化综述（研究现状） | `[~]` 当前单一综述 prompt |
| C. 对比综述（表格） | `[ ]` |
| D. 项目申请书（现状 / 科学问题 / 切入点 / 创新性） | `[x]` `template=grant_proposal` |
| `summaries` 表参与综述（先 summary 再 chunk） | `[ ]` |
| 按标签 / 集合 / 年份限定文献范围 | `[~]` 检索仍全库，题录筛选弱 |
| 导出 Markdown / DOCX | `[~]` `POST /review/export-markdown`；DOCX 未做 |

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
| 进度 SSE / WebSocket | `[ ]` 当前为 HTTP 轮询 |
| `parse-missing` / `index-missing` / `summarize-missing` | `[ ]` |
| MinerU / 嵌入并发限制（M4 24G） | `[ ]` Worker 串行 1；OpenScholar 与 Ollama embed 仍顺序执行 |
| 独立 Worker 进程 / API 与慢任务分离 | `[ ]` |

**索引嵌入说明**（与 `EMBED_PROVIDER` 独立）：

- 始终写入 `embedding_json`（Ollama 或 OpenAI 兼容 API）。
- `OPENSCHOLAR_RETRIEVER_ENABLED=1` 且依赖可用时，额外写入 `scholar_embedding_json`（本机 Retriever）。
- Reranker **不参与**建索引，仅检索阶段使用。

**验收（当前）**：点索引后 API 立即返回；文献库可见阶段进度；批量索引不长时间阻塞 HTTP。  
**验收（完整 P6）**：全库索引时 API 稳定；SSE/WS 进度；失败可重试；并发可配置不拖垮 M4。

---

## P7 — 明确延后

- Mano-P / Cider GUI 自动化  
- ScholarQA 大规模评测、外部 Semantic Scholar / OpenAlex  
- Transformers 直连 OpenScholar-8B（Ollama 够用）  
- 多用户、shadcn 全面换皮  

---

## 优先级（执行顺序）

```text
P0  错误面 + 文献库 UX + 测试基线
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
- `README.md` 功能表与配置项（`CHAT_PROVIDER`、`EMBED_PROVIDER`、`RETRIEVE_MAX_*` 等）  
- `apps/api/.env.example` 推荐组合表与索引嵌入说明  
- `docs/QUALITY_BASELINE.md` 回归集与评测查询  
