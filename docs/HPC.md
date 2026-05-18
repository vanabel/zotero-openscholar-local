# 超算（SLURM）批量向量：分块 + 双嵌入

适合 **Mac 本地只解析 PDF**（`document.md`），在 **GPU 集群**上完成分块、`embedding_json`（OpenAI 兼容 API，**无 Ollama**）与 `scholar_embedding_json`（OpenScholar Retriever / CUDA）。

调度器：**SLURM**。通用脚本：`scripts/hpc/submit_vectors.slurm`；西南大学 GridView 集群见下文 **SWU** 专节。

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

## 西南大学超算（SWU / GridView）

已在 **admin03（`ssh swu3`）** 上完成冒烟测试（单篇 `PAPER_IDS` + 全链路脚本）。

| 项目 | 说明 |
|------|------|
| 登录 / 提交 | **`swu3`**（hostname `admin03`），`export PATH=/opt/gridview/slurm/bin:$PATH` |
| 勿用于提交 | **`swu1`**（`admin01`）无 `sbatch`，仅可作跳板 |
| 模块 | **必须** `module load`；统一入口 `scripts/hpc/swu_modules.sh` |
| Python | `apps/python/3.12.3`（勿用 `~/.pyenv`，其自带 SQLite 3.7） |
| CUDA | `apps/cuda/12.2`（与 PyTorch `cu121` wheel 配套） |
| GPU 分区 | `gpu_4090`（RTX 4090，脚本默认）、`hpc_gpu`（A800） |
| SLURM 脚本 | `scripts/hpc/submit_vectors.swu.slurm` |
| 依赖安装 | `bash scripts/hpc/swu_pip_install.sh`（无代理、避免镜像混用） |

### 1. Mac：同步代码与数据

集群 `git clone` 常因 **git `http.proxy=localhost:21087`** 失败，推荐 **rsync**（示例主机名 `swu3`，路径按账号修改）：

```bash
# 仓库（排除 .venv / node_modules）
rsync -az --exclude '.venv' --exclude 'node_modules' \
  ./ swu3:~/zotero-openscholar-local/

# 数据
rsync -az ./apps/api/data/app.sqlite \
          ./apps/api/data/parsed/ \
  swu3:~/zotero-openscholar-local/apps/api/data/

# 超算专用配置（勿提交 git）
scp ./apps/api/.env.hpc swu3:~/zotero-openscholar-local/apps/api/
```

`.env.hpc` 中 **`DATA_DIR`** 须为超算绝对路径，例如：

```env
DATA_DIR=/public/home/<账号>/zotero-openscholar-local/apps/api/data
```

### 2. 登录节点：模块 + venv + pip

```bash
ssh swu3
cd ~/zotero-openscholar-local

# 一键安装（推荐；日志 ~/zos_pip_install.log）
bash scripts/hpc/swu_pip_install.sh
```

脚本会：`source swu_modules.sh` → 建 `.venv` → 从 **PyTorch 官方 `cu121`** 装 `torch`（不装 `torchvision`，避免错误索引拉 numpy 源码）→ 清华源装其余依赖 → 装 **`pysqlite3-binary`**（见下文 SQLite）。

手动等价步骤：

```bash
source scripts/hpc/swu_modules.sh
cd apps/api
python3 -m venv .venv
# 勿使用 git/pip 代理；勿依赖站点 pip.conf 的 extra-index-url
export PIP_CONFIG_FILE=/dev/null
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
```

验证：

```bash
cd apps/api
.venv/bin/python -c "import torch, pysqlite3; print(torch.__version__, pysqlite3.sqlite_version)"
# 登录节点上 torch.cuda.is_available() 常为 False，属正常
```

### 3. 提交作业

```bash
export PATH=/opt/gridview/slurm/bin:$PATH
cd ~/zotero-openscholar-local

# 全库（默认只补缺失：MISSING_ONLY=1）
sbatch scripts/hpc/submit_vectors.swu.slurm

# 冒烟：单篇（parsed 下目录取 paper_id）
sbatch --export=ALL,PAPER_IDS=<paper_id>,MISSING_ONLY=0 \
  scripts/hpc/submit_vectors.swu.slurm

# 强制重算该篇
sbatch --export=ALL,PAPER_IDS=<paper_id>,FORCE=1,MISSING_ONLY=0 \
  scripts/hpc/submit_vectors.swu.slurm
```

| `sbatch --export` 变量 | 默认 | 说明 |
|------------------------|------|------|
| `PAPER_IDS` | 空 | 逗号分隔；空则 `--all` |
| `MISSING_ONLY` | `1` | 仅补缺失 chunk/向量 |
| `FORCE` | `0` | `1` 强制重算 |
| `RUN_CHUNK` / `RUN_EMBED` / `RUN_SCHOLAR` | `1` | 可设 `0` 跳过某步 |
| `DATA_DIR` | `$REPO/apps/api/data` | 与 `.env.hpc` 一致 |

日志：`~/zotero-openscholar-local/zos_vectors_<jobid>.log` / `.err`；队列：`squeue -u $USER`。

### 4. 回传 Mac

```bash
rsync -avz swu3:~/zotero-openscholar-local/apps/api/data/app.sqlite ./apps/api/data/
rsync -avz swu3:~/zotero-openscholar-local/apps/api/data/lance/ ./apps/api/data/lance/
```

### SWU 相关脚本

| 文件 | 用途 |
|------|------|
| `scripts/hpc/swu_modules.sh` | `module load` Python/CUDA + SLURM `PATH` |
| `scripts/hpc/swu_pip_install.sh` | 登录节点无代理安装 `.venv` |
| `scripts/hpc/submit_vectors.swu.slurm` | SWU 分区 + 模块 + 三件套批处理 |

---

## 通用集群：一键提交

### 1. 登录节点

```bash
git clone <repo> ~/zotero-openscholar-local   # 若出网/代理失败，改用 Mac rsync
cd ~/zotero-openscholar-local/apps/api
python3 -m venv .venv
.venv/bin/pip install -e '.[openscholar,lance,hpc]'

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

单篇与强制重算（通用脚本同样支持）：

```bash
sbatch --export=ALL,PAPER_IDS=<paper_id>,FORCE=1,MISSING_ONLY=0 \
  scripts/hpc/submit_vectors.slurm
```

### 4. 回传 Mac

```bash
rsync -avz login:/path/to/synced/data/app.sqlite ./apps/api/data/
rsync -avz login:/path/to/synced/data/lance/ ./apps/api/data/lance/
```

本地 `.env` 可继续 `EMBED_PROVIDER=ollama`（与超算写入的 `embedding_json` 维度/模型需一致：若超算用 `BAAI/bge-m3` 等 API 模型，本地检索也应使用同一嵌入模型）。

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
| `POST /papers/{id}/parse`、文献库 **解析缺失** | 否 | 否 | 否 | 仅 `parsed/`（Mac） |
| `reindex_library.py` | 是 | 是 | 是 | `parsed/`；`reindex_only` 时 PDF 可不在本机 |

## 本地 Mac 推荐操作

1. 文献库：**扫描磁盘** → **同步 Zotero 题录**（可选）。  
2. **解析缺失** 或单篇 **仅解析** — 只写 `data/parsed/{id}/document.md`，**不**分块、**不**嵌入。  
3. rsync `app.sqlite` + `parsed/` 到超算 → `sbatch`（SWU 用 `submit_vectors.swu.slurm`）。  
4. 拉回 `app.sqlite`（及 `lance/`），重启 `pnpm dev`。

若 Mac 上已部分索引，超算设 `MISSING_ONLY=1`（默认）只补缺失向量；冒烟若显示 `skip=1` 表示该篇已有向量，可用 `FORCE=1` 重算。

## 故障排查

| 现象 | 处理 |
|------|------|
| `embed 需要 EMBED_PROVIDER=openai` | 在 `.env.hpc` 设置并 `source` |
| API 429 / 超时 | 减小 `embed_batch --batch-size`；检查配额 |
| `无 chunk` | 先跑 `chunk_batch` 或检查 `parsed/` 是否同步 |
| `PDF 文件不存在`（reindex） | 已支持「有 Markdown 无 PDF」；优先用三件套脚本 |
| scholar CUDA OOM | 减小 `OPENSCHOLAR_ENCODE_BATCH_SIZE` |
| **`sbatch: command not found`** | 在 SWU 改用 **`swu3`**，并 `export PATH=/opt/gridview/slurm/bin:$PATH` |
| **pip / git 走 `localhost:21087` 失败** | `unset` 代理；`git config --global --unset http.proxy`；安装时用 `swu_pip_install.sh` |
| **pip 从 aliyun 下 766MB torch 超时** | `export PIP_CONFIG_FILE=/dev/null`；torch 仅用 `download.pytorch.org/whl/cu121`（见 `swu_pip_install.sh`） |
| **`malformed database schema (chunks_fts)`** | 登录节点 SQLite 过旧（如 3.7）；安装 **`pysqlite3-binary`**（`pip install -e '.[hpc]'` 或安装脚本已包含） |
| 作业三步均为 **skip** | 库中已有向量；加 `FORCE=1` 或换未索引的 `paper_id` |
| 登录节点 **`torch.cuda.is_available()` 为 False** | 正常；以计算节点 GPU 作业日志为准 |

## 参考

- [CONFIGURATION.md](./CONFIGURATION.md) — Provider 与 OpenScholar  
- [OPERATIONS.md](./OPERATIONS.md) — `DATA_DIR`、备份  
