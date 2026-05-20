"""超算批处理：将 Mac 库内 pdf_path 解析为当前节点可读路径（rsync Zotero storage 后）。"""

from __future__ import annotations

import os
import re
from pathlib import Path

from app.db import get_zotero_storage_path

# Zotero 附件目录：.../storage/<8-char key>/file.pdf
_STORAGE_KEY_RE = re.compile(r"/storage/([A-Za-z0-9]{8})/", re.IGNORECASE)


def extract_zotero_storage_key(pdf_path: str) -> str | None:
    normalized = pdf_path.replace("\\", "/")
    m = _STORAGE_KEY_RE.search(normalized)
    return m.group(1) if m else None


def resolve_pdf_path(stored: str | Path) -> Path | None:
    """
    按顺序尝试：
    1. 库内路径本身可读；
    2. HPC_PDF_PATH_PREFIX_OLD → HPC_PDF_PATH_PREFIX_NEW 前缀替换；
    3. 从路径提取 Zotero storage key，在 ZOTERO_STORAGE_PATH 下拼接。
    """
    p = Path(stored).expanduser()
    if p.is_file():
        return p.resolve()

    old = os.environ.get("HPC_PDF_PATH_PREFIX_OLD", "").strip()
    new = os.environ.get("HPC_PDF_PATH_PREFIX_NEW", "").strip()
    if old and new:
        s = str(p)
        if s.startswith(old):
            cand = Path(new + s[len(old) :])
            if cand.is_file():
                return cand.resolve()

    key = extract_zotero_storage_key(str(p))
    if key:
        # HPC jobs often use a Mac-synced app.sqlite whose app_settings still
        # points to /Users/...; the job env must win on the cluster.
        env_root = os.environ.get("ZOTERO_STORAGE_PATH", "").strip()
        root = Path(env_root).expanduser() if env_root else get_zotero_storage_path()
        cand = root / key / p.name
        if cand.is_file():
            return cand.resolve()

    return None
