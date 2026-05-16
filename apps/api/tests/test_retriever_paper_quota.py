from app.services.retriever import _finalize_retrieval, apply_paper_quota


def _c(chunk_id: str, paper_id: str) -> dict:
    return {"chunk_id": chunk_id, "paper_id": paper_id, "text": chunk_id}


def test_apply_paper_quota_limits_per_paper():
    ranked = [
        _c("a1", "p1"),
        _c("a2", "p1"),
        _c("a3", "p1"),
        _c("a4", "p1"),
        _c("b1", "p2"),
        _c("b2", "p2"),
    ]
    out = apply_paper_quota(ranked, max_per_paper=2, max_distinct_papers=None, limit=10)
    assert [x["chunk_id"] for x in out] == ["a1", "a2", "b1", "b2"]
    assert sum(1 for x in out if x["paper_id"] == "p1") == 2


def test_apply_paper_quota_limits_distinct_papers():
    ranked = [_c(f"c{i}", f"p{i}") for i in range(10)]
    out = apply_paper_quota(ranked, max_per_paper=1, max_distinct_papers=3, limit=10)
    assert len(out) == 3
    assert len({x["paper_id"] for x in out}) == 3


def test_apply_paper_quota_preserves_rank_order():
    ranked = [_c("x1", "p1"), _c("y1", "p2"), _c("x2", "p1")]
    out = apply_paper_quota(ranked, max_per_paper=1, max_distinct_papers=None, limit=5)
    assert [x["chunk_id"] for x in out] == ["x1", "y1"]


def test_finalize_retrieval_backfills_from_pool_when_top_slice_dominated(monkeypatch):
    """精排前 K 条若集中在少数文献，应从更大候选池回填至 top_k_final。"""
    from app.config import settings

    monkeypatch.setattr(settings, "retrieve_max_chunks_per_paper", 3)
    monkeypatch.setattr(settings, "retrieve_max_papers", 0)
    ranked = [_c(f"a{i}", "p1") for i in range(8)] + [_c(f"b{i}", "p2") for i in range(8)]
    for i in range(10):
        ranked.append(_c(f"c{i}", f"p{i + 3}"))
    out = _finalize_retrieval(ranked, 16)
    assert len(out) == 16
    assert sum(1 for x in out if x["paper_id"] == "p1") == 3
    assert sum(1 for x in out if x["paper_id"] == "p2") == 3
