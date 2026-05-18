import asyncio
from unittest.mock import patch

from app.config import settings
from app.db import get_db, init_db, set_zotero_storage_path
from app.services.parse_batch import list_paper_ids_for_parse, parse_paper


def _seed_paper(tmp_path, monkeypatch, *, with_md: bool = False) -> tuple[str, Path]:
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    init_db()
    storage = tmp_path / "storage"
    key = "Ab12Cd34"
    pdf = storage / key / "paper.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4 minimal")
    set_zotero_storage_path(storage)

    pid = "a" * 32
    mac_path = f"/Users/me/Zotero/storage/{key}/paper.pdf"
    now = "2026-01-01T00:00:00+00:00"
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO papers(
              id, pdf_path, file_name, file_size, mtime, sha256,
              parse_status, index_status, deleted, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (pid, mac_path, "paper.pdf", 1, 1.0, "sha", "pending", "pending", 0, now, now),
        )
    if with_md:
        parsed = settings.parsed_dir / pid
        parsed.mkdir(parents=True)
        (parsed / "document.md").write_text("# T\n\n" + ("body " * 30), encoding="utf-8")
        (parsed / "meta.json").write_text('{"pdf_sha256": "sha"}', encoding="utf-8")
    return pid, pdf


def test_list_parse_missing_only(tmp_path, monkeypatch):
    pid, _ = _seed_paper(tmp_path, monkeypatch, with_md=False)
    assert pid in list_paper_ids_for_parse(missing_only=True)
    parsed = settings.parsed_dir / pid
    parsed.mkdir(parents=True, exist_ok=True)
    (parsed / "document.md").write_text("# T\n\n" + ("body " * 30), encoding="utf-8")
    (parsed / "meta.json").write_text('{"pdf_sha256": "sha"}', encoding="utf-8")
    assert pid not in list_paper_ids_for_parse(missing_only=True)


def test_parse_batch_calls_index_paper(tmp_path, monkeypatch):
    pid, _ = _seed_paper(tmp_path, monkeypatch, with_md=False)

    async def fake_index(paper_id, force=False, parse_only=False, **kwargs):
        assert paper_id == pid
        assert parse_only is True
        return {"ok": True, "paper_id": paper_id, "parse_only": True}

    with patch("app.services.parse_batch.index_paper", side_effect=fake_index):
        res = asyncio.run(parse_paper(pid))
    assert res["ok"] is True
