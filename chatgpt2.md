是的。我建议把 roadmap 从“按功能模块推进”改成“按质量目标推进”。你当前系统其实已经超过普通 MVP：已有 Zotero 扫描、题录同步、MinerU 解析、Markdown 分块、FTS + OpenScholar dense + RRF + reranker、问答/综述流式、缓存等基础能力；未完成项主要集中在专用向量库、异步任务队列、跨篇配额、chunk 去重、综述模板、引用校验、导出与评测等方面。

因此新的路线不应继续泛泛写成：

```text
Phase 2: 检索质量
Phase 3: 异步管线
Phase 4: 综述深化
```

而应重构为：

```text
目标 A：解析质量
目标 B：chunk 质量
目标 C：检索质量
目标 D：引用可靠性
目标 E：综述结构模板
目标 F：工程稳定性
```

这样 Cursor 更容易围绕“可验收指标”开发。

---

# 一、改进后的总架构

建议把系统架构明确成六层。

```text
┌────────────────────────────────────────────┐
│  6. 应用层                                  │
│  文献问答 / 文献综述 / 项目申请书素材 / 导出 │
└────────────────────────────────────────────┘
                    ▲
┌────────────────────────────────────────────┐
│  5. 生成与引用控制层                         │
│  Citation-aware prompt / evidence locking   │
│  no-evidence-no-claim / citation verifier   │
└────────────────────────────────────────────┘
                    ▲
┌────────────────────────────────────────────┐
│  4. 检索与重排序层                           │
│  FTS + dense + RRF + reranker + paper quota │
└────────────────────────────────────────────┘
                    ▲
┌────────────────────────────────────────────┐
│  3. 知识组织层                               │
│  chunks / summaries / sections / metadata   │
└────────────────────────────────────────────┘
                    ▲
┌────────────────────────────────────────────┐
│  2. 解析与清洗层                             │
│  MinerU → Markdown/JSON → quality check     │
└────────────────────────────────────────────┘
                    ▲
┌────────────────────────────────────────────┐
│  1. 数据源层                                 │
│  Zotero storage / zotero.sqlite / PDF hash  │
└────────────────────────────────────────────┘
```

关键思想：

```text
PDF 不是知识库；
Markdown 也不是最终知识库；
真正的知识库 = 文献元数据 + 结构化 Markdown + 高质量 chunks + embeddings + summaries + citation map。
```

---

# 二、推荐 Roadmap v2

## Phase 0：质量基线与工程稳定性

目标：先保证“坏了能发现，错了能定位”。

你现在已有不少测试，但还缺几个关键闭环。当前 roadmap 中也明确列出 CI、错误面、文献库 UX、扫描/索引 fixture 测试仍未完成。

### 要做

```text
0.1 统一错误面
- LLM 不可用
- embedding 不可用
- MinerU 失败
- OpenScholar retriever/reranker 不可用
- Zotero sqlite 不可读
- document.md 缺失
- chunk 为空
```

```text
0.2 建立最小回归集
- 3 篇英文数学论文
- 3 篇中文论文
- 1 篇扫描版 PDF
- 1 篇公式密集论文
- 1 篇表格/图较多论文
```

```text
0.3 CI
- 不依赖 Ollama 的测试必须自动通过
- 依赖 Ollama / MinerU 的测试标记为 optional
```

```text
0.4 文献库 UX
- 解析失败原因
- 索引失败原因
- 重新解析按钮
- 仅重建索引按钮
- 查看 document.md 片段
- 查看 chunks
```

### 验收指标

```text
pnpm test 默认通过；
前端能看到每篇文献的 parse/index 状态；
失败任务能显示具体错误原因；
不启动 Ollama 时，API 返回明确 JSON 错误，而不是崩溃。
```

---

## Phase 1：解析质量

目标：让 MinerU 输出变成“可信 Markdown”，而不是只要有 `document.md` 就算完成。

当前系统已经支持 MinerU CLI、常驻 mineru-api、cloud API，大 PDF 自动切片、断点续传、zip 下载重试和 pypdf 降级。 下一步重点不是“能解析”，而是“解析质量可评估、可修复”。

### 要做

```text
1.1 解析质量评分 parse_quality_score
```

为每篇论文生成：

```json
{
  "paper_id": "...",
  "parse_quality_score": 0.87,
  "text_length": 42000,
  "page_count": 18,
  "detected_sections": 9,
  "formula_blocks": 63,
  "table_blocks": 2,
  "image_blocks": 8,
  "ocr_ratio": 0.12,
  "suspicious_garbled_ratio": 0.03,
  "references_detected": true
}
```

```text
1.2 Markdown 清洗器
```

处理：

```text
- 页眉页脚
- 重复标题
- 断行错误
- 连字符断词
- 多栏阅读顺序错误
- 参考文献区识别
- 公式块保护
- 图表标题保护
```

```text
1.3 解析预览
```

前端显示：

```text
- 原 PDF 路径
- document.md 预览
- section tree
- 解析质量评分
- 警告项
```

```text
1.4 低质量解析重试策略
```

例如：

```text
if parse_quality_score < 0.65:
    尝试 cloud mode
elif scanned_pdf:
    启用 OCR
elif too_many_garbled_tokens:
    标记为人工检查
```

### 建议新增表

```sql
CREATE TABLE parse_reports (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    parser TEXT,
    parser_mode TEXT,
    parse_quality_score REAL,
    text_length INTEGER,
    page_count INTEGER,
    detected_sections INTEGER,
    formula_blocks INTEGER,
    table_blocks INTEGER,
    image_blocks INTEGER,
    warnings TEXT,
    created_at TEXT
);
```

### 验收指标

```text
每篇论文有 parse_quality_score；
低质量 PDF 可筛选；
文献库可预览 Markdown；
重复解析不会覆盖高质量结果，除非 force。
```

---

## Phase 2：Chunk 质量

目标：chunk 不只是“固定长度文本块”，而是“可引用、可检索、可综合”的知识单元。

当前 roadmap 中已经提到 Markdown 分块、chunks 表、FTS5、embedding；但仍缺跨篇配额、chunk 去重、结构化 section 信息等。

### 要做

```text
2.1 Chunk 类型分类
```

每个 chunk 增加：

```text
chunk_type:
- abstract
- introduction
- definition
- theorem
- proof
- method
- experiment
- discussion
- conclusion
- references
- unknown
```

数学论文尤其要识别：

```text
Definition
Lemma
Proposition
Theorem
Corollary
Remark
Proof
Example
```

```text
2.2 Section path
```

保存：

```json
{
  "section_path": ["2. Preliminaries", "2.1 Coulomb Gauge"],
  "section_level": 2
}
```

```text
2.3 Chunk 质量评分
```

```json
{
  "chunk_quality_score": 0.91,
  "has_complete_sentence": true,
  "has_citation_context": true,
  "has_formula_context": true,
  "too_short": false,
  "too_long": false,
  "mostly_references": false
}
```

```text
2.4 Chunk 去重
```

去掉：

```text
- 重复页眉页脚
- 重复摘要
- 重复参考文献条目
- MinerU 切片合并导致的重复段
```

```text
2.5 Chunk 可追溯
```

每个 chunk 必须能回到：

```text
paper_id
title
authors
year
section
page_start/page_end
source_path
markdown offset
```

### 建议新增字段

```sql
ALTER TABLE chunks ADD COLUMN chunk_type TEXT;
ALTER TABLE chunks ADD COLUMN section_path TEXT;
ALTER TABLE chunks ADD COLUMN page_start INTEGER;
ALTER TABLE chunks ADD COLUMN page_end INTEGER;
ALTER TABLE chunks ADD COLUMN markdown_start INTEGER;
ALTER TABLE chunks ADD COLUMN markdown_end INTEGER;
ALTER TABLE chunks ADD COLUMN chunk_quality_score REAL;
ALTER TABLE chunks ADD COLUMN content_hash TEXT;
```

### 验收指标

```text
问答引用可以显示：文献标题 + section + chunk；
可过滤 references-only chunk；
同一段内容不会重复进入检索结果；
定理/定义/proof 类 chunk 可被单独检索。
```

---

## Phase 3：检索质量

目标：让系统从“能检索”变为“检索得准、覆盖得全、跨文献均衡”。

你目前已经有 FTS + 多查询合并、RRF、OpenScholar dense、OpenScholar reranker 或 Ollama 余弦。当前未完成的是 LanceDB/Qdrant、嵌入抽象、融合调参、跨篇配额、chunk 去重和“仅补未 indexed”API。

### 要做

```text
3.1 专用向量库
```

建议优先：

```text
LanceDB
```

原因：

```text
- 本地文件型
- 不需要 Docker
- 适合个人 Zotero 知识库
- 比 SQLite 全表 dense 扫描更可扩展
```

```text
3.2 Hybrid retrieval pipeline
```

固定为：

```text
query
  ↓
query expansion
  ↓
FTS retrieval
  ↓
dense retrieval
  ↓
RRF fusion
  ↓
paper quota
  ↓
dedup
  ↓
reranker
  ↓
top evidence chunks
```

```text
3.3 跨篇配额
```

防止一篇文献垄断上下文：

```python
max_chunks_per_paper = 3
max_papers = 8
```

```text
3.4 查询扩展
```

数学/科研场景中很重要：

```text
alpha-Yang-Mills-Higgs
α-Yang-Mills-Higgs
Yang-Mills-Higgs
energy identity
no-neck property
bubble convergence
Lorentz space
Pohozaev identity
```

```text
3.5 检索评测集
```

建立 `eval_queries.jsonl`：

```json
{
  "query": "α-YMH 的 no-neck property 依赖哪些 Lorentz 空间估计？",
  "expected_papers": ["Ai-Li-Zhu-2025"],
  "expected_terms": ["Lorentz", "Pohozaev", "neck"],
  "notes": "应优先召回 α-YMH 定量行为论文"
}
```

### 验收指标

```text
top-5 至少包含相关文献；
top-10 覆盖多个相关文献；
同一文献最多占 k 个 chunk；
纯 FTS、纯 dense、RRF、reranker 的效果可比较；
千级/万级 chunks 延迟可接受。
```

---

## Phase 4：引用可靠性

目标：从“回答后面带几个引用”升级为“每个关键判断都有证据，且证据确实支持该判断”。

当前系统已有引用式 `[n]` 问答与综述、SSE 流式，但 roadmap 也明确列出“无证据不断言、引用与 `chunk_id` 对齐校验”仍待完成。

### 要做

```text
4.1 Evidence locking
```

生成前给 LLM 的上下文必须编号：

```text
[CHUNK:C17]
Title: ...
Authors: ...
Section: ...
Content: ...
```

回答必须引用：

```text
这个结论依赖 Pohozaev 型恒等式与 neck 区域 Lorentz 控制 [C17][C23]。
```

```text
4.2 Citation verifier
```

生成后检查：

```text
- 引用的 chunk_id 是否存在；
- 回答中的关键名词是否出现在引用 chunk 或其邻近 chunk；
- 是否存在无引用的强断言；
- 是否引用了不相关 chunk。
```

```text
4.3 Claim extraction
```

把回答拆成 claims：

```json
[
  {
    "claim": "该文证明了能量恒等式和 no-neck 性质。",
    "citations": ["C17", "C23"],
    "verified": true
  }
]
```

```text
4.4 无证据降级回答
```

如果没有证据，回答应说：

```text
当前知识库中未检索到足够证据支持该结论。
```

而不是编造。

```text
4.5 引用表
```

回答末尾给出：

```text
[1] Ai-Li-Zhu, 2025, Section 3, chunk C17
[2] ...
```

### 建议新增表

```sql
CREATE TABLE answer_citations (
    id TEXT PRIMARY KEY,
    answer_id TEXT,
    chunk_id TEXT,
    claim_text TEXT,
    verified INTEGER,
    verifier_score REAL,
    created_at TEXT
);
```

### 验收指标

```text
回答中每个关键判断至少有一个 chunk_id；
不存在引用了不存在的 chunk；
引用片段可点击查看；
没有证据时系统明确说“不足以回答”。
```

---

## Phase 5：综述结构模板

目标：把“文献问答”升级为“科研写作辅助”。

你当前 roadmap 中已经列出综述模板、综述双语、Markdown/DOCX 导出、summaries 表落地、引用表与 chunk 链接等待做项。 这一阶段应重点服务你的真实需求：文献综述、项目申请书、数学论文阅读笔记。

### 要做

```text
5.1 四类综述模板
```

#### A. 快速综述

```text
适用：快速了解一个主题
输出：
1. 主题背景
2. 主要文献
3. 关键结论
4. 技术路线
5. 未解决问题
```

#### B. 结构化综述

```text
适用：论文引言、研究现状
输出：
1. 问题源流
2. 代表性工作
3. 方法谱系
4. 技术障碍
5. 当前进展
6. 本文/本项目切入点
```

#### C. 对比综述

```text
适用：比较几篇论文
输出表格：
- 文献
- 问题设置
- 主要假设
- 核心定理
- 技术工具
- 局限性
- 与本研究关系
```

#### D. 项目申请书模板

```text
适用：国家基金/校级项目
输出：
1. 国内外研究现状
2. 关键科学问题
3. 现有方法不足
4. 本项目切入点
5. 创新性
6. 技术路线支撑文献
```

```text
5.2 summaries 表真正使用起来
```

每篇论文先生成：

```text
paper_summary
method_summary
result_summary
limitation_summary
relation_to_user_research
```

综述时先检索 summaries，再必要时下钻 chunks。

```text
5.3 导出
```

至少支持：

```text
Markdown
DOCX
BibTeX/citation list
```

```text
5.4 模板可配置
```

前端设置：

```text
综述类型
语言
字数
引用密度
是否生成表格
是否生成申请书风格
是否保留英文术语
```

### 验收指标

```text
可以一键生成“项目申请书研究现状”初稿；
可以导出 Markdown；
每段综述都有引用；
综述前可选择文献范围、标签、年份、集合。
```

---

## Phase 6：异步管线与规模化

目标：当 Zotero 文献增长到几千篇时，系统仍能稳定运行。

当前 roadmap 中已明确异步任务队列、Worker/API 分离、MinerU/embedding 并发限制、进度 SSE/WebSocket 等仍未完成。

### 要做

```text
6.1 任务队列
```

第一版不必 Celery，SQLite task queue 足够：

```text
parse
index
reindex
summarize
verify
export
```

```text
6.2 Worker 分离
```

```text
API 负责响应；
Worker 负责慢任务；
前端通过 SSE/WebSocket 看进度。
```

```text
6.3 并发限制
```

针对 MacBook M4 24G：

```text
MinerU worker: 1
Embedding worker: 1–2
LLM generation: 1
Reranker batch size: 小批量
```

```text
6.4 仅补未 indexed
```

新增 API：

```text
POST /papers/index-missing
POST /papers/parse-missing
POST /summaries/generate-missing
```

### 验收指标

```text
全库索引时 API 不阻塞；
前端能看到进度；
失败任务可重试；
MacBook M4 不会因为并发过高卡死。
```

---

# 三、重排后的优先级

我建议把你原 roadmap 的优先级改为：

```text
P0：错误面 + 文献库 UX + 测试基线
P1：解析质量评分 + Markdown 预览
P2：chunk 类型、section path、chunk 去重
P3：LanceDB + hybrid retrieval 调参 + 跨篇配额
P4：citation verifier + no-evidence-no-claim
P5：综述模板 + summaries 表 + Markdown/DOCX 导出
P6：异步任务队列 + 进度 SSE/WebSocket
P7：外部源、ScholarQA 评测、Mano-P/Cider
```

这比原路线更适合你，因为它直接对应你最关心的五个目标：

```text
解析质量 → Phase 1
chunk 质量 → Phase 2
检索质量 → Phase 3
引用可靠性 → Phase 4
综述结构模板 → Phase 5
```

---

# 四、Cursor 可直接执行的新版任务说明

可以把下面这一段加入 `ROADMAP.md` 或新建 `docs/QUALITY_ROADMAP.md`。

```text
请将项目路线从功能堆叠改为质量目标驱动。

本项目第一年不做生成模型微调。核心投入目标为：

1. 解析质量
2. chunk 质量
3. 检索质量
4. 引用可靠性
5. 综述结构模板

请按以下阶段开发。

Phase 0：工程稳定性
- 增加统一错误 JSON
- 增加扫描/索引 fixture 测试
- 增加 CI
- 前端显示 parse/index 失败原因
- 前端支持 document.md 预览和 chunks 预览

Phase 1：解析质量
- 为每篇论文生成 parse_quality_score
- 新建 parse_reports 表
- 统计 text_length, page_count, section_count, formula_count, table_count, warnings
- 增加 Markdown cleaner
- 支持低质量解析结果筛选和重新解析

Phase 2：Chunk 质量
- 为 chunks 增加 chunk_type, section_path, page_start, page_end, markdown_start, markdown_end, chunk_quality_score, content_hash
- 识别 abstract, introduction, definition, theorem, proof, method, conclusion, references 等类型
- 增加 chunk 去重
- 避免 references-only chunk 参与普通问答
- 支持前端查看 chunk 来源

Phase 3：检索质量
- 接入 LanceDB 作为专用向量库
- 保留 SQLite FTS5
- 实现 hybrid retrieval: FTS + dense + RRF + paper quota + reranker
- 增加 max_chunks_per_paper
- 增加 query expansion
- 增加 eval_queries.jsonl 检索评测集

Phase 4：引用可靠性
- 实现 evidence locking
- 生成回答时使用 chunk_id 引用
- 新建 answer_citations 表
- 实现 citation verifier
- 检查每个关键 claim 是否有 chunk 支撑
- 对无证据问题返回“不足以回答”，不要编造

Phase 5：综述结构模板
- 增加四类综述模板：快速综述、结构化综述、对比综述、项目申请书综述
- summaries 表真正落地使用
- 每篇论文生成 paper_summary, method_summary, result_summary, limitation_summary
- 综述先聚合 summaries，再下钻 chunks
- 支持导出 Markdown 和 DOCX
- 导出时保留引用表与 chunk 链接

Phase 6：异步任务与规模化
- 实现 SQLite task queue 或 RQ/Celery
- Worker 与 API 分离
- 支持 parse/index/summarize/reindex 队列
- 前端显示任务进度
- 增加 parse-missing, index-missing, summarize-missing API
```

---

# 五、建议的最终架构命名

我建议你把系统内部抽象为：

```text
Zotero Research Knowledge Base
```

而不是简单叫 RAG app。

核心模块命名：

```text
SourceManager        # Zotero PDF 与 zotero.sqlite
ParseManager         # MinerU + parse reports
CleanMarkdown        # Markdown 清洗
ChunkManager         # 结构化分块
EmbeddingManager     # embedding 与向量库
RetrievalManager     # FTS + dense + RRF + reranker
EvidenceManager      # chunk evidence locking
CitationVerifier     # 引用校验
SummaryManager       # paper/section summaries
ReviewWriter         # 综述生成
ExportManager        # Markdown/DOCX 导出
TaskManager          # 后台任务
```

一句话总结新版 roadmap：

> 第一阶段不是追求“更强模型”，而是把 Zotero 文献转化为一个**可解析、可分块、可检索、可引用、可综述、可导出**的高质量个人科研知识库。
