from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

ProviderName = Literal["ollama", "openai", "transformers"]
from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api 目录（含 .env）；配置加载不依赖进程 cwd，避免从仓库根启动时读到错误的 .env
_API_DIR = Path(__file__).resolve().parents[1]
API_ENV_FILE = _API_DIR / ".env"
# 仓库根（含 apps/、pnpm-workspace.yaml 等）。config.py 在 apps/api/app/ 下，向上 3 级到仓库根。
REPO_ROOT = Path(__file__).resolve().parents[3]

_DOTENV_FILES: tuple[str, ...] = (str(API_ENV_FILE),) if API_ENV_FILE.is_file() else ()


def path_relative_to_repo(p: Path | None) -> str | None:
    """路径若在 REPO_ROOT 下则返回 posix 相对路径，否则返回展开后的绝对路径字符串。"""
    if p is None:
        return None
    try:
        ap = p.expanduser().resolve(strict=False)
        rr = REPO_ROOT.resolve(strict=False)
        rel = ap.relative_to(rr)
        return rel.as_posix()
    except (ValueError, OSError):
        return str(p.expanduser())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_DOTENV_FILES if _DOTENV_FILES else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Path("./data")
    zotero_storage_path: Path = Path.home() / "Zotero" / "storage"
    zotero_sqlite_path: Path | None = Path.home() / "Zotero" / "zotero.sqlite"

    @field_validator("zotero_sqlite_path", mode="before")
    @classmethod
    def _empty_zotero_sqlite_path(cls, v):
        """环境变量设为空字符串时视为关闭（不读 zotero.sqlite）。"""
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = "qwen2.5:7b"
    ollama_embed_model: str = "nomic-embed-text"
    # auto：有 OPENAI_API_KEY+BASE 时用 openai，否则 ollama；可显式 ollama/openai 混用
    chat_provider: str = Field(default="auto", validation_alias="CHAT_PROVIDER")
    embed_provider: str = Field(default="auto", validation_alias="EMBED_PROVIDER")

    # 双语检索/答案：将 ModelScope 等 GGUF 导入 Ollama 后填写模型名（如 hy-mt1.5）
    bilingual_retrieval: bool = Field(default=False, validation_alias="BILINGUAL_RETRIEVAL")
    bilingual_answer: bool = Field(default=True, validation_alias="BILINGUAL_ANSWER")

    retrieve_top_k_fts: int = Field(default=40, ge=5, le=200, validation_alias="RETRIEVE_TOP_K_FTS")
    retrieve_top_k_final: int = Field(default=8, ge=1, le=100, validation_alias="RETRIEVE_TOP_K_FINAL")
    # 跨篇均衡：单篇最多保留几条 chunk；0 表示不限制每篇条数
    retrieve_max_chunks_per_paper: int = Field(
        default=3, ge=0, le=20, validation_alias="RETRIEVE_MAX_CHUNKS_PER_PAPER"
    )
    # 最多纳入几篇不同文献；0 表示不限制文献篇数
    retrieve_max_papers: int = Field(default=8, ge=0, le=50, validation_alias="RETRIEVE_MAX_PAPERS")
    retrieve_query_synonyms_enabled: bool = Field(
        default=True, validation_alias="RETRIEVE_QUERY_SYNONYMS_ENABLED"
    )
    retrieve_query_synonyms_path: str = Field(default="", validation_alias="RETRIEVE_QUERY_SYNONYMS_PATH")
    retrieve_query_synonyms_max_variants: int = Field(
        default=4, ge=0, le=20, validation_alias="RETRIEVE_QUERY_SYNONYMS_MAX_VARIANTS"
    )

    openscholar_retriever_enabled: bool = Field(default=True, validation_alias="OPENSCHOLAR_RETRIEVER_ENABLED")
    openscholar_reranker_enabled: bool = Field(default=True, validation_alias="OPENSCHOLAR_RERANKER_ENABLED")
    openscholar_retriever_model: str = Field(
        default="OpenSciLM/OpenScholar_Retriever",
        validation_alias="OPENSCHOLAR_RETRIEVER_MODEL",
    )
    openscholar_reranker_model: str = Field(
        default="OpenSciLM/OpenScholar_Reranker",
        validation_alias="OPENSCHOLAR_RERANKER_MODEL",
    )
    openscholar_device: str = Field(default="auto", validation_alias="OPENSCHOLAR_DEVICE")
    openscholar_retriever_max_length: int = Field(default=512, ge=128, le=1024, validation_alias="OPENSCHOLAR_RETRIEVER_MAX_LENGTH")
    openscholar_encode_batch_size: int = Field(default=8, ge=1, le=64, validation_alias="OPENSCHOLAR_ENCODE_BATCH_SIZE")
    openscholar_rerank_batch_size: int = Field(default=8, ge=1, le=64, validation_alias="OPENSCHOLAR_RERANK_BATCH_SIZE")
    openscholar_rerank_max_chars: int = Field(default=1800, ge=256, le=8000, validation_alias="OPENSCHOLAR_RERANK_MAX_CHARS")
    openscholar_rerank_pool: int = Field(default=80, ge=10, le=200, validation_alias="OPENSCHOLAR_RERANK_POOL")
    # 主对话 Transformers 权重（HF id 或本地目录）；留空时可从 OLLAMA_CHAT_MODEL 的 OpenScholar GGUF 名推断
    openscholar_chat_model: str = Field(default="", validation_alias="OPENSCHOLAR_CHAT_MODEL")
    openscholar_chat_device: str = Field(default="auto", validation_alias="OPENSCHOLAR_CHAT_DEVICE")
    openscholar_chat_max_new_tokens: int = Field(
        default=4096, ge=256, le=16384, validation_alias="OPENSCHOLAR_CHAT_MAX_NEW_TOKENS"
    )
    openscholar_summary_max_new_tokens: int = Field(
        default=1024, ge=128, le=4096, validation_alias="OPENSCHOLAR_SUMMARY_MAX_NEW_TOKENS"
    )
    translation_ollama_model: str = Field(default="", validation_alias="TRANSLATION_OLLAMA_MODEL")
    translation_ollama_url: str | None = Field(default=None, validation_alias="TRANSLATION_OLLAMA_URL")
    translation_temperature: float = Field(default=0.1, ge=0.0, le=1.0, validation_alias="TRANSLATION_TEMPERATURE")

    chat_cache_enabled: bool = Field(default=True, validation_alias="CHAT_CACHE_ENABLED")
    chat_cache_ttl_sec: int = Field(default=604800, ge=0, validation_alias="CHAT_CACHE_TTL_SEC")

    openai_api_base: str | None = None
    openai_api_key: str | None = None
    openai_chat_model: str = "gpt-4o-mini"
    openai_embed_model: str = Field(default="text-embedding-3-small", validation_alias="OPENAI_EMBED_MODEL")

    # cli：本机 MinerU CLI；cloud：MinerU 在线 API（https://mineru.net）
    mineru_mode: str = Field(default="cli", validation_alias="MINERU_MODE")
    mineru_api_base_url: str = Field(default="https://mineru.net", validation_alias="MINERU_API_BASE_URL")
    mineru_api_token: str | None = Field(default=None, validation_alias="MINERU_API_TOKEN")
    mineru_cloud_model_version: str = Field(default="vlm", validation_alias="MINERU_CLOUD_MODEL_VERSION")
    mineru_cloud_poll_interval_sec: float = Field(
        default=5.0, ge=2.0, le=60.0, validation_alias="MINERU_CLOUD_POLL_INTERVAL_SEC"
    )
    # MinerU 在线 API 单文件页数上限（超出则自动按页切片后多次请求再合并 Markdown）
    mineru_cloud_max_pages_per_chunk: int = Field(
        default=200, ge=10, le=500, validation_alias="MINERU_CLOUD_MAX_PAGES_PER_CHUNK"
    )

    mineru_cli: str = "mineru"
    parse_timeout_sec: int = 3600
    # MinerU 3.x 使用 -p/-o；旧版可设 MINERU_CLI_STYLE=legacy（positional pdf + -o）
    mineru_cli_style: str = Field(default="v3", validation_alias="MINERU_CLI_STYLE")
    # 若已常驻 mineru-api，填写其 base URL，解析时将附带 --api-url（省略则由 CLI 每次起临时服务）
    mineru_api_url: str | None = Field(default=None, validation_alias="MINERU_API_URL")
    # 追加传给 MinerU CLI 的参数，例如：--backend vlm-auto-engine --source local
    mineru_cli_extra_args: str | None = Field(default=None, validation_alias="MINERU_CLI_EXTRA_ARGS")
    # MinerU 子进程环境：设为 local 时需配置 models-dir（见 config/mineru.json.example 与 scripts/download_mineru_local_models.py）
    mineru_model_source: str | None = Field(default=None, validation_alias="MINERU_MODEL_SOURCE")
    # 指向 mineru.json 绝对路径；不设则 MinerU 默认读 ~/.mineru.json 或 ~/mineru.json（见 MinerU 的 MINERU_TOOLS_CONFIG_JSON）
    mineru_tools_config_json: str | None = Field(default=None, validation_alias="MINERU_TOOLS_CONFIG_JSON")
    # mineru CLI 轮询 mineru-api 任务状态的间隔（秒）；hybrid 每步约 20s+ 时默认 8 可减少 access log
    mineru_task_poll_interval_sec: float = Field(default=8.0, ge=1.0, le=120.0, validation_alias="MINERU_TASK_POLL_INTERVAL_SEC")

    # 解析质量低于阈值时自动重试（云端 / 备用 model_version）
    parse_quality_retry_enabled: bool = Field(default=True, validation_alias="PARSE_QUALITY_RETRY_ENABLED")
    parse_quality_retry_threshold: float = Field(
        default=0.65, ge=0.0, le=1.0, validation_alias="PARSE_QUALITY_RETRY_THRESHOLD"
    )
    mineru_cloud_model_version_retry: str = Field(
        default="pipeline", validation_alias="MINERU_CLOUD_MODEL_VERSION_RETRY"
    )

    # LanceDB 稠密向量索引（替代 SQLite 全表 scholar 扫描）
    lancedb_enabled: bool = Field(default=True, validation_alias="LANCEDB_ENABLED")

    # 任务队列：embedded=API 进程内 Worker；external=仅 scripts/run_task_worker.py 消费
    task_worker_mode: str = Field(default="embedded", validation_alias="TASK_WORKER_MODE")
    task_worker_concurrency: int = Field(default=1, ge=1, le=16, validation_alias="TASK_WORKER_CONCURRENCY")
    mineru_parse_concurrency: int = Field(default=1, ge=1, le=128, validation_alias="MINERU_PARSE_CONCURRENCY")
    index_embed_concurrency: int = Field(default=2, ge=1, le=8, validation_alias="INDEX_EMBED_CONCURRENCY")

    # 启动时 SQLite VACUUM：强制每次执行，或 freelist/page_count ≥ 比例阈值时自动执行
    db_vacuum_on_startup: bool = Field(default=False, validation_alias="DB_VACUUM_ON_STARTUP")
    db_vacuum_freelist_ratio: float = Field(
        default=0.25, ge=0.0, le=1.0, validation_alias="DB_VACUUM_FREELIST_RATIO"
    )

    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    pipeline_log: int = Field(default=0, ge=0, le=2, validation_alias="PIPELINE_LOG")
    log_stages: str = Field(default="", validation_alias="LOG_STAGES")
    log_context: bool = Field(default=True, validation_alias="LOG_CONTEXT")

    @field_validator("task_worker_mode", mode="before")
    @classmethod
    def _normalize_task_worker_mode(cls, v):
        if v is None:
            return "embedded"
        return str(v).strip().lower()

    @field_validator("chat_provider", "embed_provider", mode="before")
    @classmethod
    def _normalize_provider(cls, v):
        if v is None:
            return "auto"
        if isinstance(v, str) and not v.strip():
            return "auto"
        return str(v).strip().lower()

    @model_validator(mode="after")
    def _validate_providers(self) -> Settings:
        for field, val in (("chat_provider", self.chat_provider), ("embed_provider", self.embed_provider)):
            if val not in ("auto", "ollama", "openai", "transformers"):
                raise ValueError(f"{field} must be one of: auto, ollama, openai, transformers (got {val!r})")
        if self.task_worker_mode not in ("embedded", "external"):
            raise ValueError("task_worker_mode must be embedded or external")
        return self

    def openai_ready(self) -> bool:
        return bool((self.openai_api_key or "").strip() and (self.openai_api_base or "").strip())

    def resolved_chat_provider(self) -> ProviderName:
        p = self.chat_provider
        if p == "auto":
            return "openai" if self.openai_ready() else "ollama"
        if p == "transformers":
            return "transformers"
        return p  # type: ignore[return-value]

    def resolved_embed_provider(self) -> ProviderName:
        p = self.embed_provider
        if p == "auto":
            return "openai" if self.openai_ready() else "ollama"
        return p  # type: ignore[return-value]

    def effective_openscholar_chat_model(self) -> str:
        """OpenScholar-8B 的 Transformers 权重路径（HF id 或本地目录）。

        顺序：显式 ``OPENSCHOLAR_CHAT_MODEL`` → ``~/models/openscholar-ms-8b``（若权重完整）
        → 由 ``OLLAMA_CHAT_MODEL`` 的 OpenScholar GGUF 名映射到 HF id。
        """
        explicit = (self.openscholar_chat_model or "").strip()
        if explicit:
            return explicit
        local = resolve_local_openscholar_chat_dir()
        if local:
            return local
        mapped = _hf_chat_model_from_ollama_tag(self.ollama_chat_model or "")
        if mapped:
            return mapped
        return _DEFAULT_OPENSCHOLAR_HF_CHAT

    @model_validator(mode="after")
    def _resolve_data_dir_and_clamp_retrieve(self) -> Settings:
        """相对 DATA_DIR 在加载配置时锚定到绝对路径，避免换工作目录后连到另一份 app.sqlite。"""
        dd = self.data_dir.expanduser()
        if not dd.is_absolute():
            dd = (Path.cwd() / dd).resolve()
        else:
            dd = dd.resolve()
        object.__setattr__(self, "data_dir", dd)
        if self.retrieve_top_k_final > self.retrieve_top_k_fts:
            object.__setattr__(self, "retrieve_top_k_final", self.retrieve_top_k_fts)
        # Transformers 8B 在单进程内共享一把推理锁；并发>1 只会堆「chat 开始」、无法真正并行 GPU
        if self.resolved_chat_provider() == "transformers" and self.task_worker_concurrency > 1:
            object.__setattr__(self, "task_worker_concurrency", 1)
        return self

    @property
    def db_path(self) -> Path:
        p = self.data_dir / "app.sqlite"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def parsed_dir(self) -> Path:
        p = self.data_dir / "parsed"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def lance_dir(self) -> Path:
        p = self.data_dir / "lance"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def task_worker_embedded(self) -> bool:
        return (self.task_worker_mode or "embedded").strip().lower() != "external"


_DEFAULT_OPENSCHOLAR_HF_CHAT = "OpenSciLM/Llama-3.1_OpenScholar-8B"

# 常见 Ollama OpenScholar-8B GGUF 标签 → 官方 HF 全量权重（同一模型，不同打包）
_OLLAMA_OPENSCHOLAR_GGUF_TO_HF: dict[str, str] = {
    "hf.co/quantfactory/llama-3.1_openscholar-8b-gguf:q4_k_m": _DEFAULT_OPENSCHOLAR_HF_CHAT,
}

# ``ls ~/models`` 下 Transformers 主对话目录（按优先级）
_LOCAL_OPENSCHOLAR_CHAT_DIR_NAMES = (
    "openscholar-ms-8b",
    "Llama-3.1_OpenScholar-8B",
    "OpenScholar-8B",
)


def _local_models_root() -> Path:
    return (Path.home() / "models").expanduser().resolve()


def is_usable_hf_model_dir(path: Path) -> bool:
    """目录含 config.json 且根目录有完整权重（非仅 tokenizer / 未完成下载）。"""
    if not path.is_dir() or not (path / "config.json").is_file():
        return False
    if (path / "model.safetensors").is_file() or (path / "pytorch_model.bin").is_file():
        return True
    if list(path.glob("model-*-of-*.safetensors")) or list(path.glob("pytorch_model-*.bin")):
        return True
    return False


def resolve_local_openscholar_chat_dir() -> str | None:
    """``~/models`` 下可用的 OpenScholar-8B HF 目录；权重未下完则返回 None。"""
    root = _local_models_root()
    if not root.is_dir():
        return None
    for name in _LOCAL_OPENSCHOLAR_CHAT_DIR_NAMES:
        candidate = root / name
        if is_usable_hf_model_dir(candidate):
            return str(candidate)
    return None


def _hf_chat_model_from_ollama_tag(ollama_model: str) -> str | None:
    """Ollama 模型名不能用于 Transformers；仅识别 OpenScholar-8B GGUF 并返回对应 HF id。"""
    key = ollama_model.strip().lower()
    if not key:
        return None
    if key in _OLLAMA_OPENSCHOLAR_GGUF_TO_HF:
        return _OLLAMA_OPENSCHOLAR_GGUF_TO_HF[key]
    if "openscholar" in key and ("gguf" in key or "quantfactory" in key):
        return _DEFAULT_OPENSCHOLAR_HF_CHAT
    return None


settings = Settings()
