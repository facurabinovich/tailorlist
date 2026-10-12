"""core/glossary: the Glossary page's terms and search (moved from pages/7_Glossary.py, T24)."""
from core.glossary import GLOSSARY_TERMS, group_by_section, search_terms


def test_every_term_has_the_four_fields():
    assert GLOSSARY_TERMS
    for t in GLOSSARY_TERMS:
        assert set(t) == {"term", "section", "definition", "used_in"}
        assert isinstance(t["used_in"], list)


def test_empty_query_returns_every_term_in_order():
    assert search_terms("") == GLOSSARY_TERMS
    assert search_terms(None) == GLOSSARY_TERMS


def test_query_matches_name_definition_or_page_case_insensitively():
    terms = [
        {"term": "Valence", "section": "A", "definition": "Musical positivity.", "used_in": ["Audio DNA"]},
        {"term": "Energy", "section": "A", "definition": "Intensity.", "used_in": ["My Clusters"]},
        {"term": "Silhouette", "section": "B", "definition": "Cluster separation.", "used_in": ["Overview"]},
    ]
    assert [t["term"] for t in search_terms("VALENCE", terms)] == ["Valence"]
    assert [t["term"] for t in search_terms("intens", terms)] == ["Energy"]
    assert [t["term"] for t in search_terms("clusters", terms)] == ["Energy"]   # used_in page name
    assert [t["term"] for t in search_terms("cluster", terms)] == ["Energy", "Silhouette"]
    assert search_terms("zzz", terms) == []


def test_real_glossary_search_finds_valence():
    assert any(t["term"] == "Valence" for t in search_terms("valence"))


def test_group_by_section_keeps_first_appearance_order():
    terms = [
        {"term": "x", "section": "B", "definition": "", "used_in": []},
        {"term": "y", "section": "A", "definition": "", "used_in": []},
        {"term": "z", "section": "B", "definition": "", "used_in": []},
    ]
    groups = group_by_section(terms)
    assert list(groups) == ["B", "A"]
    assert [t["term"] for t in groups["B"]] == ["x", "z"]
    assert group_by_section([]) == {}
