from pathlib import Path

from app.services.parse_outcome import summarize_parse_outcome
from app.services.pdf_parse import inspect_pdf, parse_one


def test_inspect_rejects_html(tmp_path):
    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"<!doctype html><html><body>error</body></html>")
    err, pages = inspect_pdf(fake)
    assert err
    assert "HTML" in err
    assert pages is None


def test_inspect_rejects_missing_file(tmp_path):
    err, pages = inspect_pdf(tmp_path / "nope.pdf")
    assert err
    assert pages is None


def test_parse_one_skips_mineru_for_invalid_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.pdf_parse.settings.mineru_mode", "cloud")

    pdf = tmp_path / "bad.pdf"
    pdf.write_bytes(b"<!doctype html>")
    out = tmp_path / "parsed" / "paper1"
    md, meta = parse_one("paper1", pdf, out)
    assert meta["mode"] == "pdf_invalid"
    assert "HTML" in (meta.get("pdf_error") or "")
    assert "提取失败" in md
    assert (out / "document.md").is_file()


def test_parse_outcome_pdf_invalid_uses_pdf_error():
    status, msg = summarize_parse_outcome(
        "# 提取失败\n\n" + "x" * 100,
        {"mode": "pdf_invalid", "pdf_error": "文件不是 PDF（疑似 HTML/网页）。"},
    )
    assert status == "failed"
    assert "HTML" in (msg or "")
