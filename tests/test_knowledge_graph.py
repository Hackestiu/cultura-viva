from knowledge import knowledge_graph
from models import mock_knowledge_graph


def test_get_context_returns_none_for_unknown_element():
    assert knowledge_graph.get_context(None) is None
    assert knowledge_graph.get_context("unknown-element") is None


def test_get_context_renders_facts_for_known_element():
    context = knowledge_graph.get_context("chimney")

    assert context is not None
    assert "La Pedrera" in context
    assert "Antoni Gaudí" in context


def test_get_facts_returns_relation_value_triples():
    facts = mock_knowledge_graph.get_facts("dragon")

    assert ("located at", "Park Güell") in facts


def test_get_facts_returns_empty_list_for_unknown_element():
    assert mock_knowledge_graph.get_facts("unknown-element") == []
