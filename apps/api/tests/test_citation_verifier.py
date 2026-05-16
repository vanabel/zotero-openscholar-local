from app.services.citation_verifier import extract_citation_refs, no_evidence_answer, verify_citations


def _ctx(n: int = 3) -> list[dict]:
    return [{"chunk_id": f"c{i}", "paper_id": "p1", "text": f"body {i}"} for i in range(1, n + 1)]


def test_extract_citation_refs():
    assert extract_citation_refs("结论 [1] 与 [2][3]") == [1, 2, 3]


def test_verify_removes_invalid_refs():
    answer, meta = verify_citations("见文献 [1] 与 [9]。", _ctx(2), lang="zh")
    assert "见文献 [1] 与 。" in answer or "[1]" in answer
    assert "[9]" not in answer.split("（注：")[0]
    assert meta["invalid_refs"] == [9]
    assert meta["valid_refs"] == [1]


def test_no_evidence_answer():
    assert "未检索" in no_evidence_answer("zh")
    assert "evidence" in no_evidence_answer("en").lower()
