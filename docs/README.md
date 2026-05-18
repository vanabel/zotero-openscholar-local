# 文档索引

本目录为 **zotero-openscholar-local** 的完整说明；仓库根 [README.md](../README.md) 仅保留概览与快速开始。

| 文档 | 内容 |
|------|------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 六层架构、数据流、与 OpenScholar 的关系 |
| [ROADMAP.md](./ROADMAP.md) | 质量目标驱动的路线图（P0–P7） |
| [CONFIGURATION.md](./CONFIGURATION.md) | 环境变量、模型、MinerU、日志 |
| [API.md](./API.md) | HTTP API 参考 |
| [DEVELOPMENT.md](./DEVELOPMENT.md) | 开发、测试、CI、PM2 |
| [OPERATIONS.md](./OPERATIONS.md) | 数据目录、备份恢复、SQLite 维护 |
| [HPC.md](./HPC.md) | SLURM 批量向量；含 SWU（`swu3`、模块加载、`swu_pip_install.sh`） |
| [QUALITY_BASELINE.md](./QUALITY_BASELINE.md) | P0 回归 fixture 与 P3/P4 评测占位 |

维护约定：实现功能时同步更新 **ROADMAP** 状态、根 **README** 功能表、`apps/api/.env.example` 与 **API.md** / **ARCHITECTURE.md** 等本目录章节。
