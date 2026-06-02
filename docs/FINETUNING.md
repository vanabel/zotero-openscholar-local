# OpenScholar 下游微调指南

启动 API 时若看到类似日志：

```
BertModel LOAD REPORT from: .../openscholar-retriever
pooler.dense.bias   | MISSING
pooler.dense.weight | MISSING
Notes: MISSING — those params were newly initialized because missing from the checkpoint.
```

**这是预期行为，不是加载失败。** `OpenScholar_Retriever` 源自 [Contriever](https://huggingface.co/facebook/contriever)（BERT 双塔检索），训练时使用 **mean pooling + L2 归一化**，不使用 BERT 自带的 `pooler` 层。本仓库的编码逻辑见 `apps/api/app/services/openscholar_retrieval.py`：

- `AutoModel.from_pretrained(...)` 加载 backbone
- 对 `last_hidden_state` 做 attention mask 加权平均（mean pool）
- `F.normalize(..., p=2, dim=1)` 得到单位向量

因此 checkpoint 里没有 `pooler.*` 权重是正常的；**不必为了消除该警告去单独训练 pooler**。

若要在**你自己的文献库 / 学科领域**上提升检索效果，需要微调的是检索链路中的模型，并在微调后**重新建立索引**（写入新的 `scholar_embedding_json`）。

---

## 本项目中可微调的组件

| 组件 | 默认模型 | 架构 | 在本仓库中的用途 | 环境变量 |
|------|----------|------|------------------|----------|
| **Retriever**（双塔嵌入） | `OpenSciLM/OpenScholar_Retriever` | BERT / Contriever | 索引时写入 `scholar_embedding_json`；检索时编码 query | `OPENSCHOLAR_RETRIEVER_MODEL` |
| **Reranker**（交叉编码器） | `OpenSciLM/OpenScholar_Reranker` | XLM-RoBERTa 分类头 | 对 FTS + 稠密召回的候选 chunk 精排 | `OPENSCHOLAR_RERANKER_MODEL` |
| **Chat**（生成式 LM） | `OpenSciLM/Llama-3.1_OpenScholar-8B` | Llama 3.1 8B | 综述 / 问答 / 摘要 | `OPENSCHOLAR_CHAT_MODEL`（`CHAT_PROVIDER=transformers`） |

三者相互独立。微调 Retriever 后必须对文献库 **force 重建索引**；仅换 Reranker 可只重启 API（运行时加载新权重）。详见 [CONFIGURATION.md](./CONFIGURATION.md#检索)。

---

## 训练数据从哪来

常见做法（与 [OpenScholar 论文](https://arxiv.org/abs/2411.14199) 一致）：

1. **从你的 Zotero 库导出 chunk**  
   在本项目中完成 MinerU 解析与索引后，`chunks` 表已有分块文本；也可从 `data/parsed/` 下的 Markdown 自行分块。

2. **构造 (query, positive_passage) 对**  
   - 人工：为每篇文献写 1–3 个真实检索问题，正例为对应 chunk。  
   - 半自动：用摘要 / 章节标题让 LLM 生成问题（见下文 SiliconFlow 用法）。  
   - 负例：同 batch 内其它 chunk（InfoNCE in-batch negative），或显式 hard negative（同文献其它章节、相似但无关段落）。

3. **Reranker 额外需要 (query, passage, label)**  
   - `label=1`：相关；`label=0`：不相关。  
   - 或用 1–5 分相关性，OpenScholar 原文将 ≥4 为正、≤2 为负。

示例 JSONL（Retriever，InfoNCE / 对比学习通用）：

```json
{"query": "仿射 Sobolev 不等式在流形上的条件是什么？", "pos": "Theorem 2.1 ... affine Sobolev inequality ...", "neg": ["Introduction ... historical background ..."]}
```

示例 JSONL（Reranker，二分类）：

```json
{"query": "...", "passage": "...", "label": 1}
```

---

## 方式 A：ModelScope ms-swift（推荐，国内 GPU）

[ms-swift](https://github.com/modelscope/ms-swift) 支持 **Embedding** 与 **Reranker** 微调，文档：[Embedding 训练](https://swift.readthedocs.io/en/latest/BestPractices/Embedding.html)。

### 安装

```bash
pip install ms-swift -U
# 或：pip install 'ms-swift[llm]' -U
```

### A1. 微调 Reranker（与当前 `OpenScholar_Reranker` 最贴近）

OpenScholar Reranker 基于 [BGE-reranker](https://huggingface.co/BAAI/bge-reranker-large) 架构；ms-swift 的 reranker 任务可直接微调同类模型。

1. 将训练集转为 ms-swift 支持的格式（pointwise 示例，见 [train_reranker.sh](https://github.com/modelscope/ms-swift/blob/main/examples/train/reranker/train_reranker.sh)）。  
2. 以 **OpenScholar 官方 Reranker 或 BGE reranker** 为基座：

```bash
CUDA_VISIBLE_DEVICES=0 swift sft \
  --model OpenSciLM/OpenScholar_Reranker \
  --task_type reranker \
  --loss_type pointwise_reranker \
  --tuner_type lora \
  --dataset /path/to/your_rerank.jsonl \
  --output_dir ./output/openscholar-reranker-ft \
  --num_train_epochs 3 \
  --per_device_train_batch_size 16 \
  --learning_rate 6e-6 \
  --label_names labels
```

3. 合并 LoRA（若使用 `--tuner_type lora`）并导出完整 Hugging Face 目录：

```bash
swift export \
  --adapters ./output/openscholar-reranker-ft/vx-xxx/checkpoint-xxx \
  --merge_lora true \
  --output_dir ~/models/openscholar-reranker-ft
```

4. 在本项目 `.env` 中：

```env
OPENSCHOLAR_RERANKER_MODEL=/Users/<you>/models/openscholar-reranker-ft
```

### A2. 微调 Retriever（Embedding / 双塔）

**兼容性说明：** ms-swift 的 Embedding 任务主要面向 **Qwen3-Embedding、GTE、GME** 等 LLM 式嵌入模型（见官方文档「Currently supported models」）。  
`OpenScholar_Retriever` 是 **Contriever/BERT 双塔**，**不能**直接套用 Qwen3 的 embedding 脚本而不改推理代码。

你有两条路：

| 策略 | 做法 | 是否需改本仓库代码 |
|------|------|-------------------|
| **保留 OpenScholar Retriever 架构** | 用下方「方式 B」FlagEmbedding / Contriever 微调 | 否，导出 HF 后改 `OPENSCHOLAR_RETRIEVER_MODEL` 即可 |
| **换用 Qwen3-Embedding 等** | ms-swift `--task_type embedding --loss_type infonce` | **是**，需改 `openscholar_retrieval.py` 的加载与 pooling 逻辑 |

若坚持用 ms-swift 训练 **新的** 嵌入模型（例如 `Qwen/Qwen3-Embedding-0.6B`），InfoNCE 数据格式示例：

```json
{"messages": [{"role": "user", "content": "你的 query"}], "positive_messages": [[{"role": "user", "content": "相关 chunk 文本"}]]}
```

训练命令参考 [examples/train/embedding](https://github.com/modelscope/ms-swift/tree/main/examples/train/embedding)：

```bash
CUDA_VISIBLE_DEVICES=0 swift sft \
  --model Qwen/Qwen3-Embedding-0.6B \
  --task_type embedding \
  --loss_type infonce \
  --tuner_type lora \
  --dataset /path/to/your_emb.jsonl \
  --output_dir ./output/qwen3-emb-ft \
  --num_train_epochs 1 \
  --per_device_train_batch_size 8 \
  --learning_rate 5e-5
```

**接入本仓库前**，须确认微调后的模型能用 `AutoModel` + mean pool + L2 norm 得到与现网相同维度的向量；否则请走方式 B 或提交适配 PR。

### A3. 微调 OpenScholar-8B 对话模型

ms-swift 也支持 Llama 系 SFT / LoRA。基座：

```bash
swift sft \
  --model OpenSciLM/Llama-3.1_OpenScholar-8B \
  --dataset /path/to/instruction.jsonl \
  --tuner_type lora \
  --output_dir ./output/openscholar-8b-ft
```

导出后：

```env
CHAT_PROVIDER=transformers
OPENSCHOLAR_CHAT_MODEL=/Users/<you>/models/openscholar-8b-ft
```

---

## 方式 B：官方 / FlagEmbedding / Contriever（Retriever 首选）

与 `OpenScholar_Retriever` **架构完全一致** 的官方训练路径（[OpenScholar README](https://github.com/AkariAsai/OpenScholar)）：

| 组件 | 官方做法 | 链接 |
|------|----------|------|
| Retriever | 在 peS2o 上继续预训练 Contriever | [contriever 训练脚本](https://github.com/facebookresearch/contriever/blob/main/example_scripts/contriever.sh) |
| Reranker | FlagEmbedding 微调 BGE-reranker-large | [reranker 示例](https://github.com/FlagOpen/FlagEmbedding/tree/master/examples/reranker) |

**在你自己的数据上微调 Retriever（轻量方案）** — [Sentence Transformers](https://www.sbert.net/) + 对比损失：

```bash
pip install sentence-transformers
```

```python
from sentence_transformers import SentenceTransformer, InputExample, losses, models
from torch.utils.data import DataLoader

# 基座：与本项目相同的 OpenScholar Retriever（或 facebook/contriever）
word_emb = models.Transformer("OpenSciLM/OpenScholar_Retriever")
pooling = models.Pooling(word_emb.get_word_embedding_dimension(), pooling_mode="mean")
model = SentenceTransformer(modules=[word_emb, pooling])

train_examples = [
    InputExample(texts=["query 1", "positive passage 1"]),
    InputExample(texts=["query 2", "positive passage 2"]),
]
train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=16)
train_loss = losses.MultipleNegativesRankingLoss(model)

model.fit(
    train_objectives=[(train_dataloader, train_loss)],
    epochs=3,
    warmup_steps=100,
    output_path="~/models/openscholar-retriever-ft",
)
```

导出目录需包含 Hugging Face 标准文件（`config.json`、`model.safetensors`、tokenizer 等）。  
本仓库用 `AutoModel` 加载 backbone 并自行 mean pool；Sentence Transformers 保存的 transformer 子权重通常可直接作为 `OPENSCHOLAR_RETRIEVER_MODEL` 使用（指向含 `config.json` 的目录）。

**Reranker** 推荐使用 [FlagEmbedding 的 reranker 微调](https://github.com/FlagOpen/FlagEmbedding/blob/master/examples/reranker/README.md)，基座选 `OpenSciLM/OpenScholar_Reranker` 或 `BAAI/bge-reranker-large`，输出需为 `AutoModelForSequenceClassification` 可加载的 HF 目录（与本仓库 `rerank_scores` 一致）。

---

## 方式 C：SiliconFlow

参考 [SiliconFlow 微调文档](https://docs.siliconflow.cn/cn/userguide/guides/fine-tune)。

### 能做什么

| 能力 | 支持情况 |
|------|----------|
| **对话模型 LoRA 微调**（Qwen2.5 等） | ✅ 控制台创建任务，API 调用 `model` 填微调后的标识符 |
| **生图模型微调** | ✅ |
| **Embedding / Retriever 在线微调** | ❌ 平台未提供；Embedding 仅 API 推理（如 Qwen3-Embedding） |
| **Reranker 在线微调** | ❌ |

因此：**不能**在 SiliconFlow 上直接微调 `openscholar-retriever` 并下载权重回本仓库。

### 仍可与 SiliconFlow 配合的用法

1. **用 SiliconFlow 对话 API 生成训练标签**（类似 OpenScholar 论文里用 Llama 70B 给 passage 打 1–5 分）：  
   - 输入：摘要 + 检索到的 chunk  
   - 输出：相关性分数 → 转为 Reranker 的 `label` 或 Retriever 的 pos/neg 对  

2. **微调 Qwen 对话模型** 以适配你的写作风格 / 语言（中文综述等），在本项目中：

```env
CHAT_PROVIDER=openai
OPENAI_API_BASE=https://api.siliconflow.cn/v1
OPENAI_API_KEY=sk-...
OPENAI_CHAT_MODEL=<你的微调模型标识符>
```

这与 Retriever 无关；检索仍走本地 `OPENSCHOLAR_RETRIEVER_*`。

3. **在线 Embedding 作对比实验**（不替换 OpenScholar Retriever）：

```env
EMBED_PROVIDER=openai
OPENAI_EMBED_MODEL=Qwen/Qwen3-Embedding-0.6B
```

切换 `EMBED_PROVIDER` 后需重建索引（写入 `embedding_json`，与 `scholar_embedding_json` 是两套向量）。见 [CONFIGURATION.md](./CONFIGURATION.md)。

---

## 微调完成后接入本仓库

### 1. 权重目录布局

本地路径需为标准 Hugging Face 布局（与 `~/models/openscholar-retriever` 相同）：

```
~/models/openscholar-retriever-ft/
  config.json
  model.safetensors   # 或 pytorch_model.bin / 分片
  tokenizer.json
  tokenizer_config.json
  ...
```

### 2. 环境变量

```env
OPENSCHOLAR_RETRIEVER_ENABLED=1
OPENSCHOLAR_RERANKER_ENABLED=1
OPENSCHOLAR_RETRIEVER_MODEL=/Users/<you>/models/openscholar-retriever-ft
OPENSCHOLAR_RERANKER_MODEL=/Users/<you>/models/openscholar-reranker-ft
OPENSCHOLAR_DEVICE=auto
```

### 3. 重新索引

Retriever 向量存于 SQLite `chunks.scholar_embedding_json`（及可选 LanceDB）。**换 Retriever 权重后必须重建**：

- Web 文献库：对目标文献执行 **强制重建索引**；或  
- API：`POST /papers/{id}/index?force=true`  
- 批量：`apps/api/scripts/scholar_embed_batch.py`（仅重算 OpenScholar 嵌入，前提为 chunk 已存在）

若启用 LanceDB（`LANCEDB_ENABLED=1`），重建后会自动同步；也可对单篇调用 backfill（见 [API.md](./API.md)）。

### 4. 验证

```bash
cd apps/api && .venv/bin/python -c "
from app.services.openscholar_retrieval import encode_queries, encode_passages
q = encode_queries(['测试 query'])[0]
p = encode_passages(['测试 passage'])[0]
print('dim', len(q), 'cos', sum(a*b for a,b in zip(q,p)))
"
```

在文献库发起检索，观察日志中 `retrieve` 阶段是否加载新模型路径、命中是否更符合预期。

---

## 选型建议（简表）

| 目标 | 推荐平台 / 工具 | 备注 |
|------|-----------------|------|
| 微调 **OpenScholar Retriever**（BERT 双塔） | FlagEmbedding / Contriever / Sentence Transformers | 与现网代码零改动 |
| 微调 **OpenScholar Reranker** | ms-swift `--task_type reranker` 或 FlagEmbedding | 导出 HF 后改 `OPENSCHOLAR_RERANKER_MODEL` |
| 微调 **OpenScholar-8B** 对话 | ms-swift SFT / LoRA；或 SiliconFlow 对话微调 | 改 `OPENSCHOLAR_CHAT_MODEL` 或走 OpenAI 兼容 API |
| 仅用 SiliconFlow **训练 Retriever** | 不可行 | 可用其 LLM API **造数据**，在 GPU 上用 ms-swift / ST 训练 |
| 消除 **pooler MISSING** 警告 | 无需处理 | 不影响检索；mean pool 不读 pooler |

---

## 参考链接

- [OpenScholar 论文](https://arxiv.org/abs/2411.14199) / [代码库](https://github.com/AkariAsai/OpenScholar)  
- [OpenScholar_Retriever](https://huggingface.co/OpenSciLM/OpenScholar_Retriever) / [OpenScholar_Reranker](https://huggingface.co/OpenSciLM/OpenScholar_Reranker)  
- [ms-swift Embedding 文档](https://swift.readthedocs.io/en/latest/BestPractices/Embedding.html)  
- [SiliconFlow 微调](https://docs.siliconflow.cn/cn/userguide/guides/fine-tune)  
- 本仓库检索配置：[CONFIGURATION.md](./CONFIGURATION.md#检索)  
- 超算同步权重：[HPC.md](./HPC.md)
