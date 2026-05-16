"""MinerU 云端分段合并时的 Markdown 资源路径前缀。"""

from app.services.mineru_cloud import (
    _format_extract_progress_short,
    _normalize_completed_prefix,
    _parse_extract_progress,
    _prefix_relative_asset_urls,
    _should_log_poll_progress,
    _should_log_poll_stall,
)


def test_normalize_completed_prefix():
    assert _normalize_completed_prefix({0, 1, 3}, 5) == {0, 1}
    assert _normalize_completed_prefix({0, 1, 2}, 5) == {0, 1, 2}
    assert _normalize_completed_prefix(set(), 5) == set()


def test_prefix_images_and_skip_http():
    md = '![a](images/x.png) and ![b](https://x/y.png) and ![](figures/z.jpg)'
    out = _prefix_relative_asset_urls(md, "_mineru_cloud_chunks/000")
    assert "](_mineru_cloud_chunks/000/images/x.png)" in out
    assert "https://x/y.png" in out
    assert "](_mineru_cloud_chunks/000/figures/z.jpg)" in out


def test_prefix_idempotent():
    md = "![](_mineru_cloud_chunks/000/images/x.png)"
    out = _prefix_relative_asset_urls(md, "_mineru_cloud_chunks/000")
    assert out == md


def test_parse_extract_progress():
    assert _parse_extract_progress(None) == (None, None)
    assert _parse_extract_progress({"extracted_pages": 10, "total_pages": 200}) == (10, 200)
    assert _format_extract_progress_short(180, 200) == "180/200 页 (90%)"


def test_should_log_poll_progress_throttle():
    t0 = 1000.0
    assert _should_log_poll_progress(
        extracted=5, total=200, last_extracted=None, last_log_at=None, now=t0
    )
    assert not _should_log_poll_progress(
        extracted=8, total=200, last_extracted=5, last_log_at=t0, now=t0 + 5
    )
    assert _should_log_poll_progress(
        extracted=20, total=200, last_extracted=5, last_log_at=t0, now=t0 + 5
    )
    assert _should_log_poll_progress(
        extracted=52, total=200, last_extracted=48, last_log_at=t0, now=t0 + 5
    )
    assert _should_log_poll_progress(
        extracted=52, total=200, last_extracted=51, last_log_at=t0, now=t0 + 35
    )


def test_should_log_poll_stall():
    assert not _should_log_poll_stall(
        extracted=164, last_extracted=164, last_log_at=100.0, now=140.0
    )
    assert _should_log_poll_stall(
        extracted=164, last_extracted=164, last_log_at=100.0, now=161.0
    )
