from app.services.retriever import dedupe_chunks_by_text


def test_dedupe_chunks_by_text():
    ranked = [
        {"chunk_id": "a", "paper_id": "p1", "text": "same paragraph content here for dedupe test"},
        {"chunk_id": "b", "paper_id": "p2", "text": "same paragraph content here for dedupe test"},
        {"chunk_id": "c", "paper_id": "p3", "text": "unique chunk text for retrieval dedupe testing"},
    ]
    out = dedupe_chunks_by_text(ranked)
    assert [x["chunk_id"] for x in out] == ["a", "c"]
