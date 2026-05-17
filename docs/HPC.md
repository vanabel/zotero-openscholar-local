# 超算（SLURM）批量 OpenScholar 向量

在**学校 GPU 集群**上仅计算 `scholar_embedding_json`（OpenScholar Retriever），**不**重建分块、**不**调用 Ollama/OpenAI 的 `embedding_json`。适合 Mac 本地已完成解析与普通嵌入后，把最耗 GPU 的 Retriever 批处理放到超算。

调度器：**SLURM**（见 `scripts/hpc/submit_scholar.slurm`）。

## 流程概览

```text
Mac（本地）                         超算（SLURM GPU 作业）
──────────                         ─────────────────────
扫描 + 解析 + 建立索引              rsync 上行
  → parsed/{id}/document.md    →    app.sqlite（含 chunks.text、embedding_json）
  → chunks + embedding_json         OPENSCHOLAR_DEVICE=cuda
                                    scholar_embed_batch.py
rsync 下行                     ←    app.sqlite（含 scholar_embedding_json）
  → 可选 data/lance/                lance/（若 LANCEDB_ENABLED=1）
重启 API / backfill-lance
```

**注意**：`paper_id` 由 PDF **绝对路径**哈希得到。请同步 Mac 上生成的 `app.sqlite` 与 `parsed/`，不要在超算上重新扫 Zotero 生成新 ID。

## 一键提交（SLURM）

### 1. 登录节点准备

```bash
git clone <repo-url> ~/zotero-openscholar-local
cd ~/zotero-openscholar-local/apps/api
python3 -m venv .venv
.venv/bin/pip install -e '.[openscholar,lance]'

cp .env.hpc.example .env.hpc
# 编辑 .env.hpc：DATA_DIR、HF_TOKEN、批次大小等
```

从 Mac 同步数据（示例）：

```bash
rsync -avz ./apps/api/data/ login:/path/to/synced/data/
```

`synced/data` 下需含 `app.sqlite`；若仅补 scholar、不重解析，**不必**上传 PDF。

### 2. 预拉模型（建议，避免作业排队时下载失败）

```bash
export HF_HOME=/scratch/$USER/hf_cache
cd ~/zotero-openscholar-local/apps/api
.venv/bin/python -c "
from transformers import AutoModel, AutoTokenizer
m='OpenSciLM/OpenScholar_Retriever'
AutoTokenizer.from_pretrained(m)
AutoModel.from_pretrained(m)
"
```

### 3. 编辑 SLURM 脚本并提交

编辑 `scripts/hpc/submit_scholar.slurm` 顶部的 `#SBATCH`（**分区、`--gres=gpu:1`** 等按学校模板填写），以及默认变量 `REPO_ROOT`、`DATA_DIR`。

```bash
cd ~/zotero-openscholar-local
export REPO_ROOT=$PWD
export DATA_DIR=/path/to/synced/data
export ENV_FILE=$REPO_ROOT/apps/api/.env.hpc
sbatch scripts/hpc/submit_scholar.slurm
```

覆盖环境变量示例：

```bash
sbatch --export=ALL,MISSING_ONLY=1,FORCE=0,DATA_DIR=/scratch/$USER/zos-data \
  scripts/hpc/submit_scholar.slurm
```

### 4. 回传与本地收尾

```bash
rsync -avz login:/path/to/synced/data/app.sqlite ./apps/api/data/
rsync -avz login:/path/to/synced/data/lance/ ./apps/api/data/lance/
```

本地重启 API。若只回了 SQLite、未回 `lance/`：在文献库或通过 `POST /papers/backfill-lance` 将 scholar 向量写入 LanceDB。

## 命令行（不经过 SLURM）

在 `apps/api` 下：

```bash
# 仅补缺失 scholar 向量（推荐）
.venv/bin/python scripts/scholar_embed_batch.py --all --missing-only

# 指定文献
.venv/bin/python scripts/scholar_embed_batch.py --paper-id <32位id>

# 强制全量重算 scholar
.venv/bin/python scripts/scholar_embed_batch.py --all --force

# 只写 SQLite，不写 Lance
.venv/bin/python scripts/scholar_embed_batch.py --all --missing-only --no-lance
```

仓库根目录：

```bash
pnpm run scholar:embed
```

## 环境变量（`.env.hpc`）

| 变量 | 建议（超算） |
|------|----------------|
| `DATA_DIR` | 同步后的数据目录（含 `app.sqlite`） |
| `OPENSCHOLAR_RETRIEVER_ENABLED` | `1` |
| `OPENSCHOLAR_RERANKER_ENABLED` | `0`（建库不需要 Reranker） |
| `OPENSCHOLAR_DEVICE` | `cuda` |
| `OPENSCHOLAR_ENCODE_BATCH_SIZE` | 按 GPU 显存调大（如 16–64） |
| `LANCEDB_ENABLED` | `1`（与本地一致时可直接 rsync `lance/`） |
| `HF_HOME` / `HF_TOKEN` | 集群缓存目录与 Hugging Face 令牌 |

模板：`apps/api/.env.hpc.example`。

## 与 `reindex_library.py` 的区别

| 脚本 | 分块 | `embedding_json` | `scholar_embedding_json` | MinerU |
|------|------|------------------|---------------------------|--------|
| `reindex_library.py` | 是 | 是 | 是 | 否 |
| `scholar_embed_batch.py` | 否 | **否** | 是 | 否 |

## 故障排查

| 现象 | 处理 |
|------|------|
| `OpenScholar 依赖未安装` | `pip install -e '.[openscholar]'` |
| `OPENSCHOLAR_RETRIEVER_ENABLED=0` | 检查 `.env.hpc` |
| CUDA OOM | 减小 `OPENSCHOLAR_ENCODE_BATCH_SIZE` |
| 作业无 GPU | 检查 `#SBATCH --gres` 与分区 |
| 本地检索仍慢 | 确认 scholar 已写入；启用 Lance 并 backfill |

## 参考

- [CONFIGURATION.md](./CONFIGURATION.md) — OpenScholar 模型与检索开关  
- [OPERATIONS.md](./OPERATIONS.md) — `DATA_DIR` 与备份  
- [ARCHITECTURE.md](./ARCHITECTURE.md) — 索引与检索流水线  
