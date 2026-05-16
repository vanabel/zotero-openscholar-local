可以做，而且很适合你这台 **MacBook M4 24G** 做一个“本地文献智能体”的原型。但架构上要注意：**Mano-P / Cider 不应作为第一版核心依赖**，更合理的是把它们放在“端侧推理与 GUI 自动化增强层”。第一版应先完成：

> Zotero PDF 目录扫描 → MinerU 解析 PDF 为 Markdown/JSON → 文献元数据抽取 → 分块 → embedding → 向量数据库 → OpenScholar/RAG 风格问答 → 带引用的文献综述生成。

Mano-P 是端侧 GUI-VLA 智能体，定位是通过视觉理解和操作桌面/网页 GUI；Cider 则面向 Apple Silicon 和 MLX，目标是提升端侧推理效率、降低内存占用。它们对“自动操作 Zotero、浏览器、文件管理器”等很有潜力，但你的核心任务其实是**文献解析 + 检索增强生成**，不依赖 GUI 自动化也能完成。([新浪财经][1])

---

## 一、总体判断

建议项目命名为：

```text
zotero-openscholar-local
```

核心目标：

```text
将 ~/Zotero/storage/ 中的 PDF 自动解析为结构化 Markdown，
建立本地文献向量库，
并提供一个网页应用，让用户用自然语言进行文献问答、综述生成、证据追踪。
```

这个方案是可行的，因为：

1. **MinerU 正适合作为 PDF → Markdown/JSON 的解析层**。它支持 PDF、Office 文档和图片输入，能输出 Markdown、JSON，支持公式转 LaTeX、表格转 HTML、OCR、多栏排版、标题段落结构保留等能力。([GitHub][2])
2. **OpenScholar 的思想正适合文献综述式问答**。OpenScholar 本身是面向 scientific literature synthesis 的 RAG 模型，强调检索、综合和可验证引用。([GitHub][3])
3. **Mac M4 24G 可以承担本地原型开发**。特别是 embedding、向量检索、轻量本地 LLM 都可以跑；较大的生成模型可先通过 Ollama/MLX 或云端 API 混合使用。Ollama 也已在 Apple Silicon 上预览 MLX 支持，以利用统一内存架构提升性能。([Ollama][4])

---

## 二、推荐架构

整体分为 7 层。

```text
┌──────────────────────────────────────────────┐
│  Web UI: 文献对话 / 综述生成 / 引用查看          │
│  Next.js / React / Tailwind                   │
└──────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────┐
│  API Layer: FastAPI                           │
│  /scan /parse /index /chat /review /papers    │
└──────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────┐
│  Agent Layer                                  │
│  Query Planner / Retriever / Reranker / Writer│
│  OpenScholar-style RAG                        │
└──────────────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
┌──────────────────┐    ┌──────────────────────┐
│ Vector DB         │    │ Metadata DB           │
│ Qdrant / LanceDB  │    │ SQLite / DuckDB       │
└──────────────────┘    └──────────────────────┘
        ▲                       ▲
        │                       │
┌──────────────────────────────────────────────┐
│  Indexing Pipeline                            │
│  chunking / embedding / citation mapping      │
└──────────────────────────────────────────────┘
                    ▲
                    │
┌──────────────────────────────────────────────┐
│  Document Parsing Layer                       │
│  Zotero PDF → MinerU → Markdown / JSON         │
└──────────────────────────────────────────────┘
                    ▲
                    │
┌──────────────────────────────────────────────┐
│  Source Layer                                 │
│  ~/Zotero/storage/**.pdf                       │
│  Zotero SQLite metadata                        │
└──────────────────────────────────────────────┘
```

---

## 三、技术选型

### 1. 前端

推荐：

```text
Next.js + React + Tailwind + shadcn/ui
```

功能页面：

```text
/
  首页：系统状态、文献数量、索引状态

/library
  文献库：标题、作者、年份、期刊、标签、是否已解析、是否已索引

/chat
  文献问答：支持引用、来源片段、跳转原文

/review
  文献综述生成：主题、时间范围、关键词、输出结构

/settings
  Zotero 路径、模型设置、embedding 设置、MinerU 设置
```

---

### 2. 后端

推荐：

```text
FastAPI + Python
```

理由：

* MinerU、embedding、向量数据库生态更适合 Python；
* 后续接 OpenScholar 代码更方便；
* Cursor 生成 FastAPI 项目比较稳定。

API 初稿：

```text
GET  /health

POST /scan
扫描 ~/Zotero/storage/ 下的 PDF

POST /parse
调用 MinerU 解析指定 PDF

POST /index
对 Markdown 分块、embedding、写入向量库

POST /chat
基于检索结果进行问答

POST /review
生成文献综述

GET  /papers
列出文献

GET  /papers/{paper_id}
查看某篇文献详情

GET  /chunks/{chunk_id}
查看原文片段
```

---

### 3. Zotero 接入

Zotero 的 PDF 一般在：

```bash
~/Zotero/storage/
```

每篇文献可能类似：

```text
~/Zotero/storage/2RHASF9D/paper.pdf
~/Zotero/storage/AB3I42UA/article.pdf
```

第一版不要直接改 Zotero 数据库，只读即可。

建议扫描：

```text
~/Zotero/storage/**/*.pdf
```

同时读取 Zotero 的 SQLite 元数据：

```text
~/Zotero/zotero.sqlite
```

可以提取：

```text
title
authors
year
publication
DOI
abstract
tags
collections
file_path
zotero_item_key
```

但第一版可以先只做 PDF 文件扫描，然后用 MinerU 或 GROBID/LLM 从首页抽取标题作者。

---

### 4. PDF 解析层

推荐使用：

```text
MinerU
```

输出保存为：

```text
data/parsed/{paper_id}/document.md
data/parsed/{paper_id}/document.json
data/parsed/{paper_id}/images/
data/parsed/{paper_id}/meta.json
```

MinerU 的优势是它不仅能转 Markdown，还支持公式 LaTeX、表格 HTML、OCR、多栏文献阅读顺序恢复等，对数学论文尤其重要。([GitHub][2])

需要注意：

* 数学论文中公式、图表、定理环境不一定完全可靠；
* scanned PDF 会更慢；
* 第一次解析大量 Zotero 文献会非常耗时；
* MacBook M4 24G 上建议采用**任务队列 + 增量解析**，不要一次解析全部文献。

---

### 5. 分块策略

数学/科研文献不能简单按固定 token 分块。建议采用“结构优先 + token 限制”的混合分块。

优先级：

```text
Title
Abstract
Introduction
Preliminaries
Definitions
Theorems
Proofs
Experiments
Conclusion
References
```

分块规则：

```text
chunk_size: 800–1200 tokens
chunk_overlap: 120–200 tokens
保留 section_path
保留 page_range
保留 equation/table/figure 标记
保留 paper_id
保留 citation_key
```

chunk 数据结构：

```json
{
  "chunk_id": "paper123_sec2_chunk04",
  "paper_id": "paper123",
  "title": "Energy identity for alpha-Yang-Mills-Higgs fields",
  "authors": ["..."],
  "year": 2025,
  "section": "2. Preliminaries",
  "page_start": 3,
  "page_end": 4,
  "text": "...",
  "markdown": "...",
  "embedding_model": "bge-m3",
  "source_path": "~/Zotero/storage/..."
}
```

---

### 6. 向量数据库

Mac 本地第一版推荐：

```text
LanceDB
```

理由：

* 本地文件型数据库；
* 不需要额外 Docker；
* 适合个人 Zotero 文献库；
* Cursor 搭建简单。

如果后续要多用户、服务化、NAS 部署，可切换：

```text
Qdrant
```

建议第一版：

```text
LanceDB + SQLite
```

目录：

```text
data/
  lancedb/
  app.sqlite
  parsed/
  cache/
```

---

### 7. Embedding 模型

考虑你有中文、英文、数学文献，推荐顺序：

#### 首选：本地 embedding

```text
BAAI/bge-m3
```

优点：

* 多语言；
* 对中文、英文都比较稳；
* 适合文献检索。

缺点：

* 比小模型慢；
* 首次加载占内存。

#### 轻量备选

```text
nomic-embed-text
mxbai-embed-large
```

可以通过 Ollama 管理。

第一版建议：

```text
embedding_model = "BAAI/bge-m3"
```

如果性能吃紧，再切换为：

```text
embedding_model = "nomic-embed-text"
```

---

## 四、OpenScholar 应如何放入架构？

不要简单理解为“直接调用 OpenScholar 就能对你的 Zotero PDF 对话”。更准确地说：

> OpenScholar 可以作为“文献综合问答范式”和“生成模型/提示词/评估方法”的参考或组件；你的 Zotero 文献库需要自己构建本地 retrieval index。

OpenScholar 的官方仓库说明它是面向 scientific literature synthesis 的 RAG 系统，并提供代码、模型检查点和数据资源。([GitHub][3]) Ai2 对它的介绍也强调其核心是：检索相关论文、综合回答、并给出可验证引用。([allenai.org][5])

因此建议分两步：

### 第一版：OpenScholar-style RAG

先实现：

```text
local retriever + reranker + citation-aware answer prompt
```

即：

```text
用户问题
  ↓
查询改写
  ↓
向量检索 top_k=30
  ↓
重排序 top_k=8
  ↓
构造带引用上下文
  ↓
LLM 生成回答
  ↓
返回引用片段
```

### 第二版：接入 OpenScholar 模型或代码

再考虑：

```text
OpenScholar checkpoint
OpenScholar reranking logic
ScholarQA-style evaluation
Semantic Scholar API 补充开放文献
```

---

## 五、LLM 推理方案

在 MacBook M4 24G 上，建议采用分层策略。

### 方案 A：本地优先

```text
Ollama / LM Studio / mlx-lm
```

可选模型：

```text
Qwen2.5-7B-Instruct
Qwen3-8B
Llama-3.1-8B
DeepSeek-R1-Distill-Qwen-7B
```

适合：

```text
单篇论文问答
局部综述
提取摘要
提取定理/定义
中文改写
```

不适合：

```text
超长文献综述
几十篇论文的深度比较
高质量英文综述终稿
```

### 方案 B：混合模式

本地做：

```text
PDF 解析
embedding
向量检索
初步摘要
```

云端做：

```text
最终综述生成
复杂推理
长上下文整合
```

这是最稳妥的。尤其你要做“文献综述”时，真正耗费的是长上下文综合能力，而不是检索本身。

### 方案 C：Cider / MLX 增强

Cider 面向 Apple Silicon 和 MLX，强调 W8A8、W4A8 等推理路径，可降低内存并提升推理速度。([新浪财经][1]) 但它目前更适合放在后续优化阶段。第一版不建议强依赖 Cider，否则 Cursor 搭建复杂度会明显上升。

---

## 六、Mano-P 的合理位置

Mano-P 不适合作为第一版文献 RAG 的核心。它更适合作为未来增强模块：

```text
1. 自动打开 Zotero；
2. 自动导出选中文献；
3. 自动根据 GUI 操作文献管理软件；
4. 自动在浏览器中查找 DOI、arXiv、Semantic Scholar 页面；
5. 自动下载开放版本 PDF；
6. 自动补全文献元数据。
```

换言之：

```text
核心系统：文件级管道 + RAG
增强系统：Mano-P GUI Agent
```

不要一开始就让 Mano-P 操作 Zotero。那会引入：

```text
屏幕权限
稳定性问题
误操作风险
GUI 状态不可控
调试困难
```

---

## 七、性能设计：MacBook M4 24G

你的机器适合：

```text
个人文献库级别：几百到几千篇 PDF
本地 embedding
本地向量检索
轻量模型问答
小规模综述生成
```

不适合：

```text
一次性解析上万篇 PDF
同时跑大模型 + MinerU + embedding + 前端热更新
本地运行 30B 以上模型做长综述
```

### 关键性能策略

#### 1. 增量解析

不要每次重新处理全部 Zotero 文件。

对每个 PDF 计算：

```text
file_path
file_size
mtime
sha256
```

如果未变化，则跳过。

```python
if sha256 in parsed_cache:
    skip_parse()
else:
    run_mineru()
```

#### 2. 后台任务队列

使用：

```text
FastAPI + Celery/RQ/Arq
```

第一版可以用：

```text
SQLite task table + Python worker
```

任务状态：

```text
pending
parsing
parsed
indexing
indexed
failed
```

#### 3. 限制并发

MacBook M4 24G 建议：

```text
MinerU parsing workers: 1
Embedding workers: 1–2
LLM generation: 1
```

尤其不要一边 MinerU OCR，一边跑 8B 模型长文本生成。

#### 4. 分阶段任务

建议把流程拆成：

```text
scan
parse
extract_metadata
chunk
embed
index
```

而不是一个任务做完全部。

#### 5. 缓存一切

缓存：

```text
PDF hash
MinerU markdown
chunks
embeddings
retrieval results
paper summaries
section summaries
```

尤其是 section summary 很重要。文献综述时不应每次直接读取所有原文 chunk，而应先用：

```text
paper-level summary
section-level summary
key claims
key theorems
method summary
```

---

## 八、数据模型设计

### papers 表

```sql
CREATE TABLE papers (
    id TEXT PRIMARY KEY,
    zotero_key TEXT,
    title TEXT,
    authors TEXT,
    year INTEGER,
    venue TEXT,
    doi TEXT,
    arxiv_id TEXT,
    pdf_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    parse_status TEXT,
    index_status TEXT,
    created_at TEXT,
    updated_at TEXT
);
```

### chunks 表

```sql
CREATE TABLE chunks (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    section_title TEXT,
    section_path TEXT,
    page_start INTEGER,
    page_end INTEGER,
    chunk_index INTEGER,
    text TEXT,
    token_count INTEGER,
    embedding_id TEXT,
    FOREIGN KEY(paper_id) REFERENCES papers(id)
);
```

### summaries 表

```sql
CREATE TABLE summaries (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    summary_type TEXT,
    content TEXT,
    model TEXT,
    created_at TEXT,
    FOREIGN KEY(paper_id) REFERENCES papers(id)
);
```

### tasks 表

```sql
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    task_type TEXT,
    paper_id TEXT,
    status TEXT,
    error TEXT,
    created_at TEXT,
    updated_at TEXT
);
```

---

## 九、问答流程设计

用户问：

```text
请总结 α-Yang-Mills-Higgs fields 的能量恒等式相关文献。
```

系统流程：

```text
1. Query understanding
   - 识别主题：alpha-Yang-Mills-Higgs
   - 识别任务：literature review
   - 识别输出：总结、比较、引用

2. Query expansion
   - α-Yang-Mills-Higgs
   - alpha-Yang-Mills-Higgs
   - energy identity
   - no-neck property
   - bubbling
   - Sacks-Uhlenbeck approximation

3. Retrieval
   - 向量检索 top 50
   - 关键词 BM25 top 50
   - 合并去重

4. Reranking
   - 按相关性、年份、标题、摘要、section 权重重排

5. Evidence packing
   - 每篇文献最多取 2–4 个 chunk
   - 避免单篇文献支配上下文

6. Generation
   - 生成带引用综述
   - 每个关键判断必须绑定 paper_id/chunk_id

7. Citation rendering
   - [Ai-Li-Zhu 2025, §2, p.3]
   - 点击可查看原文片段
```

---

## 十、文献综述生成功能

建议设计 4 种模式。

### 1. 快速综述

```text
输入：主题
输出：1000–1500 字中文综述
```

### 2. 结构化综述

```text
输入：主题 + 研究问题
输出：
1. 研究背景
2. 主要方法
3. 关键结果
4. 技术路线
5. 未解决问题
6. 与本人研究的关系
```

### 3. 对比综述

```text
输入：若干篇文献
输出：
- 问题设置
- 方法差异
- 假设条件
- 主要定理
- 技术工具
- 局限性
```

### 4. 项目申请书模式

这个对你尤其有用：

```text
输入：主题 + 研究方向
输出：
- 国内外研究现状
- 科学问题
- 技术路线
- 创新点
- 参考文献线索
```

---

## 十一、项目目录结构

建议 Cursor 直接按这个结构生成：

```text
zotero-openscholar-local/
  README.md
  docker-compose.yml
  .env.example

  apps/
    web/
      package.json
      app/
      components/
      lib/

    api/
      pyproject.toml
      app/
        main.py
        config.py
        db.py

        routers/
          health.py
          scan.py
          parse.py
          index.py
          chat.py
          review.py
          papers.py

        services/
          zotero_scanner.py
          mineru_service.py
          metadata_extractor.py
          chunker.py
          embedding_service.py
          vector_store.py
          retriever.py
          reranker.py
          rag_pipeline.py
          review_writer.py

        models/
          paper.py
          chunk.py
          task.py

        workers/
          worker.py

  data/
    app.sqlite
    parsed/
    lancedb/
    cache/

  scripts/
    scan_zotero.py
    parse_one.py
    index_all.py
    dev_reset.py

  docs/
    architecture.md
    cursor_tasks.md
```

---

## 十二、最小可行版本 MVP

第一阶段不要追求“大而全”。MVP 只做 6 件事。

### MVP-1：扫描 Zotero PDF

```text
输入：~/Zotero/storage/
输出：papers 表
```

功能：

```text
- 找到所有 PDF
- 计算 hash
- 记录文件路径
- 显示在网页 library 页面
```

### MVP-2：单篇 PDF 解析

```text
输入：某个 PDF
输出：Markdown
```

功能：

```text
- 调用 MinerU
- 保存 document.md
- 在网页查看解析结果
```

### MVP-3：分块与 embedding

```text
输入：document.md
输出：chunks + vector index
```

功能：

```text
- Markdown 分块
- 生成 embedding
- 写入 LanceDB
```

### MVP-4：单库问答

```text
输入：用户问题
输出：带来源片段的回答
```

功能：

```text
- 检索 top_k chunks
- 调用 LLM
- 显示引用
```

### MVP-5：文献综述

```text
输入：主题
输出：结构化综述
```

功能：

```text
- 检索相关文献
- 按文献聚合
- 生成综述
```

### MVP-6：增量更新

```text
输入：新增/修改 PDF
输出：只处理变化文件
```

---

## 十三、Cursor 开发任务清单

可以直接把下面这段给 Cursor。

```text
请为我创建一个本地优先的 Zotero 文献 RAG 网页应用，项目名为 zotero-openscholar-local。

技术栈：
- Frontend: Next.js + React + Tailwind + shadcn/ui
- Backend: FastAPI + Python
- Local DB: SQLite
- Vector DB: LanceDB
- PDF parser: MinerU CLI wrapper
- Embedding: bge-m3 initially, with pluggable embedding interface
- LLM: Ollama-compatible chat interface initially, with OpenAI-compatible fallback

目标：
用户提供 Zotero PDF 目录，默认为 ~/Zotero/storage/。系统扫描所有 PDF，解析为 Markdown，分块，embedding，建立本地向量库，并提供网页问答和文献综述功能。

请先生成以下内容：
1. 完整 monorepo 目录结构；
2. FastAPI 后端基础服务；
3. SQLite 数据表：papers, chunks, tasks, summaries；
4. Zotero PDF scanner，递归扫描 ~/Zotero/storage/**/*.pdf；
5. MinerU service wrapper，支持 parse_one(pdf_path)；
6. Markdown chunker，按标题和 token 长度分块；
7. LanceDB vector store；
8. Embedding service 抽象接口；
9. RAG pipeline：retrieve -> build context -> generate answer；
10. Next.js 前端页面：
   - /
   - /library
   - /chat
   - /review
   - /settings

请注意：
- 所有耗时任务都要设计成可后台执行；
- 每个 PDF 用 sha256 判断是否需要重新解析；
- 不要一次性解析全部 PDF；
- 第一版只支持单用户本地运行；
- 所有文件和索引都保存在 ./data 目录；
- 回答必须带引用 chunk；
- 代码要清晰、模块化，方便以后接入 OpenScholar、Mano-P、Cider。
```

---

## 十四、建议的第一版运行方式

```bash
git clone <your-project>
cd zotero-openscholar-local

cp .env.example .env
```

`.env` 示例：

```bash
ZOTERO_STORAGE_PATH=/Users/vanabel/Zotero/storage
DATA_DIR=./data

VECTOR_DB=lancedb
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=BAAI/bge-m3

LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b

MINERU_MODE=cli
MINERU_OUTPUT_DIR=./data/parsed
```

启动：

```bash
cd apps/api
uvicorn app.main:app --reload --port 8000
```

```bash
cd apps/web
npm run dev
```

---

## 十五、后续升级路线

### Phase 1：本地文献库 RAG

```text
Zotero PDF → MinerU → Markdown → embedding → chat
```

### Phase 2：文献综述智能体

```text
query planning
multi-step retrieval
paper-level summary
theme clustering
citation-aware writing
```

### Phase 3：OpenScholar 增强

```text
接入 OpenScholar checkpoint / reranker / evaluation
引入 ScholarQA-style benchmark
增强 citation faithfulness
```

### Phase 4：外部学术检索

```text
Semantic Scholar
arXiv
Crossref
OpenAlex
Google Scholar 手动辅助
```

### Phase 5：Mano-P GUI 自动化

```text
自动操作 Zotero
自动下载开放 PDF
自动补全 DOI
自动整理标签
```

### Phase 6：Cider / MLX 推理优化

```text
本地 VLM
本地 GUI agent
端侧高性能推理
低内存模型部署
```

---

## 十六、关键取舍

我的建议是：

```text
第一版不要把 Mano-P / Cider / OpenScholar 全部硬塞进核心架构。
```

更稳的路线是：

```text
核心主线：
Zotero PDF → MinerU → Markdown → embedding → vector DB → RAG chat

OpenScholar：
作为文献综合问答范式和后续模型增强层

Mano-P：
作为 GUI 自动化增强层

Cider：
作为 Apple Silicon 端侧推理优化层
```

这样 Cursor 可以马上开始搭建，而且每一步都有明确可验证的结果。第一版成功标准不是“像 OpenScholar 一样强”，而是：

```text
能扫描你的 Zotero 文献；
能解析 PDF；
能建立索引；
能基于本地文献回答问题；
能生成带引用的初步文献综述。
```

这就是一个非常合理、可持续迭代的本地科研文献智能体雏形。

[1]: https://finance.sina.com.cn/jjxw/2026-05-06/doc-inhwxxke8315899.shtml "双料齐发！明略科技(2718.HK)正式开源 Cider 端侧推理加速框架与 Mano-P 端侧模型_新浪财经_新浪网"
[2]: https://github.com/opendatalab/mineru "GitHub - opendatalab/MinerU: Transforms complex documents like PDFs and Office docs into LLM-ready markdown/JSON for your Agentic workflows. · GitHub"
[3]: https://github.com/akariasai/openscholar "GitHub - AkariAsai/OpenScholar: This repository includes the official implementation of OpenScholar: Synthesizing Scientific Literature with Retrieval-augmented LMs. · GitHub"
[4]: https://ollama.com/blog/mlx "Ollama is now powered by MLX on Apple Silicon in preview · Ollama Blog"
[5]: https://allenai.org/blog/nature-openscilm "Now in Nature: Synthesizing scientific literature with retrieval-augmented LMs  | Ai2"



对，**不应该重复扫描和重复解析**。正确设计是：把扫描到的 Zotero PDF 作为一个“本地知识库”持久化存储，后续只做**增量更新**。

核心逻辑是：

```text
第一次运行：
扫描 ~/Zotero/storage/
→ 记录 PDF 路径、文件大小、修改时间、sha256
→ MinerU 解析
→ Markdown 入库
→ 分块
→ embedding
→ 写入向量数据库

以后运行：
重新扫描目录
→ 只比较文件状态
→ 未变化：跳过
→ 新增 PDF：解析并入库
→ 修改 PDF：重新解析、重新分块、重新 embedding
→ 删除 PDF：标记为 deleted 或 archived
```

建议不要理解为“每次扫描都重建知识库”，而是：

```text
扫描 = 发现变化
知识库 = 持久存储结果
```

可以用 `sha256` 判断文件内容是否真正变化，比只看修改时间更可靠。

数据库中至少要保存：

```sql
CREATE TABLE papers (
    id TEXT PRIMARY KEY,
    pdf_path TEXT NOT NULL,
    file_name TEXT,
    file_size INTEGER,
    mtime REAL,
    sha256 TEXT NOT NULL,
    parse_status TEXT,
    index_status TEXT,
    deleted INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
);
```

后续扫描时：

```python
def should_reprocess(pdf_path, old_record):
    current_size = get_file_size(pdf_path)
    current_mtime = get_mtime(pdf_path)

    if old_record is None:
        return True

    if current_size != old_record.file_size:
        return True

    if current_mtime != old_record.mtime:
        current_sha256 = compute_sha256(pdf_path)
        return current_sha256 != old_record.sha256

    return False
```

更完整的知识库结构可以这样设计：

```text
data/
  app.sqlite              # 文献元数据、任务状态、chunk 信息
  parsed/
    paper_id/
      document.md         # MinerU 解析结果
      document.json
      images/
      meta.json
  lancedb/                # 向量数据库
  cache/
    embeddings/
    summaries/
```

因此 Cursor 的需求可以改成这样：

```text
请将扫描机制设计为持久化知识库，而不是每次全量重建。

要求：
1. 扫描 ~/Zotero/storage/**/*.pdf 只是用于发现新增、删除、修改的文件；
2. 每个 PDF 使用 file_path、file_size、mtime、sha256 建立唯一记录；
3. 如果 PDF 未变化，不重复调用 MinerU；
4. 如果 Markdown 已存在且 PDF hash 未变化，不重复解析；
5. 如果 chunks 和 embeddings 已存在且 Markdown hash 未变化，不重复 embedding；
6. 如果 PDF 被删除，不立即删除知识库内容，而是标记为 deleted 或 archived；
7. 提供“强制重建索引”按钮，但默认不重建；
8. 所有解析结果、分块结果、embedding 和摘要都持久化保存在 ./data 目录。
```

一句话概括：

> **扫描只是同步 Zotero 文件系统状态；知识库才是长期资产。**

这样以后即使 Zotero 里有几千篇 PDF，也只会处理新增或变动的部分，不会每次重新跑 MinerU 和 embedding。
