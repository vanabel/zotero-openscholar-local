from app.services.parse_outcome import summarize_parse_outcome


def test_parse_failed_when_too_short():
    status, msg = summarize_parse_outcome("short", {"mode": "mineru"})
    assert status == "failed"
    assert msg


def test_parse_hint_on_pypdf_fallback():
    md = "x" * 200
    status, msg = summarize_parse_outcome(md, {"mode": "pypdf_fallback_after_mineru_error"})
    assert status is None
    assert msg and "解析提示" in msg
