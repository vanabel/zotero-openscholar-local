# 运维与数据

## 数据目录（`DATA_DIR`）

| 路径 | 内容 |
|------|------|
| `app.sqlite` | 文献、chunks、FTS、`summaries`、缓存、`tasks` |
| `parsed/{paper_id}/` | `document.md`、MinerU 产物、`meta.json` |

`paper_id` = PDF **绝对路径** 的 SHA256 前 32 位；路径不变则 ID 不变。

## 推荐工作流

1. **设置** — 确认 `ZOTERO_STORAGE_PATH`（默认 `~/Zotero/storage`）。
2. **文献库 → 扫描磁盘** — 写入/更新 `papers` 表。
3. **建立索引** — MinerU / cloud / pypdf → 分块与嵌入。
4. （可选）**摘要缺失** 或单篇 **生成摘要** — 需 LLM（Ollama 等）；展开详情阅读 AI 摘要。
5. **问答 / 综述** — 正文 `[n]` 对应引用卡片。

已有 `parsed/.../document.md` 时可用 **仅重建索引**（`reindex_only`），跳过 MinerU。

## 任务队列运维

| 现象 | 处理 |
|------|------|
| 启动日志 `恢复 N 个未完成任务`，N 很大 | 多为批量入队后中断；文献库 → **任务队列概览** → **取消全部排队**（仅 `queued`，不中断正在跑的 1 条） |
| 待处理任务指向已删文献 | **清理孤儿任务**（`POST /tasks/cancel-orphans`） |
| 取消后 Worker 仍短暂占用 CPU | 内存队列中已入队的 id 会被取出但立即跳过（`status=cancelled`） |
| 文献长期显示 `indexing` 却无任务 | 取消排队时会尝试将无其它 index 任务的文献恢复为 `pending` 或 `indexed`（已有 chunks） |

统计：`GET /tasks/stats`（按 `status` / `task_type` 聚合）。详见 [API.md](./API.md)。

## SQLite 自动压缩（VACUUM）

启动 API 时在 `reconcile` 之后可能执行 `VACUUM`（`app/services/db_maintenance.py`）：

| 配置 | 行为 |
|------|------|
| `DB_VACUUM_FREELIST_RATIO=0.25`（默认） | `freelist_count / page_count ≥ 0.25` 时压缩 |
| `DB_VACUUM_ON_STARTUP=1` | 每次启动强制压缩 |
| `DB_VACUUM_FREELIST_RATIO=0` | 仅 `ON_STARTUP=1` 时压缩 |

大量 `DELETE` 后文件仍很大、表已空，多为**空洞页**；重启 API 或手动：

```bash
cd apps/api
# 先停止 uvicorn / pnpm dev
sqlite3 data/app.sqlite 'VACUUM;'
```

`VACUUM` **不恢复**已删行，只缩小文件。

## 备份与恢复

### 完整恢复（含索引与分块）

需要 **测试/误操作之前** 的 `app.sqlite` 副本（Time Machine、网盘、手动拷贝）。替换当前文件后重启 API。

### 无备份时的部分恢复

| 资产 | 状态 |
|------|------|
| Zotero PDF | 仍在 storage，**扫描磁盘**可重建 `papers` |
| `data/parsed/*/document.md` | 仍在则 **仅重建索引**，无需重跑 MinerU |
| `chunks` / 嵌入 | 需重新索引 |
| `chat_cache` / `review_cache` | 可能在库中保留，语料指纹变化后部分失效 |

### 勿用 pytest 污染开发库

开发库被清空为测试数据（如 `aaaaaaaa…` / `/tmp/alpha.pdf`）时：扫描 Zotero 恢复列表；已修复为每测独立 `DATA_DIR`（见 [DEVELOPMENT.md](./DEVELOPMENT.md)）。

## 启动校准（reconcile）

每次 API 启动会：

- 清理无对应 chunk 的 FTS 孤儿行  
- 按磁盘 `document.md` 修正 `parse_status`  
- 按 `chunks` 表修正 `index_status`  

日志示例：`启动校准 {'fts_orphans_removed': …}`。

## 日志排查

```env
PIPELINE_LOG=1
LOG_STAGES=scan,index,parse,retrieve,db
```

见 [CONFIGURATION.md](./CONFIGURATION.md)。
