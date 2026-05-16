"""MinerU 云端分段合并时的 Markdown 资源路径前缀。"""

from app.services.mineru_cloud import _normalize_completed_prefix, _prefix_relative_asset_urls


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
