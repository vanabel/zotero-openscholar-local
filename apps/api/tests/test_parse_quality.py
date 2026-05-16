from app.services.parse_quality import analyze_markdown


def test_analyze_markdown_scores_structured_doc():
    md = "# Introduction\n\n" + ("This is a sample paragraph about Yang-Mills. " * 40) + "\n\n## Methods\n\n" + ("We prove a lemma. " * 20)
    md += "\n\n$$ E = mc^2 $$\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n## References\n\n[1] Foo et al."
    report = analyze_markdown(md, parser="test")
    assert 0.0 < report["parse_quality_score"] <= 1.0
    assert report["detected_sections"] >= 2
    assert report["references_detected"] is True
    assert report["formula_blocks"] >= 1
