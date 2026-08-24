"""Generate English Cultura Viva queries lasting approximately 3 to 20 seconds.

Custom TTS generation is standard for a reproducible benchmark fixture: it gives
each audio file a checked reference transcript and makes regeneration cheap.
External services can produce more natural voices, but should be exported to the
same 16 kHz mono WAV format before benchmarking.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import random
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

from utils import find_domain_keywords

APP_DIR = Path(__file__).resolve().parent

QUERIES = [
    {"intent": "materials", "voice": "en-US-AnaNeural", "speaker": "child_like", "rate": "+8%", "pitch": "+6Hz", "keywords": ["Gaudí", "trencadís"], "text": "What is this amazing Gaudí wall made of, and why does its trencadís surface look like it is moving?", "background_noise": 0.012},
    {"intent": "materials", "register": "polite", "voice": "en-GB-SoniaNeural", "rate": "-8%", "pitch": "-1Hz", "text": "Could you explain which materials were used on this building and how the architect combined stone, iron, and colorful ceramic details?"},
    {"intent": "materials", "register": "analytical", "voice": "en-GB-RyanNeural", "rate": "-5%", "pitch": "+0Hz", "keywords": ["modernisme"], "text": "I would like to understand how structural stone and cast iron work together in Catalan modernisme with decorative mosaic elements."},
    {"intent": "architect", "voice": "en-US-GuyNeural", "rate": "+2%", "pitch": "+0Hz", "keywords": ["Gaudí", "Casa Batlló"], "text": "Who was Gaudí, the architect behind Casa Batlló, and what made his style so different from other buildings in Barcelona?", "pause_ms": 650},
    {"intent": "architect", "register": "polite", "voice": "en-US-JennyNeural", "rate": "-8%", "pitch": "+0Hz", "text": "Excuse me, could you tell me which architect designed this monument and why the project is considered important?"},
    {"intent": "date", "register": "analytical", "voice": "en-GB-RyanNeural", "rate": "-7%", "pitch": "-1Hz", "text": "I am interested in the construction timeline: when did the project begin, what delayed it, and which parts were completed later?"},
    {"intent": "date", "voice": "en-US-AriaNeural", "rate": "+0%", "pitch": "+1Hz", "text": "When was this building started, and how many years did it take before visitors could see the finished parts?"},
    {"intent": "dragon_roof", "register": "polite", "voice": "en-GB-SoniaNeural", "rate": "-10%", "pitch": "-2Hz", "keywords": ["Casa Batlló", "dragon"], "text": "Would you explain what the dragon-shaped roof of Casa Batlló represents and how it connects this building with Catalan legend?"},
    {"intent": "dragon_roof", "voice": "en-US-GuyNeural", "rate": "+0%", "pitch": "+0Hz", "keywords": ["dragon", "Casa Batlló"], "text": "Why why does the Casa Batlló roof look like a dragon, and what story is this colorful design telling?", "stutter": "repeated_word"},
    {"intent": "columns", "voice": "en-US-AnaNeural", "speaker": "child_like", "rate": "+10%", "pitch": "+8Hz", "text": "Why do the big pillars look like tree branches, and how do they keep the roof from falling down?"},
    {"intent": "columns", "register": "polite", "voice": "en-US-JennyNeural", "rate": "-7%", "pitch": "+0Hz", "text": "Could you describe why the interior pillars branch out like trees and explain the purpose of that design?"},
    {"intent": "mosaic", "voice": "en-US-AriaNeural", "rate": "+1%", "pitch": "+0Hz", "keywords": ["trencadís", "Park Güell"], "text": "What is this bright broken-tile trencadís called, and where else can we see it around Park Güell?"},
    {"intent": "mosaic", "register": "analytical", "voice": "en-GB-RyanNeural", "rate": "-10%", "pitch": "+0Hz", "text": "How does trencadis transform broken ceramic fragments into a deliberate artistic surface, and what purpose does it serve?"},
    {"intent": "salamander", "voice": "en-US-AnaNeural", "speaker": "child_like", "rate": "+8%", "pitch": "+7Hz", "keywords": ["salamander", "Park Güell"], "text": "What is the shiny salamander by the stairs in Park Güell, and why does everybody take a picture of it?", "background_noise": 0.018},
    {"intent": "salamander", "register": "polite", "voice": "en-US-JennyNeural", "rate": "-8%", "pitch": "+0Hz", "text": "Would you tell me what the salamander represents and how its ceramic surface fits into the park's design?"},
    {"intent": "construction", "voice": "en-US-GuyNeural", "rate": "-2%", "pitch": "+0Hz", "keywords": ["Sagrada Família", "Gaudí"], "text": "Why did Gaudí's Sagrada Família take so long to build, and what is still unfinished today?"},
    {"intent": "construction", "register": "polite", "voice": "en-GB-SoniaNeural", "rate": "-12%", "pitch": "-2Hz", "text": "Could you explain why construction continued for so many years, including changes of architect, funding, and interruptions?"},
    {"intent": "construction", "register": "analytical", "voice": "en-GB-RyanNeural", "rate": "-12%", "pitch": "-1Hz", "keywords": ["Gaudí", "Sagrada Família"], "text": "I would like to understand the historical reasons for the long construction period of Gaudí's Sagrada Família, from his original plans through later technical and financial challenges."},
    {"intent": "unesco", "voice": "en-US-AriaNeural", "rate": "+0%", "pitch": "+1Hz", "keywords": ["Gaudí", "Casa Milà"], "text": "Which of Gaudí's buildings, including Casa Milà, have UNESCO status, and what makes them important enough to protect?"},
    {"intent": "unesco", "register": "polite", "voice": "en-GB-SoniaNeural", "rate": "-8%", "pitch": "-1Hz", "text": "Could you tell me which Gaudi works are recognized by UNESCO and what their heritage designation means?"},
    {"intent": "park_history", "voice": "en-US-GuyNeural", "rate": "-2%", "pitch": "+0Hz", "keywords": ["Park Güell", "Gaudí"], "text": "How did Gaudí's Park Güell change from a planned housing project into the public park we see today?"},
    {"intent": "park_history", "register": "analytical", "voice": "en-GB-RyanNeural", "rate": "-10%", "pitch": "-1Hz", "text": "What economic, social, and design factors explain why the original Park Guell housing plan was not completed?"},
    {"intent": "facades", "voice": "en-US-JennyNeural", "rate": "+0%", "pitch": "+0Hz", "keywords": ["Sagrada Família", "Gaudí"], "text": "What do the different facades of Gaudí's Sagrada Família represent, and how can I tell them apart?"},
    {"intent": "facades", "register": "polite", "voice": "en-GB-SoniaNeural", "rate": "-10%", "pitch": "-2Hz", "text": "Would you please compare the Nativity, Passion, and Glory facades and explain the story represented by each one?"},
]

UNIQUE_OPENINGS = [
    "We have arrived at this part of the tour.",
    "Before we move on, consider the materials here.",
    "From this viewpoint, the modernist structure is striking.",
    "At first glance, this building seems almost alive.",
    "One important question concerns the architect's legacy.",
    "To place this monument in context, start with its timeline.",
    "Looking toward the unfinished structure raises a historical question.",
    "Along this facade, myth and architecture meet.",
    "Here the roof turns a legend into a visible form.",
    "Notice how the dragon imagery changes the building's character.",
    "Inside this space, the columns resemble a living forest.",
    "Across the mosaic surface, broken pieces become a design.",
    "Among the colorful details, one Catalan technique stands out.",
    "Near the staircase, the famous salamander attracts visitors.",
    "During this stop, the park's signature creature deserves attention.",
    "While visiting the basilica, its long construction history is unavoidable.",
    "Beyond the present-day view, several architects shaped the project.",
    "Historically, Gaudi's original plans faced major challenges.",
    "Regarding heritage protection, UNESCO recognition is significant.",
    "For Casa Mila, the nickname La Pedrera hints at its stone facade.",
    "Around Park Guell, the landscape and architecture work together.",
    "Comparing these buildings reveals the language of modernisme.",
    "Turning to the basilica facades shows three different narratives.",
    "Finally, the Nativity, Passion, and Glory facades complete the comparison.",
]


def validate_queries() -> None:
    """Reject accidental duplicate question text or utterance openings."""
    questions = [" ".join(query["text"].casefold().split()) for query in QUERIES]
    if len(set(questions)) != len(questions):
        raise ValueError("Every benchmark question must have unique content")
    if len(UNIQUE_OPENINGS) != len(QUERIES) or len(set(UNIQUE_OPENINGS)) != len(UNIQUE_OPENINGS):
        raise ValueError("Every benchmark utterance must have a unique opening")

SPEAKER_PROFILES = {
    "en-US-AnaNeural": "child-like female voice",
    "en-US-AriaNeural": "adult female voice, United States",
    "en-US-JennyNeural": "adult female voice, United States",
    "en-US-GuyNeural": "adult male voice, United States",
    "en-GB-SoniaNeural": "adult female voice, United Kingdom",
    "en-GB-RyanNeural": "adult male voice, United Kingdom",
}


def convert_to_wav(source: Path, target: Path) -> None:
    """Convert synthesized audio to PCM, 16 kHz, mono WAV."""
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(target)],
        check=True,
    )


def apply_audio_effects(source: Path, target: Path, query: dict[str, Any], seed: int) -> None:
    """Add deterministic pause/noise effects while preserving 16-bit mono PCM."""
    with wave.open(str(source), "rb") as audio:
        parameters = audio.getparams()
        frames = bytearray(audio.readframes(audio.getnframes()))
    if parameters.sampwidth != 2 or parameters.nchannels != 1:
        raise ValueError("audio effects require 16-bit mono WAV input")

    samples = [int.from_bytes(frames[index:index + 2], "little", signed=True)
               for index in range(0, len(frames), 2)]
    sample_rate = parameters.framerate
    pause_ms = int(query.get("pause_ms", 0))
    if pause_ms:
        midpoint = len(samples) // 2
        samples[midpoint:midpoint] = [0] * int(sample_rate * pause_ms / 1000)

    noise_level = float(query.get("background_noise", 0))
    if noise_level:
        randomizer = random.Random(seed)
        amplitude = int(32767 * noise_level)
        samples = [max(-32768, min(32767, sample + randomizer.randint(-amplitude, amplitude)))
                   for sample in samples]

    with wave.open(str(target), "wb") as output:
        output.setparams(parameters)
        output.writeframes(b"".join(sample.to_bytes(2, "little", signed=True) for sample in samples))


async def synthesize(query: dict[str, Any], target: Path) -> None:
    """Generate one file with Edge TTS rate and pitch controls."""
    import edge_tts

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temporary:
        source = Path(temporary.name)
    try:
        communicator = edge_tts.Communicate(query.get("synthesis_text", query["text"]), query["voice"], rate=query["rate"], pitch=query["pitch"])
        await communicator.save(str(source))
        convert_to_wav(source, target)
    finally:
        source.unlink(missing_ok=True)


def wav_duration_seconds(path: Path) -> float:
    """Read the generated PCM WAV duration without loading samples."""
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


async def generate(output_dir: Path) -> None:
    """Generate WAV files and a manifest with exact English references."""
    validate_queries()
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale_file in output_dir.glob("query_*.wav"):
        stale_file.unlink()
    manifest = []
    for index, query in enumerate(QUERIES, start=1):
        register = query.get("register", "neutral")
        filename = f"query_{index:02d}_{register}_{query['intent']}.wav"
        target = output_dir / filename
        lead_in = UNIQUE_OPENINGS[index - 1]
        full_text = f"{lead_in} {query['text']}".strip()
        synthesis_text = full_text.replace("appreciate", "uh-PREE-shee-ate")
        synthesis_query = {**query, "text": full_text, "synthesis_text": synthesis_text}
        await synthesize(synthesis_query, target)
        if wav_duration_seconds(target) < 3:
            print(f"[WARN] Edge TTS returned a short clip for {filename}; retrying once.")
            await synthesize(synthesis_query, target)
        effects = {
            "pause_ms": query.get("pause_ms", 0),
            "background_noise_level": query.get("background_noise", 0),
        }
        if effects["pause_ms"] or effects["background_noise_level"]:
            apply_audio_effects(target, target, query, seed=index)
        duration = round(wav_duration_seconds(target), 2)
        if not 3 <= duration <= 20:
            print(f"[WARN] {filename} duration is {duration}s; expected 3-20s")
        manifest.append({
            "filename": filename,
            "language": "en",
            "register": register,
            "intent": query["intent"],
            "lead_in": lead_in,
            "question": query["text"],
            "text": full_text,
            "pronunciation_hints": {"appreciate": "uh-PREE-shee-ate"} if "appreciate" in full_text else {},
            "keywords": query.get("keywords") or find_domain_keywords(full_text),
            "audio_effects": effects,
            "speaker": query.get("speaker", SPEAKER_PROFILES[query["voice"]]),
            "voice": query["voice"],
            "duration_seconds": duration,
        })
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {len(manifest)} English WAV files in {output_dir}")


def main() -> None:
    """Parse generator options and run the selected TTS engine."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(APP_DIR / "data_audio"))
    args = parser.parse_args()
    asyncio.run(generate(Path(args.output_dir)))


if __name__ == "__main__":
    main()
