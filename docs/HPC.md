# 超算（SLURM）批量向量：分块 + 双嵌入

适合 **Mac 本地只解析 PDF**（`document.md`），在 **GPU 集群**上完成分块、`embedding_json`（OpenAI 兼容 API，**无 Ollama**）与 `scholar_embedding_json`（OpenScholar Retriever / CUDA）。

调度器：**SLURM**。一键脚本：`scripts/hpc/submit_vectors.slurm`（仅 scholar 时仍可用 `submit_scholar.slurm`）。

## 流程概览

```text
Mac（本地）                              超算（SLURM）
──────────                              ────────────
扫描 Zotero + MinerU/pypdf 解析          rsync 上行：
  → data/parsed/{id}/document.md    →     app.sqlite + parsed/
  （可不建索引、不跑嵌入）                 （PDF 路径可不存在）

                                        1. chunk_batch.py      → chunks（无向量）
                                        2. embed_batch.py      → embedding_json（HTTP API）
                                        3. scholar_embed_batch → scholar_embedding_json（GPU）

rsync 下行                           ←   app.sqlite + lance/
本地重启 API
```

**`paper_id`** 由 Mac 上 PDF 绝对路径哈希；请同步 Mac 生成的 **`app.sqlite`** 与 **`parsed/`**，勿在超算重新扫库。

## 一键提交

### 1. 登录节点

```bash
git clone <repo> ~/zotero-openscholar-local
cd ~/zotero-openscholar-local/apps/api
python3 -m venv .venv
.venv/bin/pip install -e '.[openscholar,lance]'

cp .env.hpc.example .env.hpc
# 必填：DATA_DIR、OPENAI_API_*、HF_TOKEN（若需）
```

Mac 同步（示例）：

```bash
rsync -avz ./apps/api/data/app.sqlite login:/path/to/synced/data/
rsync -avz ./apps/api/data/parsed/ login:/path/to/synced/data/parsed/
```

### 2. 配置 `.env.hpc`（无 Ollama、允许出网）

| 变量 | 说明 |
|------|------|
| `EMBED_PROVIDER=openai` | **必须**；`embed_batch` 不走 Ollama |
| `OPENAI_API_BASE` / `OPENAI_API_KEY` / `OPENAI_EMBED_MODEL` | 嵌入 API（OpenAI 或兼容网关） |
| `OPENSCHOLAR_DEVICE=cuda` | Retriever 用 GPU |
| `OPENSCHOLAR_RETRIEVER_ENABLED=1` | scholar 向量 |
| `LANCEDB_ENABLED=1` | 与本地一致，便于 rsync `lance/` |

模板：`apps/api/.env.hpc.example`。

### 3. 提交作业

编辑 `scripts/hpc/submit_vectors.slurm` 的 `#SBATCH`（分区、`--gres=gpu:1`），然后：

```bash
cd ~/zotero-openscholar-local
export REPO_ROOT=$PWD
export DATA_DIR=/path/to/synced/data
sbatch scripts/hpc/submit_vectors.slurm
```

跳过某一步（例如已有 chunk，只补向量）：

```bash
sbatch --export=ALL,RUN_CHUNK=0,RUN_EMBED=1,RUN_SCHOLAR=1,DATA_DIR=/path/to/data \
  scripts/hpc/submit_vectors.slurm
```

### 4. 回传 Mac

```bash
rsync -avz login:/path/to/synced/data/app.sqlite ./apps/api/data/
rsync -avz login:/path/to/synced/data/lance/ ./apps/api/data/lance/
```

本地 `.env` 可继续 `EMBED_PROVIDER=ollama`（与超算写入的 `embedding_json` 维度/模型需一致：若超算用 `text-embedding-3-small`，本地检索也应使用同一嵌入模型，或超算后用同一 API 模型）。

## 分步命令（apps/api）

```bash
# 1. 从 parsed Markdown 分块（本地只解析后）
.venv/bin/python scripts/chunk_batch.py --all --missing-only

# 2. OpenAI 兼容嵌入
.venv/bin/python scripts/embed_batch.py --all --missing-only

# 3. OpenScholar Retriever（GPU）
.venv/bin/python scripts/scholar_embed_batch.py --all --missing-only
```

仓库根目录：

```bash
pnpm run hpc:vectors   # 本地调试：顺序执行上述三步（需 .env 配 openai + openscholar）
```

## 脚本对照

| 脚本 | 分块 | `embedding_json` | `scholar_embedding_json` | 需要 |
|------|------|------------------|---------------------------|------|
| `chunk_batch.py` | 是 | 否 | 否 | `parsed/document.md` |
| `embed_batch.py` | 否 | 是 | 否 | chunk + `EMBED_PROVIDER=openai` + 出网 |
| `scholar_embed_batch.py` | 否 | 否 | 是 | chunk + GPU + `[openscholar]` |
| `reindex_library.py` | 是 | 是 | 是 | `parsed/`；`reindex_only` 时 PDF 可不在本机 |

## 本地 Mac 推荐操作

1. 文献库：**扫描** → **解析缺失**（或单篇解析），得到 `parsed/`。  
2. **不要**在 Mac 上跑全库嵌入（可选）。  
3. rsync `app.sqlite` + `parsed/` 到超算 → `sbatch submit_vectors.slurm`。  
4. 拉回库文件，重启 `pnpm dev`。

若 Mac 上已部分索引，超算设 `MISSING_ONLY=1`（默认）只补缺失向量。

## 故障排查

| 现象 | 处理 |
|------|------|
| `embed 需要 EMBED_PROVIDER=openai` | 在 `.env.hpc` 设置并 `source` |
| API 429 / 超时 | 减小 `embed_batch --batch-size`；检查配额 |
| `无 chunk` | 先跑 `chunk_batch` 或检查 `parsed/` 是否同步 |
| `PDF 文件不存在`（reindex） | 已支持「有 Markdown 无 PDF」；优先用三件套脚本 |
| scholar CUDA OOM | 减小 `OPENSCHOLAR_ENCODE_BATCH_SIZE` |

## 参考

- [CONFIGURATION.md](./CONFIGURATION.md) — Provider 与 OpenScholar  
- [OPERATIONS.md](./OPERATIONS.md) — `DATA_DIR`、备份  
