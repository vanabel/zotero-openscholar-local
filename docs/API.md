# API 参考

默认基址：<http://127.0.0.1:8000>。数据写入 `DATA_DIR`（默认 `apps/api/data`）。

## 健康与统计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/stats` | 文献 / 索引 / 片段统计 |

## 文献与扫描

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/scan` | 扫描 Zotero storage（增量） |
| POST | `/papers/sync-zotero-metadata` | 从 `zotero.sqlite` 同步题录 |
| GET | `/papers` | 列表；`q=` 搜索；`parse_quality_lte` / `gte` / `missing`；`sort=`；含 `has_paper_summary` |
| GET | `/papers/quality-summary` | 全库解析质量分布 |
| GET | `/papers/{id}` | 单篇元数据 |
| GET | `/papers/{id}/parse-report` | 单篇解析报告（无则 404） |
| GET | `/papers/{id}/parse-meta` | `parsed/{id}/meta.json`（MinerU 模式等） |
| GET | `/papers/{id}/document` | Markdown 预览 |
| GET | `/papers/{id}/chunks` | 分块预览 |
| GET | `/papers/{id}/summary` | AI 摘要（`paper_summary`；无则 404） |
| POST | `/papers/{id}/summarize` | 单篇入队摘要；默认 **202** + `task_id`；`wait=true` 同步 |

## 索引

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/papers/{id}/index` | 解析 + 分块 + 嵌入；默认 **202** + `task_id`；`wait=true` 同步 |
| POST | `/papers/{id}/index?reindex_only=true` | 仅重建分块/嵌入，复用 `document.md` |
| POST | `/papers/{id}/reindex-only` | 同上 |
| POST | `/papers/index-batch` | 批量；body 可含 `paper_ids`（最多 10000）、`force`、`reindex_only` |
| POST | `/papers/index-missing` | 为未 indexed 文献入队；body 可选 `limit`、`force`、`reindex_only` |
| POST | `/papers/parse-missing` | 为无 `document.md` 文献入队解析 |
| POST | `/papers/summarize-missing` | 为已 indexed 且无 `paper_summary` 文献入队摘要（需 LLM） |
| POST | `/papers/rescore-unscored` | 未评分且有 `document.md`：仅补 `parse_quality_score`（不跑 MinerU） |
| POST | `/papers/{id}/rescore-parse-quality` | 单篇补解析质量分 |
| POST | `/papers/sync-lance-indexed` | 将已有 `scholar_embedding_json` 写入 LanceDB（不重新分块/嵌入）；body 可选 `paper_ids` / `limit` |
| POST | `/papers/{id}/sync-lance` | 单篇同步 Lance |

## 任务

`task_type`：`index`（解析+分块+嵌入）| `summarize`（生成 `paper_summary`）。  
`status`：`queued` | `running` | `completed` | `failed` | `cancelled`。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/tasks/active` | 进行中任务；可选 `paper_ids=` 逗号分隔 |
| GET | `/tasks/active/stream` | SSE：任务进度与状态推送 |
| GET | `/tasks/stats` | 全表任务统计（按 status / task_type）；`failed_limit=` 最近失败样本 |
| POST | `/tasks/cancel-queued` | 取消全部 `queued`（不中断 `running`）；恢复卡在 `indexing` 的文献状态 |
| POST | `/tasks/cancel-orphans` | 清理指向已删/不存在文献的 `queued`/`running` 任务 |
| GET | `/tasks/{id}` | 状态与 `progress_json` |

## 问答

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat` | JSON；可含 `tags_any` / `collections_any` / `years_*`；返回 `claims` |
| POST | `/chat/stream` | SSE：`citations` → `token` → 可选 `bilingual*` → `done` |
| GET | `/chat/recent` | 近期提问 |

## 综述

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/review` | `template=literature_review` \| `grant_proposal` |
| POST | `/review/stream` | 流式 |
| POST | `/review/export-markdown` | 导出 Markdown |
| POST | `/review/export-docx` | 导出 DOCX（需 `python-docx`） |
| GET | `/review/recent` | 近期主题 |

## 设置与其它

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/PUT | `/settings` | Zotero 路径等 |
| GET | `/chunks/{id}` | 片段详情 |

## 脚本等价

```bash
pnpm run reindex:all
pnpm run reindex -- --paper-id <id>
```

等价于 `reindex_only=true` 的 API 调用（勿与 `force=true` 同用）。
