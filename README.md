# zotero-openscholar-local

**单人**个人科研知识库：将 **Zotero 本地 PDF** 解析、分块、检索，用于**文献问答**、**文献综述**与**项目申请书素材**。

技术上：MinerU 或 pypdf → Markdown 分块 → **FTS5** + 可选 **OpenScholar Retriever/Reranker**（**RRF**、跨篇配额）→ 带 `[n]` 引用的问答与综述。与 **[OpenScholar](https://arxiv.org/abs/2411.14199)** 同类「证据检索 + 可核查引用」；**LLM 与索引均为本机/自管**。

**文档**：[docs/README.md](./docs/README.md)（架构、路线图、配置、API、开发、运维）

---

## 功能概览

| 能力 | 说明 |
|------|------|
| Zotero PDF 扫描 | 递归 `storage`，`sha256` / `mtime` 增量；删除标记 `deleted` |
| 解析 | MinerU 3.x（CLI / `mineru-api` / **cloud**）或 **pypdf** 降级 |
| 索引 | 分块、质量分、嵌入；可选 OpenScholar 稠密向量；**202 异步** + 任务进度 |
| 检索 | FTS + RRF + Reranker；标签/集合/年份范围；排除 `references` chunk |
| 问答 / 综述 | 流式、`[n]` 引用、论断核验；申请书模板；Markdown / DOCX 导出 |
| 前端 | Next.js 14：文献库（质量筛选、批量索引）、问答、综述、设置 |

路线图：[docs/ROADMAP.md](./docs/ROADMAP.md)

---

## 快速开始

在**仓库根目录**：

```bash
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local   # 可选

corepack enable
pnpm install
pnpm run setup
pnpm dev          # :8000 API + :3000 Web；cloud 模式不启本机 mineru-api
# pnpm run dev:no-mineru
```

浏览器：<http://localhost:3000> · API：<http://127.0.0.1:8000>

**推荐流程**

1. **设置** — 确认 Zotero PDF 目录（默认 `~/Zotero/storage`）。
2. **文献库 → 扫描磁盘** — 导入 PDF 列表。
3. **批量建立索引**（或单篇）；已有 `document.md` 可用「仅重建索引」。
4. **问答 / 综述** — `[1][2]` 对应引用卡片。

```bash
pnpm test                    # 默认 pytest（隔离临时 DATA_DIR）
pnpm run test:api:optional   # 需 Ollama / MinerU
```

---

## 项目结构

| 路径 | 说明 |
|------|------|
| `apps/api` | FastAPI + SQLite + FTS5 |
| `apps/web` | Next.js 14 |
| `docs/` | 完整文档 |
| `scripts/` | `dev-mineru-api.sh` 等 |

Python 依赖仅安装在 **`apps/api/.venv`**（`pnpm run setup`）。

---

## 进一步阅读

| 主题 | 文档 |
|------|------|
| 环境变量与模型 | [docs/CONFIGURATION.md](./docs/CONFIGURATION.md) |
| HTTP API | [docs/API.md](./docs/API.md) |
| 开发与测试 | [docs/DEVELOPMENT.md](./docs/DEVELOPMENT.md) |
| 备份、VACUUM、数据恢复 | [docs/OPERATIONS.md](./docs/OPERATIONS.md) |
| 质量回归 fixture | [docs/QUALITY_BASELINE.md](./docs/QUALITY_BASELINE.md) |
