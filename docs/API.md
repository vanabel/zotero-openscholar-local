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
| GET | `/papers` | 列表；`q=` 搜索；`parse_quality_lte` / `gte` / `missing`；`sort=` |
| GET | `/papers/quality-summary` | 全库解析质量分布 |
| GET | `/papers/{id}/parse-report` | 单篇解析报告（无则 404） |
| GET | `/papers/{id}/document` | Markdown 预览 |
| GET | `/papers/{id}/chunks` | 分块预览 |

## 索引

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/papers/{id}/index` | 解析 + 分块 + 嵌入；默认 **202** + `task_id`；`wait=true` 同步 |
| POST | `/papers/{id}/index?reindex_only=true` | 仅重建分块/嵌入，复用 `document.md` |
| POST | `/papers/{id}/reindex-only` | 同上 |
| POST | `/papers/index-batch` | 批量；body 可含 `paper_ids`（最多 10000）、`force`、`reindex_only` |

## 任务

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/tasks/active` | 进行中任务 |
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
