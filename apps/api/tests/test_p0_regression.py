"""P0 最小回归集：分块、索引（mock 嵌入）、FTS，不依赖 Ollama / MinerU。"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.config import settings
from app.db import get_db, init_db
from app.services.llm import EmbeddingClient
from app.services.retriever import fts_retrieve

from p0_helpers import (
    FIXTURES_ROOT,
    chunk_drafts_for,
    fixture_paper_id,
    index_fixture,
    load_manifest,
)


@pytest.fixture
def p0_env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data)
    init_db()

    async def _fake_embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.0, -0.1] for _ in texts]

    monkeypatch.setattr(EmbeddingClient, "embed", _fake_embed)
    monkeypatch.setattr(
        "app.services.openscholar_retrieval.openscholar_retriever_enabled",
        lambda: False,
    )
    return data


def test_p0_manifest_matches_directories():
    manifest = load_manifest()
    ids = {m["id"] for m in manifest}
    dirs = {p.name for p in FIXTURES_ROOT.iterdir() if p.is_dir() and (p / "document.md").is_file()}
    assert ids == dirs
    assert len(manifest) == 8


@pytest.mark.parametrize("meta", load_manifest(), ids=lambda m: m["id"])
def test_p0_chunk_structure(meta):
    drafts = chunk_drafts_for(meta["id"])
    assert len(drafts) >= meta.get("min_chunks", 1)
    paths = [d.section_path for d in drafts]
    for needle in meta.get("section_paths_contain", []):
        assert any(needle in p for p in paths), f"section_paths 应含 {needle!r}，实际 {paths}"
    joined = "\n".join(d.text for d in drafts)
    for needle in meta.get("text_must_include", []):
        assert needle in joined, f"分块正文应含 {needle!r}"


@pytest.mark.parametrize("meta", load_manifest(), ids=lambda m: m["id"])
def test_p0_index_and_fts(meta, p0_env):
    res = asyncio.run(index_fixture(meta["id"], p0_env))
    assert res["ok"] is True
    assert res["chunks"] >= meta.get("min_chunks", 1)

    paper_id = fixture_paper_id(meta["id"])
    with get_db() as conn:
        n = conn.execute("SELECT COUNT(*) AS c FROM chunks WHERE paper_id = ?", (paper_id,)).fetchone()["c"]
        assert n == res["chunks"]
        for case in meta.get("fts", []):
            hits = fts_retrieve(conn, case["query"], limit=10)
            paper_hits = [h for h in hits if h["paper_id"] == paper_id]
            assert len(paper_hits) >= case.get("min_hits", 1), case
            if "body_contains" in case:
                blob = " ".join(h["text"] for h in paper_hits)
                assert case["body_contains"] in blob, case
