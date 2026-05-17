from app.services.citation_verifier import normalize_evidence_locks, verify_citations


def _ctx():
    return [
        {"chunk_id": "a" * 32, "paper_id": "p1", "text": "evidence one about neural networks"},
        {"chunk_id": "b" * 32, "paper_id": "p1", "text": "evidence two about transformers"},
    ]


def test_normalize_chunk_refs_to_numeric():
    cid = "a" * 32
    answer, invalid = normalize_evidence_locks(f"结论 [CHUNK:{cid}]。", _ctx())
    assert invalid == []
    assert "[1]" in answer
    assert f"[CHUNK:{cid}]" not in answer


def test_verify_citations_accepts_chunk_lock():
    cid = "a" * 32
    answer, meta = verify_citations(
        f"神经网络训练需要大量数据与算力支撑 [CHUNK:{cid}]。",
        _ctx(),
        lang="zh",
    )
    assert "[1]" in answer
    assert meta["valid_refs"] == [1]
