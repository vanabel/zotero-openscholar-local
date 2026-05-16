# 架构

## 定位

单人个人科研知识库：将 Zotero 本地 PDF 解析为结构化 Markdown，经分块与检索，支持**文献问答**、**文献综述**与**项目申请书素材**。与 [OpenScholar](https://arxiv.org/abs/2411.14199) 同类「证据检索 + 可核查引用」；LLM 与索引均为本机或自管 API。

```text
PDF 不是知识库；
Markdown 也不是最终知识库；
知识库 = 文献元数据 + 结构化 Markdown + 高质量 chunks + embeddings + summaries + citation map。
```

## 六层

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

## 运行时组件

| 路径 | 职责 |
|------|------|
| `apps/web` | Next.js 14：文献库、问答、综述、设置 |
| `apps/api` | FastAPI、SQLite（`papers` / `chunks` / FTS5）、任务队列 |
| `scripts/dev-mineru-api.sh` | 开发时可选本机 mineru-api（`MINERU_MODE=cli`） |
| `DATA_DIR` | `app.sqlite`、`parsed/{paper_id}/document.md`、缓存 |

## 索引流水线（简图）

```text
~/Zotero/storage/**/*.pdf
        │  scan_storage（sha256 / mtime）
        ▼
   papers 表 + zotero.sqlite 题录同步
        │  index_paper
        ▼
   MinerU cloud/cli 或 pypdf → document.md
        │  analyze_markdown → parse_quality_score
        ▼
   分块 + embedding_json [+ scholar_embedding_json]
        ▼
   chunks + chunks_fts
```

## 检索流水线（简图）

```text
用户问题 →（可选双语扩展）→ FTS 召回
        →（可选）OpenScholar Retriever 稠密召回
        → RRF 融合 → 跨篇配额 → Reranker / Ollama 余弦
        → 引用式 prompt [1][2] → LLM → CitationVerifier / claims
```

## 与 OpenScholar 官方栈的差异

| | 本仓库 | OpenScholar 论文 / OSDS |
|---|--------|-------------------------|
| 文献来源 | Zotero 本地 PDF | 远程论文库 |
| 向量存储 | SQLite + JSON 嵌入（可选 LanceDB 见 ROADMAP） | 专用 datastore |
| 生成模型 | Ollama GGUF / OpenAI 兼容 API | 官方流水线 |

## 模块命名（实现参考）

```text
SourceManager      # zotero_scanner + zotero_sqlite_sync
ParseManager       # indexing + mineru_cloud + parse_quality
ChunkManager       # chunking + chunk_quality
EmbeddingManager   # llm.EmbeddingClient + openscholar_retrieval
TaskManager        # task_queue
RetrievalManager   # retriever
CitationVerifier   # citation_verifier
SummaryManager     # summaries
ReviewWriter       # rag + review_templates
ExportManager      # export_docx
```

详见 [ROADMAP.md](./ROADMAP.md) 各阶段验收项。
