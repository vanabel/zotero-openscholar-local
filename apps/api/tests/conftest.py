"""pytest：import 路径 + 每测独立 DATA_DIR，禁止写入开发库 apps/api/data/。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.db import init_db

sys.path.insert(0, str(Path(__file__).resolve().parent))

# 开发默认数据目录（apps/api/data）；测试不得使用此路径
_DEV_DATA_DIR = (Path(__file__).resolve().parents[1] / "data").resolve()


@pytest.fixture(autouse=True)
def isolated_test_data_dir(monkeypatch, tmp_path):
    """
    每个测试使用独立临时 DATA_DIR（含 app.sqlite / parsed/）。
    覆盖未显式 monkeypatch 的用例，避免 DELETE FROM papers 等清空开发库。
    """
    data = (tmp_path / "data").resolve()
    data.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.config.settings.data_dir", data)
    assert data != _DEV_DATA_DIR
    init_db()
    yield data
