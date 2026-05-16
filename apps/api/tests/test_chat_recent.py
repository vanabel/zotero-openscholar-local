from datetime import datetime, timezone

from app.config import settings
from app.db import get_db, init_db
from app.services.chat_cache import cache_key, list_recent_questions, put_cached_answer


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_list_recent_questions_random_subset(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "chat_cache_enabled", True)
    init_db()
    now = _utc_now()
    with get_db() as conn:
        conn.execute("DELETE FROM chat_cache")
    for i in range(5):
        put_cached_answer(
            f"问题 {i} 关于测试",
            "zh",
            {"answer": f"a{i}", "citations": []},
        )
    items = list_recent_questions("zh", limit=3, pool=10)
    assert len(items) == 3
    assert all(it["has_cache"] for it in items)
    assert all(it["question"].startswith("问题") for it in items)
