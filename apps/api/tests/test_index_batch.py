"""批量索引 API：请求体验证与大批量 paper_ids。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_index_batch_rejects_empty_ids():
    r = client.post("/papers/index-batch", json={"paper_ids": []})
    assert r.status_code == 422
    body = r.json()
    assert body.get("error", {}).get("code") == "validation_error"


def test_index_batch_accepts_more_than_legacy_100_cap():
    """历史上 max_length=100 会导致全选 1800+ 篇时 validation_error。"""
    ids = [f"nonexistent-{i}" for i in range(150)]
    r = client.post("/papers/index-batch", json={"paper_ids": ids})
    assert r.status_code == 202
    data = r.json()
    assert data.get("queued", 0) == 0
    assert data.get("failed", 0) == 150
