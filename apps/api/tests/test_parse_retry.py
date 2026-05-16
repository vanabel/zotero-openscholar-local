import pytest

from app.services import parse_retry


def test_retry_model_for_cloud_uses_pipeline():
    assert parse_retry._retry_model_for_mode("mineru_cloud") == "pipeline"


def test_retry_model_for_pypdf_uses_primary_vlm():
    assert parse_retry._retry_model_for_mode("pypdf") == "vlm"


def test_maybe_retry_skips_when_score_ok(monkeypatch):
    import asyncio
    from pathlib import Path

    monkeypatch.setattr(parse_retry.settings, "parse_quality_retry_enabled", True)
    monkeypatch.setattr(parse_retry.settings, "parse_quality_retry_threshold", 0.65)

    async def _run():
        return await parse_retry.maybe_retry_low_quality_parse(
            "p1",
            Path("/tmp/x.pdf"),
            Path("/tmp/out"),
            "# ok",
            {"mode": "mineru"},
            {"parse_quality_score": 0.9},
            force=False,
        )

    md, meta, report = asyncio.run(_run())
    assert md == "# ok"
    assert report["parse_quality_score"] == 0.9
