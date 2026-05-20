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
                                      （SWU 登录节点补；计算节点可能无外网 DNS）
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

# MinerU 权重（任选其一，见下节「Mac 已有 MinerU」）
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
| `mineru-models` | 见下：仓库 `data/mineru-models` **或** `~/mineru.json` 里的 ModelScope 路径 |

### Mac 已有 MinerU（独立 venv）

若本机已安装，例如：

- CLI：`/Users/vanabel/development/Python/MinerU/.venv/bin/mineru`
- 配置：`~/mineru.json` 的 `models-dir`（常为 `~/.cache/modelscope/hub/models/OpenDataLab/...`）

**Mac** `apps/api/.env`（本地解析 / `pnpm dev`）：

```bash
MINERU_MODE=cli
MINERU_CLI=/Users/vanabel/development/Python/MinerU/.venv/bin/mineru
MINERU_MODEL_SOURCE=local
MINERU_TOOLS_CONFIG_JSON=/Users/vanabel/mineru.json
MINERU_API_URL=http://127.0.0.1:8001
```

**不必**从 Hugging Face 重下。若要把权重整理到仓库 `data/mineru-models/`（可选，便于统一路径）：

```bash
# 先 Ctrl+C 停掉正在跑的 Hugging Face 下载（若还在终端里）
# 默认：从 ~/mineru.json 的 ModelScope 目录链接/复制到 apps/api/data/mineru-models
pnpm run download:mineru-models              # 默认符号链接（秒级、不占双倍磁盘）
# pnpm run download:mineru-models:copy       # 物理复制（体积大、慢）
# pnpm run download:mineru-models:hf         # 仅当本地没有 ModelScope 权重时
```

超算同步**不必**先整理到 `data/mineru-models`，可直接：

```bash
./scripts/hpc/sync_to_hpc.sh mineru-models   # 从 ~/mineru.json 的 models-dir rsync
```

同步到超算时：

```bash
# sync_to_hpc.local.env 默认 LOCAL_MINERU_CONFIG=~/mineru.json
./scripts/hpc/sync_to_hpc.sh mineru-models
```

脚本会按 `models-dir` 的 `vlm` / `pipeline` 路径 rsync 到超算 `data/mineru-models/`，并打印 `mineru.hpc.json` 应用的路径。

**注意**：只同步**权重**，不同步 Mac 的 `MinerU/.venv`（架构不同）。超算上仍用 `swu_pip_install_mineru.sh` 安装 **Linux** 版 `mineru`，`MINERU_CLI` 指向超算 `apps/api/.venv/bin/mineru`。

`sync_to_hpc.local.env` 可选：

```bash
LOCAL_ZOTERO_STORAGE="${HOME}/Zotero/storage"
LOCAL_MINERU_CONFIG="${HOME}/mineru.json"
LOCAL_MINERU_CLI=/Users/vanabel/development/Python/MinerU/.venv/bin/mineru
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
# SWU Python 3.12 / CentOS7 无 onnxruntime wheel；推荐 VLM 后端
MINERU_CLI_EXTRA_ARGS="--backend vlm-auto-engine --source local"
# SWU 计算节点无外网 DNS；本地 MinerU 解析不做低分云端重试
PARSE_QUALITY_RETRY_ENABLED=0
# pipeline / mineru-api 模式才需要：
# MINERU_API_URL=http://127.0.0.1:8001

# 若 PDF 未放在 Zotero storage 镜像目录，可用前缀替换（一般不必）
# HPC_PDF_PATH_PREFIX_OLD=/Users/<你>/Zotero/storage
# HPC_PDF_PATH_PREFIX_NEW=/public/home/<账号>/.../zotero-storage
```

`mineru.hpc.json`：复制 `scripts/hpc/mineru.json.hpc.example` 为 `apps/api/config/mineru.hpc.json`，把 `models-dir` 改为超算绝对路径。

**云端解析**（不占 GPU 权重）：设 `MINERU_MODE=cloud` 与 `MINERU_API_TOKEN`，可跳过 `mineru-models` 同步与 `swu_pip_install_mineru.sh`，作业里 `RUN_MINERU_API=0`。

## 2. 超算：依赖

### 2.1 SWU（西南大学）

登录后若见 `perl: Setting locale failed`，在 **已 `sync code` 之后** 写入 `~/.bashrc`（须判断文件存在，避免首次同步前报错）：

```bash
[ -f ~/zotero-openscholar-local/scripts/hpc/swu_locale.sh ] && \
  source ~/zotero-openscholar-local/scripts/hpc/swu_locale.sh
```

```bash
ssh swu3
cd ~/zotero-openscholar-local
bash scripts/hpc/swu_pip_install.sh          # 向量三件套 + torch
bash scripts/hpc/swu_pip_install_mineru.sh   # MinerU CLI（若 PyPI 失败见脚本日志，按官方文档手动装）
```

当前推荐的 SWU MinerU 路径是 **本地 CLI + 本地权重**：

- `MINERU_MODE=cli`
- `MINERU_CLI=.../apps/api/.venv/bin/mineru`
- `MINERU_MODEL_SOURCE=local`
- `MINERU_TOOLS_CONFIG_JSON=.../apps/api/config/mineru.hpc.json`
- `MINERU_CLI_EXTRA_ARGS="--backend vlm-auto-engine --source local"`
- `PARSE_QUALITY_RETRY_ENABLED=0`

`submit_parse.swu.slurm` 默认不启动独立 `mineru-api`，由 MinerU 3 的 `vlm-auto-engine` 使用本地权重在 GPU 节点解析。已在 swu3 冒烟验证：`mode=mineru`，非 `pypdf_fallback`。

登录节点检查：

```bash
cd ~/zotero-openscholar-local
bash scripts/hpc/test_mineru_cli.sh
```

### 2.2 验证 PDF 路径

```bash
cd apps/api
source ../../scripts/hpc/swu_modules.sh  # SWU
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

# SWU 并行：按当前 gpu_4090 空闲卡数自动切片提交（最多 8 个单卡作业）
bash scripts/hpc/submit_parse_shards.swu.sh

# 手动指定并行片数 / 资源（每片 1 张 4090）
PARSE_SHARDS=8 CPUS_PER_TASK=8 MEM=48G TIME=48:00:00 \
  bash scripts/hpc/submit_parse_shards.swu.sh

# 只预览分片和 sbatch 命令，不提交
DRY_RUN=1 PARSE_SHARDS=8 bash scripts/hpc/submit_parse_shards.swu.sh

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
| `RUN_MINERU_API` | `0` | 本地 `vlm-auto-engine` 不需要；仅 pipeline / 独立 mineru-api 模式设 `1` |

日志：`zos_parse_<jobid>.log` / `.err`。

并行分片脚本 `submit_parse_shards.swu.sh` 会先在登录节点计算待解析 ID，写入
`apps/api/data/hpc_shards/parse_<时间>/shard_*.txt`，再为每个非空分片提交一个
`submit_parse.swu.slurm` 作业。每个作业申请 `--gres=gpu:1`；当前 MinerU 流程是单进程单卡，
所以**多卡加速应提交多个单卡作业**，不要给单个作业申请多卡。

| 分片变量 | 默认 | 说明 |
|----------|------|------|
| `PARSE_SHARDS` | `auto` | 自动按分区空闲 GPU 数提交，最多 `MAX_SHARDS` |
| `MAX_SHARDS` | `8` | 自动模式上限 |
| `PARTITION` | `gpu_4090` | 可改 `hpc_gpu` 试 A800 |
| `GPUS_PER_JOB` | `1` | 建议保持 1 |
| `CPUS_PER_TASK` / `MEM` / `TIME` | `8` / `48G` / `48:00:00` | 传给每个 sbatch |
| `DRY_RUN` | `0` | `1` 只生成分片并打印命令 |

SLURM 队列、日志、取消作业等常用命令见 [HPC.md：SLURM 常用命令](./HPC.md#4-slurm-常用命令swu)。

### 3.2 解析完成后：向量

解析作业 **成功结束后** 再提交向量作业（或依赖链）：

```bash
# 方式 A：手动
sbatch scripts/hpc/submit_vectors.swu.slurm

# 若普通 embedding_json 因计算节点无 DNS 被跳过，在 swu3 登录节点补：
bash scripts/hpc/run_embed_login.swu.sh

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

**推荐**（仓库根目录，单行总进度 + `--stats`；SSH 别名与 `sync_to_hpc.local.env` 一致，默认 `HPC_SSH=swu3`）：

```bash
pnpm run hpc:pull:parsed   # 仅 parsed/
pnpm run hpc:pull:sqlite   # app.sqlite
pnpm run hpc:pull:lance    # lance/
pnpm run hpc:pull:all      # 以上三项
```

底层脚本 `scripts/hpc/sync_from_hpc.sh` 会优先使用 **`/opt/homebrew/bin/rsync`**（支持 `--info=progress2`），并通过 `scripts/hpc/hpc_rsync_rsh.sh` 避免 locale 告警。若只有 macOS 自带的 `/usr/bin/rsync`（openrsync），会自动回退为 `--progress`。

**Mac 安装新版 rsync**（可选，与上行 `sync_to_hpc.sh` 行为一致）：

```bash
brew update && brew install rsync
# 确认：/opt/homebrew/bin/rsync --version   # 3.x
```

**手写 rsync**（等价于 `hpc:pull:parsed`，需已 `brew install rsync`）：

```bash
/opt/homebrew/bin/rsync -avz --info=progress2 --stats \
  -e ./scripts/hpc/hpc_rsync_rsh.sh \
  swu3:~/zotero-openscholar-local/apps/api/data/parsed/ \
  ./apps/api/data/parsed/
```

仅系统 openrsync 时勿用 `--info=progress2`，改用 `--progress --stats`。

本地 `pnpm dev`；Mac 上 PDF 路径未变，无需改库。

## 5. 脚本对照

| 文件 | 用途 |
|------|------|
| `scripts/hpc/sync_to_hpc.sh pdfs` | Mac → 超算 Zotero PDF |
| `scripts/hpc/sync_from_hpc.sh` | 超算 → Mac：`parsed` / `sqlite` / `lance` / `all` |
| `pnpm run hpc:pull:parsed` 等 | 同上（仓库根目录） |
| `scripts/hpc/sync_to_hpc.sh mineru-models` | MinerU 权重 |
| `scripts/hpc/submit_parse.swu.slurm` | SWU：GPU + parse_batch |
| `scripts/hpc/submit_parse_shards.swu.sh` | SWU：把待解析 PDF 切片，提交多个单卡解析作业 |
| `scripts/hpc/submit_parse.slurm` | 通用 SLURM 解析 |
| `scripts/hpc/test_mineru_cli.sh` | 登录节点检查本地 MinerU CLI / 权重 / 配置 |
| `scripts/hpc/start_mineru_api_hpc.sh` | 计算节点启动 mineru-api（pipeline / http-client 模式才用） |
| `scripts/hpc/swu_pip_install_mineru.sh` | SWU 安装 MinerU CLI |
| `apps/api/scripts/parse_batch.py` | 批量 parse_only |
| `app/services/hpc_pdf_path.py` | Mac 路径 → 超算 PDF |

## 6. 故障排查

| 现象 | 处理 |
|------|------|
| `PDF 文件不存在` | 跑 `sync_to_hpc.sh pdfs`；检查 `.env.hpc` 的 `ZOTERO_STORAGE_PATH` |
| 已同步 PDF 但仍提示没有可解析 PDF | Mac 同步来的 `app.sqlite` 可能保存了 `/Users/.../Zotero/storage`；代码已让超算作业优先使用 `.env.hpc` 的 `ZOTERO_STORAGE_PATH`。先 `sync_to_hpc.sh code`，再重跑 |
| `找不到 MinerU` | `swu_pip_install_mineru.sh` 或手动安装；`MINERU_CLI` 指向 `.venv/bin/mineru` |
| mineru-api 启动超时 | 仅 pipeline / http-client 模式相关。SWU 推荐 `vlm-auto-engine`，保持 `RUN_MINERU_API=0` |
| **`No module named mineru.cli.api_client`** | MinerU 2.2.x 无此模块；已修复 `mineru_cli_wrapper.py`。建议 `pip install 'mineru>=3,<4'` 或重新 `swu_pip_install_mineru.sh` |
| **`No module named 'onnxruntime'`** | CLI 默认 `pipeline` 后端需要 onnxruntime；SWU Python 3.12 / CentOS7 无可用 wheel。设置 `MINERU_CLI_EXTRA_ARGS="--backend vlm-auto-engine --source local"` |
| `magika` / `onnxruntime` 出现在 MinerU 3 日志 | `mineru_cli_wrapper.py` 会把 `scripts/mineru_shims` 加入 `PYTHONPATH`。先 `sync_to_hpc.sh code`，再重跑 |
| 日志出现 `低分重试 → cloud` / `mineru.net Name or service not known` | 本地 MinerU 已成功，但质量重试尝试云端。SWU 本地解析设 `PARSE_QUALITY_RETRY_ENABLED=0`，并 `sync_to_hpc.sh env code` |
| 冒烟 `mode=mineru` 但正文是「提取失败」 | 旧 `parsed/` 残留或手写 PDF 无效；`submit_test_mineru` 会 `clear_parsed_output_dir` 并用 reportlab 生成 PDF |
| 解析 skip 很多 | 已有 `document.md` 且 PDF 未变；用 `FORCE=1` |
| 向量阶段 `无 chunk` | 解析作业未成功或未跑；先查 `zos_parse_*.log` |
| 不想在 `all` 里同步 PDF | 用分步：`code` `data` `models` `env`，另单独 `pdfs` |

## 参考

- [HPC.md](./HPC.md) — 仅向量（Mac 已解析）流程  
- [CONFIGURATION.md](./CONFIGURATION.md) — MinerU 环境变量  
