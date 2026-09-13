"""Bridge to the prompt construction and knowledge base the device actually ships.

This benchmark used to carry its own copy of the prompt: one flat string with a
generic "CulturaViva" persona. The device has since moved to chat messages whose
system turn puts the retrieved facts *first* and the personality instructions
second -- an ordering llama.cpp's prefix KV cache depends on. The two drifted, and
the benchmark ended up scoring a prompt that no longer shipped.

So rather than copy the prompt again, this imports it.

It used to import only *half* of what it needed. The prompt builders came from the
device; the facts they were given came from a renderer this project maintained
separately, which produced a prose blob the board has never emitted -- so
`personality/arms.py` claimed to build "the exact chat messages the device would
send" while feeding them context the device would never produce. Both halves now
come from the same place.

`arduino/python/guide_prompt.py` and `knowledge_store.py` are top-level,
stdlib-only modules on purpose, so importing them costs nothing: no `config`, and
therefore no camera, microphone or speaker probe, and no log file. That is why the
old `_quieten_device_logging()` workaround is gone.
"""

from __future__ import annotations

from core.device_paths import DEVICE_APP_DIR  # noqa: F401  (side effect: sys.path)

from guide_prompt import (
    PERSONALITIES,
    PERSONALITY_PROMPTS,
    build_facts_block,
    build_messages,
    build_system_prompt,
)
from knowledge_store import UNKNOWN_ELEMENT, KnowledgeStore, element_display_name

__all__ = [
    "DEVICE_APP_DIR",
    "PERSONALITIES",
    "PERSONALITY_PROMPTS",
    "UNKNOWN_ELEMENT",
    "KnowledgeStore",
    "build_facts_block",
    "build_messages",
    "build_system_prompt",
    "display_name",
    "element_display_name",
]

# One store for the whole process. Constructing it is cheap -- the JSON is loaded
# lazily on first lookup -- but sharing it means the sheets are parsed once.
_store: KnowledgeStore | None = None


def store() -> KnowledgeStore:
    """The device's knowledge store, reading the device's own JSON files."""
    global _store
    if _store is None:
        _store = KnowledgeStore()
    return _store


def display_name(element: str | None) -> str | None:
    """The element's English name, resolved exactly as the device resolves it."""
    return store().display_name(element)
