"""
Lookup of structured knowledge base entries (knowledge_base.json) based on a query string.

Instead of using the RAG index, this module allows to find the monument_id and context
for a given query (e.g., a label from the vision model) by matching against the
knowledge base entries (name and aliases) using exact and fuzzy matching.
"""
import json
import re
import difflib
from pathlib import Path
from typing import Optional

KB_PATH = Path(__file__).parent / "knowledge_base.json"

_kb_cache: Optional[dict] = None


def load_knowledge_base(path: Path = KB_PATH) -> dict[Optional[str], dict]:
    """Load the knowledge base from a JSON file, caching it in memory."""
    global _kb_cache
    if _kb_cache is None:
        with open(path, "r", encoding="utf-8") as f:
            _kb_cache = json.load(f)
    return _kb_cache


def _normalize(text: str) -> str:
    """Normalize text for matching: lowercase, strip, remove confidence suffix and punctuation."""
    text = text.lower().strip()
    text = re.sub(r"\s*\(.*?\)\s*$", "", text)  # remove "(95% confidence)"
    text = re.sub(r"[^\w\s]", "", text)         # remove punctuation
    return text.strip()


def find_monument_id(query: str, kb: Optional[dict] = None, cutoff: float = 0.6) -> Optional[str]:
    """Search for a monument_id in the knowledge base that matches the query string.
    First tries exact or substring match against name and aliases, then falls back to fuzzy matching.
    Returns the monument_id if a match is found, or None otherwise."""
    kb = kb or load_knowledge_base()
    normalized_query = _normalize(query)

    # exact match or substring match against name and aliases
    for monument_id, entry in kb.items():
        candidates = [entry["name"]] + entry.get("aliases", [])
        for candidate in candidates:
            normalized_candidate = _normalize(candidate)
            if normalized_candidate == normalized_query or normalized_candidate in normalized_query:
                return monument_id

    # fuzzy matching using difflib
    best_match = None
    best_score = 0.0
    for monument_id, entry in kb.items():
        candidates = [entry["name"]] + entry.get("aliases", [])
        for candidate in candidates:
            score = difflib.SequenceMatcher(None, _normalize(candidate), normalized_query).ratio()
            if score > best_score:
                best_score = score
                best_match = monument_id

    return best_match if best_score >= cutoff else None


def format_context(monument_id: str, kb: Optional[dict] = None) -> str:
    """Convert the monument entry into a readable plain text format for the prompt."""
    kb = kb or load_knowledge_base()
    entry = kb.get(monument_id)
    if not entry:
        return ""

    lines = [f"Name: {entry['name']}"]
    for key in ("location", "architect", "style", "construction_start",
                "construction_end", "consecrated", "unesco_status", "status"):
        if key in entry:
            label = key.replace("_", " ").capitalize()
            lines.append(f"{label}: {entry[key]}")
    if entry.get("notable_facts"):
        lines.append("Notable facts:")
        lines.extend(f"- {fact}" for fact in entry["notable_facts"])

    return "\n".join(lines)


def get_context_from_labels(image_labels: list[str], kb: Optional[dict] = None) -> Optional[dict]:
    """Typical entry point: receives the labels from the vision model
    (ordered by confidence) and returns {monument_id, context} of the first
    match found, or None if no label matches."""
    kb = kb or load_knowledge_base()
    for label in image_labels:
        monument_id = find_monument_id(label, kb)
        if monument_id:
            return {"monument_id": monument_id, "context": format_context(monument_id, kb)}
    return None
