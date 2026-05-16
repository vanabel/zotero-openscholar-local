from pathlib import Path

from pydantic import Field, field_validator, model_validator
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

    # 双语检索/答案：将 ModelScope 等 GGUF 导入 Ollama 后填写模型名（如 hy-mt1.5）
    bilingual_retrieval: bool = Field(default=False, validation_alias="BILINGUAL_RETRIEVAL")
    bilingual_answer: bool = Field(default=True, validation_alias="BILINGUAL_ANSWER")

    retrieve_top_k_fts: int = Field(default=40, ge=5, le=200, validation_alias="RETRIEVE_TOP_K_FTS")
    retrieve_top_k_final: int = Field(default=8, ge=1, le=100, validation_alias="RETRIEVE_TOP_K_FINAL")

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
    translation_ollama_model: str = Field(default="", validation_alias="TRANSLATION_OLLAMA_MODEL")
    translation_ollama_url: str | None = Field(default=None, validation_alias="TRANSLATION_OLLAMA_URL")
    translation_temperature: float = Field(default=0.1, ge=0.0, le=1.0, validation_alias="TRANSLATION_TEMPERATURE")

    chat_cache_enabled: bool = Field(default=True, validation_alias="CHAT_CACHE_ENABLED")
    chat_cache_ttl_sec: int = Field(default=604800, ge=0, validation_alias="CHAT_CACHE_TTL_SEC")

    openai_api_base: str | None = None
    openai_api_key: str | None = None
    openai_chat_model: str = "gpt-4o-mini"

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
    # MinerU 子进程环境：设为 local 时需配置 models-dir（见 config/mineru.json.example 与 scripts/download_mineru_local_models.py）
    mineru_model_source: str | None = Field(default=None, validation_alias="MINERU_MODEL_SOURCE")
    # 指向 mineru.json 绝对路径；不设则 MinerU 默认读 ~/.mineru.json 或 ~/mineru.json（见 MinerU 的 MINERU_TOOLS_CONFIG_JSON）
    mineru_tools_config_json: str | None = Field(default=None, validation_alias="MINERU_TOOLS_CONFIG_JSON")
    # mineru CLI 轮询 mineru-api 任务状态的间隔（秒）；hybrid 每步约 20s+ 时默认 8 可减少 access log
    mineru_task_poll_interval_sec: float = Field(default=8.0, ge=1.0, le=120.0, validation_alias="MINERU_TASK_POLL_INTERVAL_SEC")

    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    pipeline_log: int = Field(default=0, ge=0, le=2, validation_alias="PIPELINE_LOG")
    log_stages: str = Field(default="", validation_alias="LOG_STAGES")

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


settings = Settings()
