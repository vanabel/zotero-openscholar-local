from pathlib import Path

from pydantic import BaseModel, Field
from fastapi import APIRouter

from app.config import API_ENV_FILE, REPO_ROOT, path_relative_to_repo, settings
from app.db import get_zotero_storage_path, set_zotero_storage_path

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsOut(BaseModel):
    """路径类字段：绝对路径用于程序；带 _rel 的为相对仓库根（便于在设置页阅读）。"""
    repo_root: str
    env_file_used: str
    env_file_exists: bool
    zotero_storage_path: str
    zotero_storage_path_rel: str | None
    zotero_sqlite_path: str | None
    zotero_sqlite_path_rel: str | None
    data_dir: str
    data_dir_rel: str | None
    ollama_base_url: str
    ollama_chat_model: str
    ollama_embed_model: str
    openai_configured: bool
    mineru_mode: str
    mineru_api_base_url: str
    mineru_cloud_configured: bool


class SettingsUpdate(BaseModel):
    zotero_storage_path: str = Field(..., min_length=1, max_length=4096)


def _settings_out() -> SettingsOut:
    zp = get_zotero_storage_path()
    zsql = settings.zotero_sqlite_path
    dd = settings.data_dir.resolve()
    zsql_exp = zsql.expanduser().resolve(strict=False) if zsql else None
    zp_res = zp.expanduser().resolve(strict=False)
    return SettingsOut(
        repo_root=str(REPO_ROOT.resolve(strict=False)),
        env_file_used=str(API_ENV_FILE),
        env_file_exists=API_ENV_FILE.is_file(),
        zotero_storage_path=str(zp_res),
        zotero_storage_path_rel=path_relative_to_repo(zp_res),
        zotero_sqlite_path=str(zsql_exp) if zsql_exp else None,
        zotero_sqlite_path_rel=path_relative_to_repo(zsql_exp) if zsql_exp else None,
        data_dir=str(dd),
        data_dir_rel=path_relative_to_repo(dd),
        ollama_base_url=settings.ollama_base_url,
        ollama_chat_model=settings.ollama_chat_model,
        ollama_embed_model=settings.ollama_embed_model,
        openai_configured=bool(settings.openai_api_key and settings.openai_api_base),
        mineru_mode=(settings.mineru_mode or "cli").strip(),
        mineru_api_base_url=(settings.mineru_api_base_url or "https://mineru.net").strip(),
        mineru_cloud_configured=bool((settings.mineru_api_token or "").strip()),
    )


@router.get("", response_model=SettingsOut)
def get_settings():
    return _settings_out()


@router.put("", response_model=SettingsOut)
def put_settings(body: SettingsUpdate):
    p = Path(body.zotero_storage_path).expanduser()
    set_zotero_storage_path(p)
    return _settings_out()
