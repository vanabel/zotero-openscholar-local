"""MinerU 云端 HTTP 瞬态错误重试。"""

import httpx
import pytest

from app.services.mineru_cloud import (
    MinerUCloudError,
    _cloud_request_with_retry,
    _http_status_retryable,
)


def test_http_status_retryable():
    assert _http_status_retryable(429)
    assert _http_status_retryable(503)
    assert not _http_status_retryable(404)
    assert not _http_status_retryable(401)


def test_cloud_request_retries_connect_error(monkeypatch):
    calls: list[int] = []

    def fn() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ConnectError(
                "[Errno 8] nodename nor servname provided, or not known",
                request=httpx.Request("GET", "https://mineru.net/"),
            )
        return "ok"

    monkeypatch.setattr("app.services.mineru_cloud._backoff_before_retry", lambda _a: None)
    assert _cloud_request_with_retry("申请上传", fn, retries=4) == "ok"
    assert len(calls) == 3


def test_cloud_request_no_retry_on_business_error():
    def fn() -> str:
        raise MinerUCloudError("未配置 token")

    with pytest.raises(MinerUCloudError, match="未配置 token"):
        _cloud_request_with_retry("申请上传", fn, retries=4)


def test_cloud_request_retries_503(monkeypatch):
    calls: list[int] = []

    def fn() -> int:
        calls.append(1)
        if len(calls) < 2:
            req = httpx.Request("GET", "https://mineru.net/api/v4/x")
            resp = httpx.Response(503, request=req)
            raise httpx.HTTPStatusError("503", request=req, response=resp)
        return 42

    monkeypatch.setattr("app.services.mineru_cloud._backoff_before_retry", lambda _a: None)
    assert _cloud_request_with_retry("解析结果轮询", fn) == 42
    assert len(calls) == 2


def test_cloud_request_exhausted_raises_mineru_cloud_error(monkeypatch):
    def fn() -> str:
        raise httpx.ConnectError("dns", request=httpx.Request("PUT", "https://oss.example/upload"))

    monkeypatch.setattr("app.services.mineru_cloud._backoff_before_retry", lambda _a: None)
    with pytest.raises(MinerUCloudError, match="已重试 4 次"):
        _cloud_request_with_retry("上传 PDF", fn, retries=4, hint="（https://oss.example）")
