from app.services.chunk_quality import (
    classify_chunk_type,
    content_hash,
    dedupe_chunk_drafts,
    score_chunk,
)
from app.services.chunker import ChunkDraft


def test_classify_references_and_theorem():
    assert classify_chunk_type("References", "Foo bar") == "references"
    assert classify_chunk_type("3. Main Results", "Theorem 1.1 (Energy identity).") == "theorem"


def test_dedupe_chunk_drafts():
    d1 = ChunkDraft("t", "path", 0, "same body text " * 5, None, None)
    d2 = ChunkDraft("t", "path2", 1, "same body text " * 5, None, None)
    out = dedupe_chunk_drafts([d1, d2])
    assert len(out) == 1
    assert content_hash(d1.text) == content_hash(d2.text)


def test_score_chunk():
    assert score_chunk("short", "unknown") < 0.5
    assert score_chunk("This is a complete sentence with enough content. " * 3, "introduction") > 0.5
