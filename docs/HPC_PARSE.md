# 超算解析 + 向量（PDF rsync → MinerU → 三件套）

在 **Mac 只扫库、不同步解析** 时，把 PDF 与 `app.sqlite` 送上超算，用 **GPU + MinerU** 生成 `parsed/document.md`，再跑 [HPC.md](./HPC.md) 中的分块与双嵌入。

与「Mac 本地解析 + 超算只向量」相比，本流程把 **MinerU 算力** 放在集群上。

## 流程概览

```text
Mac（本地）                         超算（SLURM）
──────────                         ────────────
扫描 Zotero → app.sqlite      →    rsync：app.sqlite
（可不解析）                       rsync：Zotero/storage/*.pdf
                                   rsync：mineru-models（可选，本地权重）

                                   1. parse_batch.py     → parsed/document.md
                                   2. chunk_batch.py     → chunks
                                   3. embed_batch.py     → embedding_json
                                   4. scholar_embed_batch → scholar_embedding_json

rsync 下行                      ←   app.sqlite + parsed/ + lance/
```

**`paper_id`** 仍由 Mac 上 PDF **绝对路径** 哈希；**勿在超算重新扫库**。库内 `pdf_path` 可以是 Mac 路径；解析时通过 `ZOTERO_STORAGE_PATH` 或前缀映射定位超算上的 PDF（见下文）。

## 1. Mac：配置与同步

### 1.1 同步脚本

与 [HPC.md](./HPC.md) 相同，先配置 `scripts/hpc/sync_to_hpc.local.env` 与 `apps/api/.env.hpc`。

```bash
# 仓库与库（题录 + 已有 parsed 若有）
./scripts/hpc/sync_to_hpc.sh code
./scripts/hpc/sync_to_hpc.sh data

# Zotero 附件 PDF（仅 *.pdf，可多次增量）
./scripts/hpc/sync_to_hpc.sh pdfs

# MinerU 本地权重（Mac 先 pnpm run download:mineru-models）
./scripts/hpc/sync_to_hpc.sh mineru-models

# OpenScholar Retriever + 环境
./scripts/hpc/sync_to_hpc.sh models
./scripts/hpc/sync_to_hpc.sh env

# 或一次（含 PDF + MinerU 权重，耗时长）
./scripts/hpc/sync_to_hpc.sh all
```

| 子命令 | 内容 |
|--------|------|
| `pdfs` | `~/Zotero/storage` → 超算 `apps/api/data/zotero-storage`（可 `REMOTE_ZOTERO_STORAGE` 覆盖） |
| `mineru-models` | `apps/api/data/mineru-models` → 超算同路径 |

`sync_to_hpc.local.env` 可选：

```bash
LOCAL_ZOTERO_STORAGE="${HOME}/Zotero/storage"
# REMOTE_ZOTERO_STORAGE=/public/home/<账号>/zotero-storage
```

### 1.2 `.env.hpc` 解析相关

在 `apps/api/.env.hpc.example` 基础上增加（路径按超算账号修改）：

```bash
DATA_DIR=/public/home/<账号>/zotero-openscholar-local/apps/api/data
ZOTERO_STORAGE_PATH=/public/home/<账号>/zotero-openscholar-local/apps/api/data/zotero-storage

MINERU_MODE=cli
MINERU_CLI=/public/home/<账号>/zotero-openscholar-local/apps/api/.venv/bin/mineru
MINERU_MODEL_SOURCE=local
MINERU_TOOLS_CONFIG_JSON=/public/home/<账号>/zotero-openscholar-local/apps/api/config/mineru.hpc.json
MINERU_API_URL=http://127.0.0.1:8001

# 若 PDF 未放在 Zotero storage 镜像目录，可用前缀替换（一般不必）
# HPC_PDF_PATH_PREFIX_OLD=/Users/<你>/Zotero/storage
# HPC_PDF_PATH_PREFIX_NEW=/public/home/<账号>/.../zotero-storage
```

`mineru.hpc.json`：复制 `scripts/hpc/mineru.json.hpc.example` 为 `apps/api/config/mineru.hpc.json`，把 `models-dir` 改为超算绝对路径。

**云端解析**（不占 GPU 权重）：设 `MINERU_MODE=cloud` 与 `MINERU_API_TOKEN`，可跳过 `mineru-models` 同步与 `swu_pip_install_mineru.sh`，作业里 `RUN_MINERU_API=0`。

## 2. 超算：依赖

### 2.1 SWU（西南大学）

```bash
ssh swu3
cd ~/zotero-openscholar-local
bash scripts/hpc/swu_pip_install.sh          # 向量三件套 + torch
bash scripts/hpc/swu_pip_install_mineru.sh   # MinerU CLI（若 PyPI 失败见脚本日志，按官方文档手动装）
```

### 2.2 验证 PDF 路径

```bash
cd apps/api
source ../scripts/hpc/swu_modules.sh  # SWU
set -a && source .env.hpc && set +a
.venv/bin/python -c "
from app.db import init_db, set_zotero_storage_path
from pathlib import Path
import os
init_db()
from app.config import settings
from app.services.hpc_pdf_path import resolve_pdf_path
from app.db import get_db
row = get_db().__enter__().execute('SELECT pdf_path FROM papers WHERE deleted=0 LIMIT 1').fetchone()
print('sample', row['pdf_path'] if row else None)
if row: print('resolved', resolve_pdf_path(row['pdf_path']))
"
```

## 3. 提交作业

### 3.1 仅解析（MinerU）

```bash
export PATH=/opt/gridview/slurm/bin:$PATH   # SWU
cd ~/zotero-openscholar-local

# SWU
sbatch scripts/hpc/submit_parse.swu.slurm

# 冒烟单篇
sbatch --export=ALL,PAPER_IDS=<paper_id>,MISSING_ONLY=0 \
  scripts/hpc/submit_parse.swu.slurm

# 通用集群
sbatch scripts/hpc/submit_parse.slurm
```

| `sbatch --export` | 默认 | 说明 |
|-------------------|------|------|
| `PAPER_IDS` | 空 | 逗号分隔；空则 `--all` |
| `MISSING_ONLY` | `1` | 仅缺 `document.md` 或 PDF 已变更 |
| `FORCE` | `0` | `1` 强制重解析 |
| `RUN_MINERU_API` | `1` | `0` 表示已手动常驻 mineru-api 或 cloud 模式 |

日志：`zos_parse_<jobid>.log` / `.err`。

### 3.2 解析完成后：向量

解析作业 **成功结束后** 再提交向量作业（或依赖链）：

```bash
# 方式 A：手动
sbatch scripts/hpc/submit_vectors.swu.slurm

# 方式 B：依赖上一作业（示例 jobid=12345）
sbatch --dependency=afterok:12345 scripts/hpc/submit_vectors.swu.slurm
```

向量步骤与 [HPC.md](./HPC.md) 完全一致；`parsed/` 已在超算本地，**无需** 再从 Mac 同步 `parsed/`（除非你在 Mac 上又解析过）。

### 3.3 本地调试命令

```bash
cd apps/api
# 需 .env 或 .env.hpc：MinerU + ZOTERO_STORAGE_PATH
.venv/bin/python scripts/parse_batch.py --all --missing-only
pnpm run hpc:parse    # 仓库根目录
pnpm run hpc:vectors  # 解析完成后的三件套
```

## 4. 回传 Mac

```bash
rsync -avz swu3:~/zotero-openscholar-local/apps/api/data/app.sqlite ./apps/api/data/
rsync -avz swu3:~/zotero-openscholar-local/apps/api/data/parsed/ ./apps/api/data/parsed/
rsync -avz swu3:~/zotero-openscholar-local/apps/api/data/lance/ ./apps/api/data/lance/
```

本地 `pnpm dev`；Mac 上 PDF 路径未变，无需改库。

## 5. 脚本对照

| 文件 | 用途 |
|------|------|
| `scripts/hpc/sync_to_hpc.sh pdfs` | Mac → 超算 Zotero PDF |
| `scripts/hpc/sync_to_hpc.sh mineru-models` | MinerU 权重 |
| `scripts/hpc/submit_parse.swu.slurm` | SWU：GPU + parse_batch |
| `scripts/hpc/submit_parse.slurm` | 通用 SLURM 解析 |
| `scripts/hpc/start_mineru_api_hpc.sh` | 计算节点启动 mineru-api |
| `scripts/hpc/swu_pip_install_mineru.sh` | SWU 安装 MinerU CLI |
| `apps/api/scripts/parse_batch.py` | 批量 parse_only |
| `app/services/hpc_pdf_path.py` | Mac 路径 → 超算 PDF |

## 6. 故障排查

| 现象 | 处理 |
|------|------|
| `PDF 文件不存在` | 跑 `sync_to_hpc.sh pdfs`；检查 `.env.hpc` 的 `ZOTERO_STORAGE_PATH` |
| `找不到 MinerU` | `swu_pip_install_mineru.sh` 或手动安装；`MINERU_CLI` 指向 `.venv/bin/mineru` |
| mineru-api 启动超时 | 看 `~/zos_mineru_api.log`；权重路径是否在 `mineru.hpc.json` |
| 解析 skip 很多 | 已有 `document.md` 且 PDF 未变；用 `FORCE=1` |
| 向量阶段 `无 chunk` | 解析作业未成功或未跑；先查 `zos_parse_*.log` |
| 不想在 `all` 里同步 PDF | 用分步：`code` `data` `models` `env`，另单独 `pdfs` |

## 参考

- [HPC.md](./HPC.md) — 仅向量（Mac 已解析）流程  
- [CONFIGURATION.md](./CONFIGURATION.md) — MinerU 环境变量  
