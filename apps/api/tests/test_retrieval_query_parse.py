from app.services.translation import (
    _is_mostly_cjk,
    _parse_query_json,
    _parse_query_json_regex,
)


def test_parse_query_json_standard():
    raw = '{"zh":"极大值原理","en":"maximum principle"}'
    zh, en = _parse_query_json(raw)
    assert zh == "极大值原理"
    assert en == "maximum principle"


def test_parse_query_json_markdown_fence():
    raw = '```json\n{"zh":"a","en":"b"}\n```'
    zh, en = _parse_query_json(raw)
    assert zh == "a"
    assert en == "b"


def test_parse_query_json_alternate_keys():
    raw = '{"chinese":"极大值","english":"maximum"}'
    zh, en = _parse_query_json(raw)
    assert zh == "极大值"
    assert en == "maximum"


def test_parse_query_json_regex_fallback():
    raw = '说明：{"zh":"foo","en":"bar"} 结束'
    zh, en = _parse_query_json(raw)
    assert zh == "foo"
    assert en == "bar"


def test_parse_query_json_regex_loose():
    zh, en = _parse_query_json_regex('zh: "极大值原理", en: "maximum principle"')
    assert zh == "极大值原理"
    assert en == "maximum principle"


def test_parse_query_json_empty():
    assert _parse_query_json("not json at all") == (None, None)


def test_is_mostly_cjk():
    assert _is_mostly_cjk("能量恒等式相关") is True
    assert _is_mostly_cjk("maximum principle") is False
