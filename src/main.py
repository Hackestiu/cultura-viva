import argparse
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from config import OUTPUT_WAV
from knowledge.knowledge_graph import get_context
from speech.slm import ask_slm
from speech.stt import transcribe
from speech.tts import synthesize
from vision.classifiers import Location, classify_for_location


class Personality(Enum):
    """Guiding style selected via a button on the physical exhibit.
    The enum value is assumed to already be resolved at this point."""

    ARTISTIC = "artistic"
    TECHNICAL = "technical"
    CHILD = "child"


SYSTEM_PROMPTS: dict[Personality, str] = {
    Personality.ARTISTIC: (
        "You are a passionate art guide at a Gaudí site. Speak evocatively "
        "about form, texture, light and symbolism. Favour sensory, emotive "
        "language over dates and figures."
    ),
    Personality.TECHNICAL: (
        "You are an architecture guide at a Gaudí site. Answer with precise, "
        "factual detail: construction techniques, materials, structural "
        "innovations and dates. Avoid flowery language."
    ),
    Personality.CHILD: (
        "You are a friendly guide explaining a Gaudí site to a curious child "
        "around 8 years old. Use short sentences, simple words and fun "
        "comparisons. Keep it playful and encouraging."
    ),
}


@dataclass
class VisitResult:
    element: Optional[str]
    question: str
    answer: str
    audio_path: str


def run(
    location: Location,
    personality: Personality,
    audio_path: str,
    image_path: Optional[str] = None,
    output_path: str = OUTPUT_WAV,
) -> VisitResult:
    """Run the full orchestration: STT -> per-location vision -> KG lookup -> SLM -> TTS."""
    question = transcribe(audio_path)
    if not question.strip():
        raise ValueError("No speech detected in the audio file.")

    element = classify_for_location(location, image_path)
    kg_context = get_context(element)
    system_prompt = SYSTEM_PROMPTS[personality]

    answer = ask_slm(
        question,
        image_labels=[element] if element else None,
        system_prompt=system_prompt,
        kg_context=kg_context,
    )

    synthesize(answer, output_path)
    return VisitResult(element=element, question=question, answer=answer, audio_path=output_path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Gaudí guide orchestration: STT -> vision -> SLM -> TTS."
    )
    parser.add_argument(
        "location", choices=[loc.value for loc in Location], help="Physical site the visitor is at."
    )
    parser.add_argument(
        "personality",
        choices=[p.value for p in Personality],
        help="Guiding style selected via the exhibit button.",
    )
    parser.add_argument("audio_path", help="Path to the visitor's spoken question (.wav).")
    parser.add_argument(
        "image_path", nargs="?", default=None, help="Optional path to the captured photo."
    )
    return parser.parse_args()


def main() -> None:
    """Main function to run the full orchestration from the CLI."""
    args = _parse_args()
    location = Location(args.location)
    personality = Personality(args.personality)

    try:
        result = run(location, personality, args.audio_path, args.image_path)
    except ValueError as exc:
        print(exc)
        sys.exit(1)

    print("\n--- Orchestration complete ---")
    print(f"Location:         {location.value}")
    print(f"Personality:      {personality.value}")
    print(f"Detected element: {result.element}")
    print(f"Question:         {result.question}")
    print(f"Answer:           {result.answer}")


if __name__ == "__main__":
    main()
