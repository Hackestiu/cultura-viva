"""The rendered knowledge context is frozen. These tests are what freeze it.

`ModelRegistry._prefix_state_path` names each cached KV state by the sha256 of the
rendered facts block, so any change to field order, a separator, or one of the
`[:2]` caps in `KnowledgeStore.render_sheet` silently orphans every
`data/prefix_cache/prefix_*.pkl` on every deployed board. Nothing is wrong with the
answers afterwards -- they just cost a full cold prefill each, roughly 30 s per
element across 24 elements.

`golden/kg_context.json` was captured from `core/model_module.py`'s ModelRegistry
*before* the knowledge_store extraction, so a green run here is the proof that
moving the renderer out changed no byte of what the model sees.

These import only `knowledge_store` -- no `config`, no `model_module`, no loguru,
no hardware. That is the whole point of the module being dependency-free: this file
needs no fixtures, no venv and none of the device's heavy dependencies.

    uv run --no-project --python 3.12 -m pytest arduino/python/tests -q
"""

import hashlib
import json
from pathlib import Path

import pytest

from knowledge_store import KnowledgeStore, element_display_name

HERE = Path(__file__).resolve().parent
GOLDEN_PATH = HERE / "golden" / "kg_context.json"
GOLDEN = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
PINNED_MODEL_NAME = GOLDEN["pinned_model_name"]

ALL_KEYS = sorted(GOLDEN["entries"])


@pytest.fixture(scope="module")
def store():
    return KnowledgeStore()


def _facts_block(element, kg_context, element_name):
    """The head of the system prompt, inlined from core.model_module.build_facts_block.

    Inlined rather than imported so this file stays free of `config`. build_facts_block
    is not touched by the extraction, so re-deriving the digest from context_for_element
    and display_name is sufficient proof that the cache key is stable.
    """
    parts = []
    if element == "unknown":
        parts.append(
            "[Visual recognition: The photo does not match any architectural element of this monument. "
            "Politely and concisely tell the user (in your assigned guide personality) that the photo does not seem "
            "to show a recognized monument element, and invite them to capture an architectural element if they'd like details.]"
        )
    elif element:
        parts.append(
            f"[Detected element in photo: {element_name or element_display_name(element)}]"
        )
    if kg_context:
        parts.append(f"[Factual information about the element:\n{kg_context}]")
    return "\n\n".join(parts)


def _digest(facts: str) -> str:
    return hashlib.sha256(
        f"{PINNED_MODEL_NAME}\x00{facts}".encode("utf-8")
    ).hexdigest()[:32]


def test_golden_covers_every_sheet(store):
    """The golden file must not silently stop covering a sheet somebody added."""
    assert set(store.element_ids()) == set(GOLDEN["sheet_ids"]), (
        "element_sheets.json gained or lost a sheet. Regenerate the golden file and "
        "review the diff -- every changed entry is a cold prefill on every board."
    )


@pytest.mark.parametrize("key", ALL_KEYS)
def test_display_name_matches_golden(store, key):
    expected = GOLDEN["entries"][key]["display_name"]
    assert store.display_name(key or None) == expected


@pytest.mark.parametrize("key", ALL_KEYS)
def test_rendered_context_matches_golden(store, key):
    expected = GOLDEN["entries"][key]["kg_context"]
    assert store.context_for_element(key) == expected


@pytest.mark.parametrize("key", ALL_KEYS)
def test_prefix_cache_digest_is_stable(store, key):
    """The assertion that actually protects deployed boards."""
    entry = GOLDEN["entries"][key]
    name = store.display_name(key or None)
    facts = _facts_block(key or None, store.context_for_element(key), name)
    assert facts == entry["facts_block"]
    assert _digest(facts) == entry["prefix_digest"]


def test_identifiers_never_reach_the_prompt(store):
    """No raw snake_case id may appear in a rendered context.

    The benchmark's old renderer interpolated the parent *id*, producing
    "Serpentine Bench (part of park_guell)" -- which the model then read aloud and
    invented around. The device renderer resolves the parent's display name instead.
    """
    for eid in store.element_ids():
        ctx = store.context_for_element(eid)
        for other in store.element_ids():
            assert f"(part of {other})" not in ctx
            assert f"Part of: {other}\n" not in ctx


def test_search_finds_sheets_by_body_text(store):
    """Keyword search must reach facts beyond render_sheet's caps.

    This is why _search_text exists as a separate projection: scoring against the
    capped prompt rendering would make these unfindable.
    """
    hits = store.search("catenary arches attic", k=1)
    assert hits and "Casa" in hits[0]


def test_search_returns_a_safe_default_when_nothing_matches(store):
    out = store.context_for_topic("zzzz qqqq xxxx")
    assert "No specific context available" in out


def test_unknown_and_missing_elements_render_empty(store):
    assert store.context_for_element("no_such_element") == ""
    assert store.context_for_element("") == ""
