from pathlib import Path

from app.config import settings
from app.db import get_db, init_db, set_zotero_storage_path
from app.services.hpc_pdf_path import extract_zotero_storage_key, resolve_pdf_path


def test_extract_zotero_storage_key():
    p = "/Users/me/Zotero/storage/Ab12Cd34/paper.pdf"
    assert extract_zotero_storage_key(p) == "Ab12Cd34"


def test_resolve_via_storage_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    storage = tmp_path / "zotero-storage"
    key = "XyZz1234"
    pdf = storage / key / "doc.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4")
    set_zotero_storage_path(storage)

    mac_path = f"/Users/other/Zotero/storage/{key}/doc.pdf"
    resolved = resolve_pdf_path(mac_path)
    assert resolved is not None
    assert resolved.resolve() == pdf.resolve()


def test_resolve_prefix_remap(tmp_path, monkeypatch):
    target = tmp_path / "mirror" / "KEY" / "a.pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x")
    monkeypatch.setenv("HPC_PDF_PATH_PREFIX_OLD", "/Mac/root")
    monkeypatch.setenv("HPC_PDF_PATH_PREFIX_NEW", str(tmp_path / "mirror"))
    stored = "/Mac/root/KEY/a.pdf"
    assert resolve_pdf_path(stored) == target.resolve()
