from app.services.retriever import _atomic_search_tokens


def test_atomic_tokens_splits_hyphenated_english():
    q = "summaries the results of multi-point maximum principle"
    t = _atomic_search_tokens(q)
    assert "multi" in t
    assert "point" in t
    assert "maximum" in t
    assert "principle" in t
    assert "the" not in t


def test_atomic_tokens_skips_fts_reserved():
    t = _atomic_search_tokens("maximum and minimum bounds")
    assert "and" not in t
    assert "maximum" in t
    assert "minimum" in t


def test_atomic_tokens_includes_cjk():
    t = _atomic_search_tokens("请总结 能量恒等式 相关结论")
    assert any("能量" in x or "恒等" in x or "结论" in x for x in t)
