"""Lookup for the pre-generated Gaudí knowledge graph.

This is a placeholder for a real knowledge-graph store (e.g. a graph DB or a
generated JSON export). It maps an architectural element name, as returned
by a location classifier (see classifiers.py), to a short block of factual
context that gets fed into the SLM prompt.
"""

from typing import Optional

_KNOWLEDGE_GRAPH: dict[str, str] = {
    "chimney": (
        "La Pedrera's rooftop chimneys were designed by Antoni Gaudí between "
        "1906 and 1912. They are covered in broken glass, ceramic and stone "
        "fragments (trencadís) and were nicknamed 'espantabruixes' (witch "
        "scarers) for their helmet-like shapes."
    ),
    "dragon": (
        "The mosaic dragon (also called 'el drac' or the salamander) sits on "
        "the main staircase of Park Güell. Gaudí built it around 1904-1905 "
        "using trencadís, a technique of covering surfaces with broken tile "
        "and ceramic fragments."
    ),
}


def get_context(element: Optional[str]) -> Optional[str]:
    """Return the pre-generated knowledge-graph context for an element, if known."""
    if element is None:
        return None
    return _KNOWLEDGE_GRAPH.get(element)
