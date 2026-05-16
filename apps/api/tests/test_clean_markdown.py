from app.services.clean_markdown import clean_markdown, fix_hyphenation_line_breaks, strip_repeated_header_footer_lines


def test_fix_hyphenation_line_breaks():
    md = "inter-\nnational conference"
    assert fix_hyphenation_line_breaks(md) == "international conference"


def test_strip_repeated_header_footer():
    header = "Journal of Examples Vol. 1"
    body = "\n".join([header, "# Title", "Content line."] * 5)
    out = strip_repeated_header_footer_lines(body, min_repeats=3)
    assert header not in out
    assert "# Title" in out


def test_clean_markdown_trims_references_when_disabled():
    md = "# Main\n\nBody.\n\n## References\n\n[1] Foo"
    kept = clean_markdown(md, keep_references=True)
    assert "References" in kept
    trimmed = clean_markdown(md, keep_references=False)
    assert "References" not in trimmed
    assert "Body" in trimmed
