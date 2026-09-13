"""The arms of the study: the three shipped guide personalities.

The prompts are not defined here. They are imported from the device application
through core.device_prompt, so what this study measures is what actually ships.

The one thing worth guarding: build_system_prompt resolves an unknown personality
name by silently falling back to artistic --

    PERSONALITY_PROMPTS.get(personality, PERSONALITY_PROMPTS.get("artistic", ...))

so a typo in an arm name does not raise, it quietly generates a second artistic
arm. The study would then compare artistic against artistic and report a perfect
null with no sign anything went wrong. resolve_arms() refuses unknown names up
front for that reason.
"""

from __future__ import annotations

from core.device_prompt import (
    PERSONALITIES,
    PERSONALITY_PROMPTS,
    build_messages,
    build_system_prompt,
)

__all__ = ["ARMS", "resolve_arms", "messages_for", "system_prompt_for", "assert_arms_distinct"]

ARMS: tuple[str, ...] = PERSONALITIES


def resolve_arms(names: list[str] | None) -> list[str]:
    """Validate requested arm names against the personalities the device defines.

    Raises rather than falling back, because the fallback is invisible: an
    unrecognised name would produce a duplicate artistic arm and a meaningless null.
    """
    if not names:
        return list(ARMS)
    unknown = [n for n in names if n not in PERSONALITY_PROMPTS]
    if unknown:
        raise ValueError(
            f"Unknown personality {unknown}. The device defines: {list(ARMS)}. "
            "Refusing to continue -- build_system_prompt would silently substitute "
            "'artistic' and the run would compare it against itself."
        )
    return list(names)


def system_prompt_for(arm: str, element: str | None, kg_context: str) -> str:
    """The exact system turn the device would send for this arm."""
    if arm not in PERSONALITY_PROMPTS:
        raise ValueError(f"Unknown personality {arm!r}")
    return build_system_prompt(element, arm, kg_context)


def messages_for(question: str, arm: str, element: str | None, kg_context: str) -> list[dict]:
    """The exact chat messages the device would send for this arm."""
    if arm not in PERSONALITY_PROMPTS:
        raise ValueError(f"Unknown personality {arm!r}")
    return build_messages(question, element, arm, kg_context)


def assert_arms_distinct(arms: list[str], element: str | None, kg_context: str) -> None:
    """Pre-flight: the arms must render pairwise-distinct system prompts.

    Cheap insurance against the silent fallback, against a prompt-editing accident
    that makes two personalities identical, and against a future refactor that
    breaks the import in core.device_prompt.
    """
    rendered = {arm: system_prompt_for(arm, element, kg_context) for arm in arms}
    for i, a in enumerate(arms):
        for b in arms[i + 1:]:
            if rendered[a] == rendered[b]:
                raise AssertionError(
                    f"Arms {a!r} and {b!r} render an identical system prompt. "
                    "The study would be comparing a personality against itself."
                )


# Each guide's prompt demands one concrete, mechanically checkable thing. These
# check whether it actually did it. Compliance is what separates "the model
# ignored the instruction" from "the model obeyed and the voices are still
# indistinguishable" -- two findings with entirely different remedies.
#
# The three requirements are orthogonal on purpose: a comparison, a number and a
# closing question cannot be satisfied by the same sentence, so a guide that obeys
# is distinguishable from one that does not.
FORMAT_REQUIREMENT: dict[str, str] = {
    "artistic": 'one comparison to nature, written as "like ..."',
    "technical": "one number, measurement or date",
    "child": "a closing question inviting the child to look",
}


def follows_format(arm: str, answer: str) -> bool:
    """Did this answer satisfy the format its personality prompt demands?"""
    text = answer.strip()
    low = text.lower()
    if arm == "artistic":
        return " like " in low or low.startswith("like ")
    if arm == "technical":
        return any(c.isdigit() for c in text)
    if arm == "child":
        return text.endswith("?")
    raise ValueError(f"No format requirement defined for {arm!r}")
