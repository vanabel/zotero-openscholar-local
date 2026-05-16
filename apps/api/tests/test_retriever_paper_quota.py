from app.services.retriever import apply_paper_quota


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
