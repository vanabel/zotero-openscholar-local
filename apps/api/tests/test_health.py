from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_stats_empty_db():
    r = client.get("/stats")
    assert r.status_code == 200
    data = r.json()
    assert "papers" in data
    assert "chunks" in data
