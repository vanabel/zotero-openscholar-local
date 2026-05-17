# 开发

## 环境

- Python ≥ 3.11（`apps/api/.venv`）
- Node.js + pnpm（或 npm）
- 可选：Ollama、MinerU、PyTorch（`[openscholar]`）

**Python 隔离**：依赖只装在 `apps/api/.venv`。勿向系统 Python 全局 `pip install`。

## 启动

仓库根目录：

```bash
corepack enable
pnpm install
pnpm run setup          # .venv + pip install -e ".[dev,hf,openscholar]"
pnpm dev                # mineru-api + API :8000 + Web :3000
pnpm run dev:no-mineru  # 无 MinerU 时
pnpm run dev:external   # API 不入队消费 + 独立 Worker + Web
pnpm run dev:worker     # 仅任务 Worker（需 TASK_WORKER_MODE=external）
```

浏览器：<http://localhost:3000> · API：<http://127.0.0.1:8000>

## 测试

```bash
pnpm test                      # pytest -m 'not optional'
pnpm run test:api:optional     # 需 Ollama / MinerU
```

### 测试数据库隔离

`tests/conftest.py` 为每个用例分配**独立临时** `DATA_DIR`，避免 `DELETE FROM papers` 等清空开发库 `apps/api/data/app.sqlite`。

**不要**对开发库直接跑未隔离的 pytest。若需固定测试目录：

```bash
cd apps/api && DATA_DIR=./data-test .venv/bin/pytest
```

回归：`tests/test_data_dir_isolation.py`、`tests/test_p0_regression.py`（见 [QUALITY_BASELINE.md](./QUALITY_BASELINE.md)）。

任务与摘要相关：`tests/test_task_queue.py`、`tests/test_task_stats.py`、`tests/test_paper_summary_route.py`、`tests/test_paper_batch.py`。

## CI

推送 `main` / `master` 时 `.github/workflows/ci.yml` 运行默认 pytest。

## 仅重建索引（开发）

```bash
pnpm run reindex:all
pnpm run reindex -- --paper-id <id>
```

## PM2（非热重载）

```bash
npm run setup
npx pm2 start ecosystem.config.cjs
```

## 手动分终端

**API**

```bash
cd apps/api
python3 -m venv .venv && .venv/bin/pip install -e ".[dev,hf,openscholar]"
cp .env.example .env
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

**Web**

```bash
cd apps/web && npm install && cp .env.example .env.local && npm run dev
```

## 项目结构

| 路径 | 说明 |
|------|------|
| `apps/api/app` | FastAPI 应用 |
| `apps/api/tests` | pytest + fixtures |
| `apps/web` | Next.js 前端 |
| `docs/` | 文档 |
| `scripts/` | 开发脚本 |
