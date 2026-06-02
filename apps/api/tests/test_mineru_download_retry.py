"""MinerU 仅重试 zip 下载（mineru_pending.json）。"""

import json
import io
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config import settings
from app.services.mineru_cloud import (
    MinerUCloudError,
    clear_mineru_download_pending,
    finish_mineru_download_from_pending,
    save_mineru_download_pending,
)
from app.services.mineru_download_retry import (
    list_mineru_download_pending_paper_ids,
    paper_has_mineru_download_pending,
    retry_mineru_cloud_download,
)


def _mini_zip_md(text: str = "# ok\n\nbody") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("full.md", text)
    return buf.getvalue()


def test_pending_save_and_list(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    out = settings.parsed_dir / "paper-a"
    save_mineru_download_pending(
        out,
        batch_id="batch-1",
        zip_url="https://cdn.example/a.zip",
        file_name="a.pdf",
        paper_id="paper-a",
    )
    assert paper_has_mineru_download_pending("paper-a")
    assert list_mineru_download_pending_paper_ids() == ["paper-a"]


def test_finish_download_clears_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    out = settings.parsed_dir / "p1"
    out.mkdir(parents=True)
    save_mineru_download_pending(
        out,
        batch_id="b1",
        zip_url="https://cdn.example/z.zip",
        file_name="doc.pdf",
        paper_id="p1",
    )
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp.content = _mini_zip_md()
    fake_resp.raise_for_status = MagicMock()
    fake_client.get.return_value = fake_resp

    with patch("app.services.mineru_cloud.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value = fake_client
        md = finish_mineru_download_from_pending(out)
    assert "ok" in md
    assert not (out / "mineru_pending.json").is_file()
    assert (out / "document.md").is_file()


def test_retry_paper_writes_document(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    paper_id = "pid-99"
    out = settings.parsed_dir / paper_id
    out.mkdir(parents=True)
    save_mineru_download_pending(
        out,
        batch_id="bx",
        zip_url="https://cdn-mineru.openxlab.org.cn/z.zip",
        file_name="x.pdf",
        paper_id=paper_id,
    )
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp.content = _mini_zip_md("# recovered\n\ntext " * 20)
    fake_resp.raise_for_status = MagicMock()
    fake_client.get.return_value = fake_resp

    with patch("app.services.mineru_cloud.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value = fake_client
        md, meta = retry_mineru_cloud_download(paper_id)
    assert "recovered" in md
    assert meta.get("mode") == "mineru_cloud" or meta.get("mineru_download_retried")


def test_retry_without_pending_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    (settings.parsed_dir / "empty").mkdir(parents=True)
    with pytest.raises(MinerUCloudError, match="无待重试"):
        retry_mineru_cloud_download("empty")
