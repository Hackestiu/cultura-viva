"""The knowledge base: one lookup, one renderer, shared by everything.

This module is the single definition of how a Gaudí knowledge sheet becomes text.
It is imported by the device (through `core.model_module.ModelRegistry`), by the
SLM benchmark and the personality study (through
`benchmark/slm/core/device_prompt.py`), and it is copied verbatim into the Arduino
export bundle by `benchmark/slm/scripts/prepare.py`.

It exists because there used to be four copies. They drifted in both directions:
the export bundle's copy grew a better keyword scorer that the generator never
received, while the generator grew a `purpose` field and a richer
`knowledge_base.json` renderer that the export copy never received. Neither was a
superset, and `prepare.py --export-arduino` silently overwrote the former with the
latter. Meanwhile the benchmark rendered a prose blob the board has never shipped,
so the personality study scored a prompt that did not exist -- even though the
*prompt builders* next door were carefully imported rather than copied.

Two rules keep it that way:

**Top level, not under `core/`.** `benchmark/slm/` has its own top-level `core`
package, and it is already in `sys.modules` by the time `device_prompt.py`
path-loads the device's modules. A `from core.knowledge_store import ...` inside
`core/model_module.py` would resolve to the *benchmark's* `core` and fail. Sitting
beside `config.py` means one flat `import knowledge_store` works in the device
tree, under the benchmark's path-load, and in the flat export bundle alike.

**No `config` import.** `config.py` mutates `sys.path`, creates eleven
directories, configures logging and probes for a camera, microphone and speaker on
import. Taking the two JSON paths as constructor arguments keeps this module
importable off-board, in the bundle, and from a test, with nothing but the stdlib.

## Three projections, only one of them frozen

A sheet is rendered three different ways, and conflating them is what caused the
drift. Only the first is load-bearing:

| Projection | Consumer | Frozen? |
| --- | --- | --- |
| prompt text (`render_sheet`, labeled and capped) | the SLM | **Yes** |
| search text (`_search_text`, flat and uncapped) | `search()` scoring | No |
| chunk text (the benchmark's `_build_chunks`) | the embedder | No |

The prompt text is frozen because it *is* the KV prefix cache key:
`ModelRegistry._prefix_state_path` hashes the rendered facts block, so changing a
separator, a field order or one of the `[:2]` caps silently orphans every
`data/prefix_cache/prefix_*.pkl` on every deployed board. `tests/test_knowledge_store.py`
asserts it against a golden file captured before this module existed.

Search text is deliberately *not* the prompt text: scoring against the capped
rendering would drop every fact beyond the caps out of the searchable body, so a
query matching a fifth technical fact would stop finding its sheet.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent

# The device layout keeps the knowledge files under models/knowledge/; the Arduino
# export bundle copies them in flat, beside this module. Try the former, fall back
# to the latter, so one file serves both without being told which it is in.
_SHEETS_NAME = "element_sheets.json"
_KB_NAME = "knowledge_base.json"


def _default_path(filename: str) -> Path:
    nested = APP_DIR / "models" / "knowledge" / filename
    return nested if nested.exists() else APP_DIR / filename


# Vision's label for "this photo is not a monument element". Duplicated from
# config.VISION_UNKNOWN_LABEL rather than imported, because importing config here
# would drag in the hardware probe.
#
# The guard belongs here rather than only in ModelRegistry: display_name("unknown")
# must return None so build_facts_block emits the "photo not recognised" branch
# instead of a "[Detected element in photo: unknown]" line. Leaving the guard to
# the caller meant the export bundle, which calls this store directly, got the
# latter -- caught by tests/golden/kg_context.json.
UNKNOWN_ELEMENT = "unknown"


def element_display_name(element: str) -> str:
    """Fallback rendering of an element identifier for a reader.

    Identifiers are Catalan/Spanish snake_case ("sala_hipostila", "facana_passio")
    because they are also the vision model's class labels. Putting one in the prompt
    raw is what produced answers like "You are seeing laterals_sagrada_familia" and,
    worse, "Gaudi built the Sala Hipostila to house a collection of columns" -- the
    model reads the identifier as a proper name it half-recognises and invents around
    it. KnowledgeStore.display_name resolves the real English name from the knowledge
    sheet; this is only the fallback for an element that has no sheet.
    """
    return element.replace("_", " ").strip()


class KnowledgeStore:
    """Id-based lookup and rendering over element_sheets.json and knowledge_base.json.

    `logger` is optional and duck-typed: anything with loguru-style brace-formatting
    `.warning`/`.success`/`.exception` will do. The device passes its logger so the
    existing log lines survive; the benchmark and the export bundle pass nothing and
    stay silent, which is what keeps this module free of a loguru dependency.
    """

    def __init__(self, sheets_path=None, kb_path=None, logger=None):
        self.sheets_path = Path(sheets_path) if sheets_path else _default_path(_SHEETS_NAME)
        self.kb_path = Path(kb_path) if kb_path else _default_path(_KB_NAME)
        self._log = logger
        self._sheets_by_id: dict | None = None
        self._alias_index: dict | None = None
        self._kb: dict | None = None

    # ------------------------------------------------------------------ loading

    def _warn(self, msg: str, *args) -> None:
        if self._log is not None:
            self._log.warning(msg, *args)

    def load_sheets(self) -> None:
        """Loads element_sheets.json into an index by element id and an alias index
        (alias, lowercased, mapped to id); a no-op once already loaded, and leaves both
        indices empty if the file is missing."""
        if self._sheets_by_id is not None:
            return

        self._sheets_by_id = {}
        self._alias_index = {}  # alias.lower() -> id

        if not self.sheets_path.exists():
            self._warn(
                "element_sheets.json not found at {}. Returning empty KG context.",
                self.sheets_path,
            )
            return

        try:
            with open(self.sheets_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            sheets = data.get("sheets", [])
            for sheet in sheets:
                sid = sheet.get("id", "")
                if sid:
                    self._sheets_by_id[sid] = sheet
                    for alias in [sheet.get("name", "")] + sheet.get("aliases", []):
                        if alias:
                            self._alias_index[alias.lower()] = sid
            if self._log is not None:
                self._log.success(
                    "Knowledge sheets loaded: {} elements", len(self._sheets_by_id)
                )
        except (OSError, ValueError) as exc:
            if self._log is not None:
                self._log.exception("Could not read element_sheets.json: {}", exc)

    def load_kb(self) -> dict:
        """Loads and caches knowledge_base.json, which provides monument-level overview
        context used as a fallback when a specific element sheet is unavailable."""
        if self._kb is not None:
            return self._kb

        self._kb = {}
        if not self.kb_path.exists():
            return self._kb
        try:
            with open(self.kb_path, "r", encoding="utf-8") as f:
                self._kb = json.load(f)
            if self._log is not None:
                self._log.success("Knowledge base loaded.")
        except (OSError, ValueError) as exc:
            if self._log is not None:
                self._log.exception("Could not read knowledge_base.json: {}", exc)
        return self._kb

    @property
    def sheets_by_id(self) -> dict:
        self.load_sheets()
        return self._sheets_by_id

    @property
    def alias_index(self) -> dict:
        self.load_sheets()
        return self._alias_index

    @property
    def kb(self) -> dict:
        return self.load_kb()

    # ------------------------------------------------------------- id lookup

    def sheet_for(self, element: str):
        """The sheet for an element id, falling back to a case-insensitive alias match.

        Vision emits Catalan/Spanish snake_case class labels ("sala_hipostila",
        "escalinata_drac"); the sheets carry a readable name and list those labels among
        their aliases.
        """
        self.load_sheets()
        sheet = self._sheets_by_id.get(element)
        if sheet is None:
            sid = self._alias_index.get(element.lower())
            sheet = self._sheets_by_id.get(sid) if sid else None
        return sheet

    def display_name(self, element: str | None) -> str | None:
        """The element's English name from its knowledge sheet.

        Resolving here keeps the snake_case identifier out of the prompt, and therefore
        out of the spoken answer. Falls back to the de-underscored identifier when no
        sheet matches, so an element the knowledge base does not cover still reads as
        words.
        """
        if not element or element == UNKNOWN_ELEMENT:
            return None
        sheet = self.sheet_for(element)
        if sheet is None:
            base = self.load_kb().get(element, {})
            return base.get("name") or element_display_name(element)
        return sheet.get("name") or element_display_name(element)

    def context_for_element(self, element: str) -> str:
        """Retrieves and formats factual context for an architectural element. Falls back
        to monument-level overview data if no specific element sheet is found, and returns
        an empty string if the element is absent from both knowledge files.

        The result deliberately does not depend on the personality. The three guides differ
        in how they speak, not in what is true, and one rendering shared by all of them is
        what lets a single cached KV state per element serve every button.
        """
        if not element or element == UNKNOWN_ELEMENT:
            return ""

        sheet = self.sheet_for(element)

        # fallback: monument level from knowledge_base.json
        if sheet is None:
            entry = self.load_kb().get(element, {})
            if entry:
                if self._log is not None:
                    self._log.info(
                        "KG: element {!r} served from knowledge_base.json", element
                    )
                return self.render_kb_entry(entry)
            self._warn("KG: element {!r} not found in any knowledge file.", element)
            return ""

        return self._build_element_context(sheet)

    def element_ids(self) -> list[str]:
        """Every element id the store knows, sorted. Used by prewarm_cache.py."""
        return sorted(self.sheets_by_id)

    def has_element(self, element: str) -> bool:
        return element in self.sheets_by_id

    # ------------------------------------------------------- prompt rendering

    def _build_element_context(self, sheet: dict) -> str:
        """Assembles the full context block for an element sheet: its own facts, a short
        summary of its parent monument if any, and up to two related-element notes,
        trimmed for the on-device SLM's small context window."""
        parts = [self.render_sheet(sheet)]

        parent_id = sheet.get("parent")
        if parent_id and parent_id != sheet.get("id"):
            parent_sheet = self.sheets_by_id.get(parent_id)
            if parent_sheet is not None:
                parts.append(self.render_parent_summary(parent_sheet))

        related = sheet.get("similarities", [])[:2]
        for note in related:
            parts.append(f"Related: {note}")

        return "\n---\n".join(p for p in parts if p)

    def render_parent_summary(self, parent_sheet: dict) -> str:
        """Produces a compact 2-3 line summary of the parent monument or area a sub-element
        belongs to (e.g. Park Güell for the Dragon Stairway). Unlike render_sheet, this
        stays short since it rides alongside the element's own facts."""
        name = parent_sheet.get("name", "")
        lines = [f"Part of: {name}"] if name else []
        if parent_sheet.get("creator"):
            lines.append(f"Creator: {parent_sheet['creator']}")
        if parent_sheet.get("inspiration"):
            lines.append(f"Context: {parent_sheet['inspiration']}")
        return "\n".join(lines)

    def render_sheet(self, sheet: dict) -> str:
        """Formats a knowledge sheet into a compact factual string for the SLM prompt.

        One rendering serves all three personalities. The per-personality field selection
        this replaced saved perhaps forty tokens of prompt, and cost a separate cached KV
        state per personality -- a bad trade once the prefix is read from disk rather than
        prefilled. The per-kind caps keep the block near the size the artistic rendering
        used to be, which matters for a 0.5B model's attention even though the prefill is
        now free.

        Every detail below is inside the prefix cache key. Do not reorder the fields,
        change a separator, or widen a cap without regenerating tests/golden/kg_context.json
        and accepting that deployed boards re-prefill from cold.
        """
        lines: list[str] = []
        name = sheet.get("name", "")
        if name:
            lines.append(f"Element: {name}")

        if sheet.get("creator"):
            lines.append(f"Creator: {sheet['creator']}")
        if sheet.get("timeline"):
            lines.append(f"Timeline: {sheet['timeline']}")
        if sheet.get("purpose"):
            lines.append(f"Purpose: {sheet['purpose']}")
        if sheet.get("inspiration"):
            lines.append(f"Inspiration: {sheet['inspiration']}")

        for key in ("materials", "construction_process", "technical_figures"):
            val = sheet.get(key)
            if not val:
                continue
            if isinstance(val, list):
                lines.append(f"{key}: {'; '.join(str(v) for v in val)}")
            elif isinstance(val, dict):
                for k2, v2 in val.items():
                    lines.append(f"{k2}: {v2}")
            else:
                lines.append(f"{key}: {val}")

        for fact in sheet.get("technical_facts", [])[:2]:
            lines.append(f"- {fact}")
        for fact in sheet.get("artistic_facts", [])[:2]:
            lines.append(f"- {fact}")
        for fact in sheet.get("general_knowledge_facts", [])[:1]:
            lines.append(f"- {fact}")

        # similarities are deliberately not rendered here: _build_element_context
        # already appends the first two as "Related:" lines. Emitting them in both
        # places, as the artistic rendering used to, spent tokens saying the same
        # thing twice to a model with 1024 of them.

        return "\n".join(lines)

    def render_kb_entry(self, entry: dict) -> str:
        """Formats a monument-level knowledge_base.json entry into a labeled string, deriving
        each label from its JSON key so new fields appear automatically without code changes.
        The 'name' field is surfaced first; list-of-strings fields render as bullets, nested
        dicts are flattened one level, and empty or falsy values are skipped."""
        lines: list[str] = []
        if name := entry.get("name"):
            lines.append(f"Name: {name}")

        for key, val in entry.items():
            if key == "name" or not val:
                continue
            label = key.replace("_", " ").title()

            if isinstance(val, list):
                if all(isinstance(v, str) for v in val):
                    lines.append(f"{label}:\n- " + "\n- ".join(val))
                else:
                    lines.append(f"{label}: {'; '.join(str(v) for v in val)}")
            elif isinstance(val, dict):
                for k2, v2 in val.items():
                    lines.append(f"{k2.replace('_', ' ').title()}: {v2}")
            else:
                lines.append(f"{label}: {val}")

        return "\n".join(lines).strip()

    # ---------------------------------------------------- keyword free-text

    # Words too generic to distinguish between entries -- excluded from scoring.
    _STOP_WORDS: frozenset = frozenset({
        "a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for",
        "is", "it", "its", "was", "are", "be", "by", "as", "with", "from",
        "that", "this", "what", "where", "when", "who", "which", "how",
        "did", "do", "does", "has", "have", "had", "been", "not",
        "kind", "built", "located", "tell", "me", "about", "give",
    })

    def _search_text(self, sheet: dict) -> str:
        """Flat, uncapped body text for scoring only -- never shown to a model.

        Deliberately not render_sheet(): that caps facts at 2 technical + 2 artistic + 1
        general, so scoring against it would make every fact beyond the caps unsearchable
        and a query matching a fifth technical fact would stop finding its sheet.
        """
        parts = [
            sheet.get("name", ""),
            sheet.get("creator", ""),
            sheet.get("timeline", ""),
            sheet.get("purpose", ""),
            sheet.get("inspiration", ""),
            sheet.get("construction_process", ""),
            " ".join(str(v) for v in sheet.get("materials", [])),
            " ".join(str(v) for v in sheet.get("technical_facts", [])),
            " ".join(str(v) for v in sheet.get("artistic_facts", [])),
            " ".join(str(v) for v in sheet.get("general_knowledge_facts", [])),
        ]
        figures = sheet.get("technical_figures")
        if isinstance(figures, dict):
            parts.extend(f"{k} {v}" for k, v in figures.items())
        return " ".join(p for p in parts if p)

    @staticmethod
    def _tokens(text: str) -> set:
        return set(re.findall(r"\w+", text.lower()))

    def search(self, query: str, k: int = 1) -> list[str]:
        """Best-matching rendered entries for a free-text query, highest score first.

        Scoring (per candidate):
        - 2 points for each query token matched in the entry's name / aliases (title match)
        - 1 point for each query token matched in its body text (body match)
        - Tokens in _STOP_WORDS are excluded to avoid false ties.
        - Matching uses word-token sets, not substring search, to avoid "on" matching
          inside "Antoni", "it" inside "architect", etc.

        The device never calls this -- vision names the element and `context_for_element`
        looks it up by id. It exists for the export bundle and the benchmark, where the
        question arrives as free text with no element id attached.
        """
        raw_tokens = self._tokens(query)
        tokens = raw_tokens - self._STOP_WORDS
        if not tokens:
            tokens = raw_tokens

        scored: list[tuple[int, str, str]] = []  # (score, kind, key)

        for key, entry in self.load_kb().items():
            title_words = self._tokens(
                " ".join([entry.get("name", ""), *entry.get("aliases", []), key])
            )
            body_words = self._tokens(self.render_kb_entry(entry))
            score = sum(2 for t in tokens if t in title_words) + sum(
                1 for t in tokens if t in body_words and t not in title_words
            )
            if score:
                scored.append((score, "kb", key))

        for sheet_id, sheet in self.sheets_by_id.items():
            title_words = self._tokens(
                " ".join([sheet.get("name", ""), *sheet.get("aliases", []), sheet_id])
            )
            body_words = self._tokens(self._search_text(sheet))
            score = sum(2 for t in tokens if t in title_words) + sum(
                1 for t in tokens if t in body_words and t not in title_words
            )
            if score:
                scored.append((score, "sheet", sheet_id))

        if not scored:
            return []

        scored.sort(key=lambda s: (-s[0], s[2]))
        out = []
        for _score, kind, key in scored[:k]:
            if kind == "sheet":
                out.append(self._build_element_context(self.sheets_by_id[key]))
            else:
                out.append(self.render_kb_entry(self.load_kb()[key]))
        return out

    def context_for_topic(self, query: str, k: int = 1) -> str:
        """Joined free-text context, or a safe instruction when nothing matches."""
        hits = self.search(query, k=k)
        if not hits:
            return (
                "No specific context available. Answer only with widely known, "
                "well-established facts about Antoni Gaudi, and say so if unsure."
            )
        return "\n\n---\n\n".join(hits)
