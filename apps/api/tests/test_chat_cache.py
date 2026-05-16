from app.services.chat_cache import _normalize_question, cache_key


def test_cache_key_stable_for_same_question():
    k1 = cache_key("  hello   world  ", "zh")
    k2 = cache_key("hello world", "zh")
    assert k1 == k2


def test_cache_key_differs_by_lang():
    assert cache_key("hello", "zh") != cache_key("hello", "en")
