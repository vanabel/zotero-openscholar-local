from app.services.chunker import chunk_markdown
from app.services.section_path import (
    dumps_section_path_json,
    format_chunk_source,
    parse_section_path_json,
    section_path_display,
    split_markdown_sections_structured,
)


def test_split_markdown_sections_structured_nested():
    md = "# Intro\n\nA\n\n## Methods\n\nB\n\n### Detail\n\nC"
    parts = split_markdown_sections_structured(md)
    assert parts[0][0] == ["Intro"]
    assert parts[1][0] == ["Intro", "Methods"]
    assert parts[2][0] == ["Intro", "Methods", "Detail"]


def test_section_path_json_roundtrip():
    parts = ["Introduction", "Background"]
    raw = dumps_section_path_json(parts)
    assert parse_section_path_json(raw) == parts
    assert section_path_display(None, raw) == "Introduction › Background"


def test_format_chunk_source_with_pages():
    s = format_chunk_source(
        section_path_json=dumps_section_path_json(["Results"]),
        page_start=3,
        page_end=5,
    )
    assert "Results" in s
    assert "3" in s and "5" in s


def test_chunk_markdown_has_section_path_json():
    md = "# Title\n\nbody text here with enough length for chunk"
    drafts = chunk_markdown(md)
    assert drafts
    assert parse_section_path_json(drafts[0].section_path_json) == ["Title"]
