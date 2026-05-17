from app.services.query_synonyms import expand_query_with_synonyms


def test_expand_query_with_synonyms_replaces_term():
    rules = {"zotero": ["Zotero"]}
    extras = expand_query_with_synonyms("how to use zotero plugin", rules, force=True)
    assert any("Zotero" in e for e in extras)
