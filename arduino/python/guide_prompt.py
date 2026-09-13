"""How a question, a photo and a guide personality become chat messages.

The single definition of the prompt. The device builds every answer with it, the
SLM benchmark and the personality study import it through
`benchmark/slm/core/device_prompt.py`, and `prepare.py` copies it verbatim into the
Arduino export bundle.

It is separate from `core/model_module.py` for the same reason `knowledge_store.py`
is: `model_module` owns the llama.cpp lifecycle and imports `config`, which probes
for a camera, microphone and speaker on import. These are pure functions over
(question, element, personality, facts) and should cost nothing to import.

Top level rather than under `core/` -- see `knowledge_store.__doc__`; the benchmark
has its own `core` package that would shadow the device's.

The bundle used to carry its own prompt instead: a flat completion
("You are CulturaViva... Context: ... Visitor: ... Guide:") with no personality at
all, at max_tokens=150 and temperature=0.2 against the device's 60 and 0.1. That is
the drift this module exists to make impossible.
"""

from __future__ import annotations

from knowledge_store import UNKNOWN_ELEMENT, element_display_name

# System prompts for each Personality (Cultura Viva pipeline).
# Keys must match the values in models/models.json ("artistic", "technical", "child").
#
# Each guide is given a FORMAT requirement rather than a tone instruction. The
# earlier prompts described how to sound -- "speak with passion and use evocative
# metaphors", "be precise and rigorous", "use an animated tone" -- and a 0.5B model
# did not act on any of it: a blind judge recovered the intended guide in 38.9% of
# answers against a 33.3% chance baseline, and identified the child guide in 4% of
# its own (benchmark/slm/personality/results/baseline_tone_prompts/).
#
# The three required formats are deliberately orthogonal -- a comparison, a number,
# a closing question -- so the guides differ in something a listener can actually
# catch, rather than in three shades of register that all sound the same coming out
# of a small model.
PERSONALITY_PROMPTS: dict[str, str] = {
    "artistic": (
        "You are a tour guide who helps visitors see. "
        "You explain Gaudí's works through shape, colour, light and the forms he borrowed from nature. "
        "Every answer must contain one comparison to something from nature, written as \"like ...\". "
        "Answer only what the user asks, and add no unrelated background. "
        "Keep your response strictly under 3 short sentences (maximum 50 words)."
    ),
    "technical": (
        "You are a tour guide who explains how things were built. "
        "You explain Gaudí's works through construction techniques, materials and structural innovations. "
        "Every answer must contain at least one number written in digits, taken from the facts you were given. "
        "Answer only what the user asks, and add no unrelated background. "
        "Keep your response strictly under 3 short sentences (maximum 50 words)."
    ),
    "child": (
        "You are a tour guide talking to a child of about eight. "
        "You explain Gaudí's works in simple everyday words, with no technical terms. "
        "Every answer must end by asking the child a short question, finishing with a question mark. "
        "Answer only what the user asks, and add no unrelated background. "
        "Keep your response strictly under 3 short sentences (maximum 50 words)."
    ),
}

PERSONALITIES: tuple[str, ...] = tuple(PERSONALITY_PROMPTS)


def build_facts_block(
    element: str | None, kg_context: str, element_name: str | None = None
) -> str:
    """Renders the photo-dependent head of the system prompt: what vision detected and
    the facts retrieved for it.

    This block is deliberately free of anything personality-specific, and
    build_system_prompt puts it first, because it is the part that gets cached. llama.cpp
    reuses the longest common *prefix* of its KV cache and nothing else, so a block can
    only be restored from disk if it sits at the very front of the prompt -- see
    ModelRegistry.warm_prefix.

    Returns an empty string when there is nothing photo-dependent to say, in which case
    there is also nothing worth caching.
    """
    parts: list[str] = []

    if element == UNKNOWN_ELEMENT:
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


def build_system_prompt(
    element: str | None, personality: str, kg_context: str, element_name: str | None = None
) -> str:
    """Assembles the system message: what vision detected and the retrieved facts first,
    the personality instructions second.

    That order is what makes the prefix cache possible -- the facts are identical for
    every personality, so one cached KV state per element serves all three, and editing a
    personality prompt invalidates none of them. It also puts the instructions closer to
    the question, which small models tend to follow better.

    The rendered prompt up to the user turn is identical for every question asked about
    the same photo with the same personality, so llama.cpp treats it as a cache hit once
    warm_prefix() has evaluated it.
    """
    instructions = PERSONALITY_PROMPTS.get(
        personality, PERSONALITY_PROMPTS.get("artistic", "You are a tour guide.")
    )
    facts = build_facts_block(element, kg_context, element_name)
    return f"{facts}\n\n{instructions}" if facts else instructions


def build_messages(
    question: str,
    element: str | None,
    personality: str,
    kg_context: str,
    element_name: str | None = None,
) -> list[dict]:
    """Builds the chat messages for one question. The user turn holds nothing but the
    question, so it is the only part of the rendered prompt that changes between
    questions about the same photo."""
    return [
        {
            "role": "system",
            "content": build_system_prompt(element, personality, kg_context, element_name),
        },
        {"role": "user", "content": question or "(no question provided)"},
    ]
