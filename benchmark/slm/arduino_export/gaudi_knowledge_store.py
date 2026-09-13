"""Shared id-based knowledge lookup for the CulturaViva audio guide.

Kept as a standalone module so the Arduino export bundle is completely self-contained.
"""

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
KB_PATH = BASE_DIR / "knowledge_base.json"
SHEETS_PATH = BASE_DIR / "element_sheets.json"


class GaudiKnowledgeStore:
    def __init__(self, kb_path: Path = KB_PATH, sheets_path: Path = SHEETS_PATH):
        self.kb = self._load_json(kb_path) or {}
        sheets_data = self._load_json(sheets_path) or {}
        self.sheets_by_id = {s["id"]: s for s in sheets_data.get("sheets", [])}

    @staticmethod
    def _load_json(path: Path):
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def context_for_element(self, element_id: str, include_similar: bool = True) -> str:
        sheet = self.sheets_by_id.get(element_id)
        if sheet is None:
            return self.context_for_topic(element_id)

        parts = [self._render_sheet(sheet)]
        parent = self.sheets_by_id.get(sheet.get("parent"))
        if parent is not None:
            parts.append(self._render_sheet(parent))
        if include_similar:
            for note in sheet.get("similarities", []):
                parts.append(f"Related: {note}")

        return "\n---\n".join(parts)

    # Words too generic to distinguish between KB entries — excluded from scoring.
    _STOP_WORDS: frozenset = frozenset({
        "a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for",
        "is", "it", "its", "was", "are", "be", "by", "as", "with", "from",
        "that", "this", "what", "where", "when", "who", "which", "how",
        "did", "do", "does", "has", "have", "had", "been", "not",
        "kind", "built", "located", "tell", "me", "about", "give",
    })

    def context_for_topic(self, query: str) -> str:
        """Return the best-matching KB entry or element sheet for a free-text query.

        Scoring (per candidate):
        - 2 points for each query token matched in the entry's name / aliases  (title match)
        - 1 point for each query token matched in the rendered body text        (body match)
        - Tokens in _STOP_WORDS are excluded from scoring to avoid false ties.
        - Matching uses word-token sets, not substring search, to avoid "on"
          matching inside "Antoni", "it" inside "architect", etc.
        """
        raw_tokens = set(re.findall(r"\w+", query.lower()))
        tokens = raw_tokens - self._STOP_WORDS
        if not tokens:
            tokens = raw_tokens

        best_key, best_score, best_source = None, 0, None

        # --- Search knowledge_base.json entries ---
        for key, entry in self.kb.items():
            title_words = set(re.findall(
                r"\w+",
                " ".join([entry.get("name", ""), *entry.get("aliases", []), key]).lower()
            ))
            body_words = set(re.findall(r"\w+", self._render_kb_entry(entry).lower()))

            title_score = sum(2 for t in tokens if t in title_words)
            body_score  = sum(1 for t in tokens if t in body_words and t not in title_words)
            score = title_score + body_score

            if score > best_score:
                best_key, best_score, best_source = key, score, "kb"

        # --- Search element_sheets.json sheets ---
        for sheet_id, sheet in self.sheets_by_id.items():
            title_words = set(re.findall(
                r"\w+",
                " ".join([sheet.get("name", ""), *sheet.get("aliases", []), sheet_id]).lower()
            ))
            body_words = set(re.findall(r"\w+", self._render_sheet(sheet).lower()))

            title_score = sum(2 for t in tokens if t in title_words)
            body_score  = sum(1 for t in tokens if t in body_words and t not in title_words)
            score = title_score + body_score

            if score > best_score:
                best_key, best_score, best_source = sheet_id, score, "sheet"

        if best_key is None:
            return (
                "No specific context available. Answer only with widely known, "
                "well-established facts about Antoni Gaudi, and say so if unsure."
            )

        if best_source == "sheet":
            return self._render_sheet(self.sheets_by_id[best_key])
        return self._render_kb_entry(self.kb[best_key])

    @staticmethod
    def _render_sheet(sheet: dict) -> str:
        materials = ", ".join(sheet.get("materials", []))
        facts = " ".join(sheet.get("technical_facts", []) + sheet.get("artistic_facts", []))
        return (
            f"{sheet.get('name')} (part of {sheet.get('parent', sheet.get('name'))}). "
            f"Materials: {materials}. {sheet.get('inspiration', '')} {facts}"
        ).strip()

    @staticmethod
    def _render_kb_entry(entry: dict) -> str:
        facts = "\n".join(entry.get("notable_facts", []))
        return (
            f"{entry.get('name')}: {entry.get('style', '')}. "
            f"{entry.get('status', entry.get('timeline', ''))} Facts:\n{facts}"
        ).strip()
