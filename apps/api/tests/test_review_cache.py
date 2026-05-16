from app.db import init_db
from app.services.review_cache import get_cached_review, put_cached_review, review_cache_key


def test_review_cache_key_stable():
    k1 = review_cache_key("  topic  ", " focus ", "zh")
    k2 = review_cache_key("topic", "focus", "zh")
    assert k1 == k2


def test_review_cache_key_differs_by_focus():
    assert review_cache_key("topic", "a", "zh") != review_cache_key("topic", "b", "zh")


def test_put_and_get_cached_review():
    init_db()
    topic = "test review cache unique topic"
    focus = "optional focus"
    put_cached_review(
        topic,
        focus,
        "zh",
        {"review": "综述正文", "citations": [], "contexts_used": 3},
    )
    hit = get_cached_review(topic, focus, "zh")
    assert hit is not None
    assert hit["review"] == "综述正文"
    assert hit.get("cached") is True
