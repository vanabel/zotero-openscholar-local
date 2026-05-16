import json

from app.db import get_db
from app.services.chat_cache import clear_cached_translation, get_cached_answer, put_cached_answer


def test_clear_cached_translation_removes_answer_other():
    q = "test clear translation cache unique"
    lang = "zh"
    put_cached_answer(
        q,
        lang,
        {
            "answer": "主答",
            "citations": [],
            "answer_other": "坏译文",
            "answer_other_lang": "en",
        },
    )
    assert clear_cached_translation(q, lang) is True
    hit = get_cached_answer(q, lang)
    assert hit is not None
    assert hit["answer"] == "主答"
    assert "answer_other" not in hit or not hit.get("answer_other")
    with get_db() as conn:
        row = conn.execute(
            "SELECT payload_json FROM chat_cache WHERE question_norm = ? AND lang = ?",
            ("test clear translation cache unique", lang),
        ).fetchone()
    payload = json.loads(row["payload_json"])
    assert "answer_other" not in payload
    assert "answer_other_lang" not in payload


def test_clear_cached_translation_noop_without_translation():
    q = "test clear translation noop unique"
    put_cached_answer(q, "zh", {"answer": "仅主答", "citations": []})
    assert clear_cached_translation(q, "zh") is False
