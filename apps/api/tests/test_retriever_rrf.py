from app.services.retriever import rrf_merge_ranked_lists


def test_rrf_merge_prefers_consensus():
    a = ["c1", "c2", "c3"]
    b = ["c2", "c1", "c4"]
    merged = rrf_merge_ranked_lists([a, b])
    assert merged[0] in ("c1", "c2")
    assert "c4" in merged
