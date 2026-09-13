"""Lookup for the Gaudí knowledge graph.

Currently backed by the mock in-memory graph in models/mock_knowledge_graph.py,
standing in for a real graph DB or generated export.
"""

from typing import Optional

from models.mock_knowledge_graph import get_context as _get_context


def get_context(element: Optional[str]) -> Optional[str]:
    """Return the pre-generated knowledge-graph context for an element, if known."""
    return _get_context(element)
