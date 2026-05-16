from app.services import lance_store


def test_lancedb_enabled_false_when_disabled(monkeypatch):
    monkeypatch.setattr(lance_store.settings, "lancedb_enabled", False)
    assert lance_store.lancedb_enabled() is False


def test_search_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(lance_store.settings, "lancedb_enabled", False)
    assert lance_store.search_scholar([0.1, 0.2], limit=5) is None
