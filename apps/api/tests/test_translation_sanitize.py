from app.services.translation import (
    _answer_translate_prompt,
    _collapse_repeated_paragraphs,
    _sanitize_translation_output,
    _stream_hit_repetition,
)


def test_answer_translate_prompt_no_nested_english_instruction():
    p = _answer_translate_prompt("中文正文 [1]", "zh")
    assert "English" not in p
    assert "将以下文本翻译为中文" in p
    assert "中文正文" in p


def test_collapse_repeated_paragraphs():
    raw = "A\n\nA\n\nA\n\nB"
    out = _collapse_repeated_paragraphs(raw)
    assert out == "A\n\nB"


def test_sanitize_strips_instruction_echo():
    raw = "将以下文本翻译为中文，注意只需要输出翻译后的结果\n\n这是译文。"
    assert _sanitize_translation_output(raw) == "这是译文。"


def test_stream_hit_repetition():
    block = "alpha-beta-gamma-" * 50
    long = block * 6
    assert len(long) > 500
    assert _stream_hit_repetition(long) is True
