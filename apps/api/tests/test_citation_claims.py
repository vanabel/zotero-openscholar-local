from app.services.citation_verifier import split_claims, verify_claims, verify_citations


def _ctx():
    return [
        {"chunk_id": "c1", "paper_id": "p1", "text": "Yang-Mills energy identity and no-neck property for harmonic maps."},
        {"chunk_id": "c2", "paper_id": "p2", "text": "Unrelated topic about fluid dynamics only."},
    ]


def test_split_claims():
    claims = split_claims("结论一。[1] 说明能量恒等式。另一句无引用。")
    assert len(claims) >= 1


def test_verify_claims_keyword_overlap():
    answer = "文献证明了 Yang-Mills 能量恒等式。[1]"
    records, meta = verify_claims(answer, _ctx(), lang="zh")
    assert meta["claims_total"] >= 1
    assert any(r.get("status") == "verified" for r in records)


def test_verify_citations_persist_meta():
    answer, meta = verify_citations(
        "根据文献，Yang-Mills 能量恒等式成立。[1]",
        _ctx(),
        lang="zh",
        persist=False,
    )
    assert meta["valid_refs"] == [1]
    assert "citation_status" in meta
    assert meta["claims"]
