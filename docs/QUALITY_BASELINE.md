# 质量回归基线

单人知识库的质量迭代依赖固定样本与可重复评测。本文档定义 **P0** 最小回归集与 **P3** 检索评测占位。路线图见 [ROADMAP.md](./ROADMAP.md)。

## 最小回归集（P0）

建议在 `apps/api/tests/fixtures/papers/` 放置脱敏或公开 PDF 的解析/索引产物（仅 `document.md` + 元数据，不含全文 PDF 若版权受限）：

| ID | 类型 | 用途 |
|----|------|------|
| `fixture-en-math-01` | 英文、公式密集 | 解析质量、定理类 chunk |
| `fixture-en-math-02` | 英文、多定理证明 | chunk 类型识别 |
| `fixture-en-math-03` | 英文、标准结构 | 检索基线 |
| `fixture-zh-01` | 中文期刊 | OCR / 中文 FTS |
| `fixture-zh-02` | 中文、多栏 | 阅读顺序 |
| `fixture-zh-03` | 中文综述体例 | 综述模板 |
| `fixture-scan-01` | 扫描版 PDF | MinerU OCR、低分重试 |
| `fixture-table-01` | 图表密集 | 表格/图 caption 保留 |

集成测试应 **mock LLM**，不依赖 Ollama / MinerU 即可跑通：扫描元数据、分块、FTS 命中、配额逻辑。

实现：`apps/api/tests/test_p0_regression.py`（参数化 8 个 fixture）；样本在 `apps/api/tests/fixtures/papers/`。从本机 `data/parsed` 重新摘录英文/扫描类 fixture：`.venv/bin/python scripts/build_p0_fixtures.py`。

```bash
cd apps/api && .venv/bin/pytest tests/test_p0_regression.py -q
```

## 检索评测（P3）

`apps/api/tests/eval/eval_queries.jsonl`：每行一条 JSON，例如：

```json
{
  "query": "α-YMH 的 no-neck property 依赖哪些 Lorentz 空间估计？",
  "expected_paper_ids": [],
  "expected_terms": ["Lorentz", "Pohozaev", "neck"],
  "notes": "应优先召回相关定量行为论文；paper_id 填入索引后的 id"
}
```

运行（待实现 CLI）：

```bash
cd apps/api && .venv/bin/python -m scripts.eval_retrieval --top-k 10
```

## 引用评测（P4）

对固定问答用例检查：输出中 `[n]` 与 `chunk_id` 映射、无证据时是否降级。用例文件占位：`apps/api/tests/eval/eval_citations.jsonl`。
