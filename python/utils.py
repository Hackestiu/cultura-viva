"""Small, dependency-light helpers shared by the STT benchmark."""

from __future__ import annotations

import json
import math
import os
import platform
import re
import subprocess
import sys
import unicodedata
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from difflib import SequenceMatcher


DOMAIN_KEYWORD_ALIASES = {
    "Gaudí": ("gaudí", "gaudi"),
    "Sagrada Família": ("sagrada família", "sagrada familia"),
    "salamander": ("salamander",),
    "dragon": ("dragon",),
    "trencadís": ("trencadís", "trencadis"),
    "Park Güell": ("park güell", "park guell"),
    "Casa Batlló": ("casa batlló", "casa batllo"),
    "Casa Milà": ("casa milà", "casa mila"),
    "modernisme": ("modernisme", "modernism"),
}

DOMAIN_ENTITY_REPLACEMENTS = {
    "gaudi": "Gaudí",
    "gaudy": "Gaudí",
    "gotti": "Gaudí",
    "sagrada familia": "Sagrada Família",
    "park guell": "Park Güell",
    "park guelph": "Park Güell",
    "park well": "Park Güell",
    "casa batllo": "Casa Batlló",
    "casa batlo": "Casa Batlló",
    "casa batlow": "Casa Batlló",
    "casa botlo": "Casa Batlló",
    "casa mila": "Casa Milà",
    "trencadis": "trencadís",
    "trincottis": "trencadís",
    "trincardis": "trencadís",
    "trend cotted": "trencadís",
    "trend-cotted": "trencadís",
    "modernism": "modernisme",
}


def build_domain_prompt() -> str:
    """Build a Whisper-style domain-vocabulary hint from the canonical keyword list.

    Reuses DOMAIN_KEYWORD_ALIASES — the same table used for keyword-spotting
    scoring and for sherpa-onnx's hotwords file — as the single source of
    truth, so every engine's domain hint (when enabled) refers to exactly the
    same entities the benchmark scores against.
    """
    entries = []
    for canonical, aliases in DOMAIN_KEYWORD_ALIASES.items():
        alt_spellings = [alias for alias in aliases if alias.casefold() != canonical.casefold()]
        entries.append(f"{canonical} and {', '.join(alt_spellings)}" if alt_spellings else canonical)
    return "A tour of Barcelona and Catalonia. Proper names include " + ", ".join(entries) + "."


def build_sherpa_hotwords_file(
    keywords: Iterable[str], model_dir: Path, output_path: Path, score: float = 2.0
) -> Path | None:
    """Write a sherpa-onnx hotwords file (BPE-tokenized keywords + boosting score).

    Returns None instead of raising when domain-bias hotwords cannot be built
    safely for this model (no sentencepiece installed, no bundled bpe.model —
    e.g. a Whisper export, which never supports hotwords — or a keyword whose
    BPE round-trip doesn't reconstruct the original text), so the caller can
    fall back to running that engine without domain bias instead of risking a
    malformed hotwords file at decode time.
    """
    bpe_model_path = model_dir / "bpe.model"
    if not bpe_model_path.is_file():
        return None
    try:
        import sentencepiece as spm
    except ImportError:
        return None

    processor = spm.SentencePieceProcessor()
    processor.load(str(bpe_model_path))

    lines = []
    for keyword in keywords:
        for candidate in (keyword, keyword.upper(), keyword.lower()):
            pieces = processor.encode(candidate, out_type=str)
            if not pieces:
                continue
            reconstructed = "".join(pieces).replace("\u2581", " ").strip()
            if reconstructed.casefold() == candidate.casefold():
                lines.append(f"{' '.join(pieces)}:{score}")
                break
    if not lines:
        return None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def normalize_text(text: str) -> str:
    """Normalize punctuation and whitespace while preserving accented words."""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"[^\w\s']", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def canonicalize_domain_entities(text: str) -> str:
    """Restore canonical spelling for known domain entities in any engine output."""
    replacements = sorted(DOMAIN_ENTITY_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True)
    for alias, canonical in replacements:
        text = re.sub(rf"(?<!\w){re.escape(alias)}(?!\w)", canonical, text, flags=re.IGNORECASE)
    return text


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Calculate WER with a compact dynamic-programming implementation."""
    reference_words = normalize_text(reference).split()
    hypothesis_words = normalize_text(hypothesis).split()
    if not reference_words:
        return math.nan
    previous = list(range(len(hypothesis_words) + 1))
    for row, reference_word in enumerate(reference_words, start=1):
        current = [row]
        for column, hypothesis_word in enumerate(hypothesis_words, start=1):
            substitution = previous[column - 1] + (reference_word != hypothesis_word)
            insertion = current[column - 1] + 1
            deletion = previous[column] + 1
            current.append(min(substitution, insertion, deletion))
        previous = current
    return previous[-1] / len(reference_words)


def character_error_rate(reference: str, hypothesis: str) -> float:
    """Calculate CER after normalizing case, punctuation, and whitespace."""
    reference_text = normalize_text(reference).replace(" ", "")
    hypothesis_text = normalize_text(hypothesis).replace(" ", "")
    if not reference_text:
        return math.nan
    previous = list(range(len(hypothesis_text) + 1))
    for row, reference_char in enumerate(reference_text, start=1):
        current = [row]
        for column, hypothesis_char in enumerate(hypothesis_text, start=1):
            substitution = previous[column - 1] + (reference_char != hypothesis_char)
            insertion = current[column - 1] + 1
            deletion = previous[column] + 1
            current.append(min(substitution, insertion, deletion))
        previous = current
    return previous[-1] / len(reference_text)


def _strip_accents(text: str) -> str:
    """Remove diacritics so accented and unaccented forms compare equally."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def _fuzzy_keyword_present(keyword: str, haystack_spaceless: str, threshold: float = 0.72) -> bool:
    """Return True if a space-free substring of the hypothesis is phonetically close to keyword.

    ASR engines routinely mishear a multi-word or single-word domain entity as
    a different number of words (e.g. "trencadis" heard as "trend kind of",
    "Casa Batllo" heard as "Casa Bortlow"). Comparing word-for-word against a
    fixed alias list therefore misses new mishearings the alias table was never
    updated for. Comparing space-free substrings with a sliding window
    generalizes to mishearings not seen before, instead of requiring each one
    to be hand-added.
    """
    needle = _strip_accents(keyword.casefold()).replace(" ", "")
    needle_len = len(needle)
    for size in range(max(1, needle_len - 2), needle_len + 4):
        for start in range(0, max(1, len(haystack_spaceless) - size + 1)):
            window = haystack_spaceless[start:start + size]
            if SequenceMatcher(None, needle, window).ratio() >= threshold:
                return True
    return False


def find_domain_keywords(text: str) -> list[str]:
    """Return canonical Cultura Viva keywords present in text, exact or phonetically close."""
    normalized = normalize_text(text)
    haystack_spaceless = _strip_accents(normalized).replace(" ", "")
    return [
        keyword
        for keyword, aliases in DOMAIN_KEYWORD_ALIASES.items()
        if any(alias in normalized for alias in aliases)
        or _fuzzy_keyword_present(keyword, haystack_spaceless)
    ]


def keyword_spotting_accuracy(
    reference: str, hypothesis: str, keywords: Iterable[str] | None = None
) -> float:
    """Score the fraction of reference domain keywords recovered by the model."""
    expected = list(keywords or find_domain_keywords(reference))
    if not expected:
        return math.nan
    found = set(find_domain_keywords(hypothesis))
    return sum(keyword in found for keyword in expected) / len(expected)


def wav_duration_seconds(path: Path) -> float:
    """Read duration without decoding the full recording into memory."""
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def wav_format(path: Path) -> tuple[int, int, int]:
    """Return (frame_rate, channels, sample_width_bytes) for a WAV file."""
    with wave.open(str(path), "rb") as audio:
        return audio.getframerate(), audio.getnchannels(), audio.getsampwidth()


def ensure_16k_mono_pcm16(source: Path, cache_dir: Path) -> Path:
    """Return a path to a 16 kHz mono 16-bit PCM copy of `source`, converting via ffmpeg if needed.

    BUG THIS FIXES: only the synthetic TTS generator (dataset_generator.py)
    guarantees 16 kHz/mono/PCM16 output. A human-recorded dataset dropped into
    data_audio/recorded/ (the set main.py *prefers* when present) may well be
    44.1/48 kHz stereo straight off whatever device captured it, and nothing
    upstream of this benchmark validated or normalized that.

    That mismatch degrades engines very unevenly, which is what makes it look
    like a model-quality problem rather than a plumbing one:
      - faster-whisper resamples internally, so it mostly tolerates it.
      - Vosk reads audio.getframerate() itself and adapts.
      - sherpa-onnx's transducer path is built with a hardcoded
        sample_rate=16000 feature extractor and does no resampling of its
        own (see SherpaOnnxRecognizer) — feeding it 44.1/48 kHz audio silently
        produces near-garbage transcriptions instead of an error.

    Normalizing every file before it reaches a recognizer removes this
    confound so WER/CER differences reflect the models, not the input format.
    """
    frame_rate, channels, sample_width = wav_format(source)
    if (frame_rate, channels, sample_width) == (16000, 1, 2):
        return source

    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / source.name
    if not target.exists() or target.stat().st_mtime < source.stat().st_mtime:
        print(
            f"[INFO] {source.name} is {frame_rate} Hz / {channels}ch / "
            f"{sample_width * 8}-bit; resampling to 16 kHz mono PCM16 for scoring."
        )
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error", "-i", str(source),
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(target),
            ],
            check=True,
        )
    return target


def resolve_faster_whisper_path(model_name_or_path: str) -> str | None:
    """Resolve a faster-whisper model name to a local snapshot directory, offline-safe.

    BUG THIS FIXES: faster_whisper.utils.download_model(..., local_files_only=True)
    only recognizes its own expected Hugging Face cache layout. On an offline
    edge device (Arduino Uno Q) where the model was provisioned by copying files
    into place rather than by letting faster-whisper manage its own cache, that
    call raises even though the model is present and loads fine. Previously this
    caused model_size_mb() to silently return None for every faster-whisper
    engine, which is exactly why Whisper model sizes were missing from the
    resource-usage plot while Vosk/sherpa-onnx (which just read a directory the
    user points at directly) were not.

    Falls back to scanning the standard Hugging Face hub cache layout by hand.
    Returns None only if no local copy can be found by any method.
    """
    candidate = Path(model_name_or_path)
    if candidate.is_dir():
        return str(candidate)

    try:
        from faster_whisper.utils import download_model

        return download_model(model_name_or_path, local_files_only=True)
    except Exception:
        pass

    cache_root = Path(os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface"))) / "hub"
    snapshot_root = cache_root / f"models--Systran--faster-whisper-{model_name_or_path}" / "snapshots"
    if snapshot_root.is_dir():
        snapshots = sorted(p for p in snapshot_root.iterdir() if p.is_dir())
        if snapshots:
            return str(snapshots[-1])
    return None


def current_rss_mb() -> float:
    """Return process RSS in MB using psutil when available, with POSIX fallback."""
    try:
        import psutil

        return psutil.Process(os.getpid()).memory_info().rss / 1024**2
    except ImportError:
        import resource

        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return value / 1024 if os.name != "nt" else value / 1024**2


def directory_size_mb(path: Path) -> float | None:
    """Return a model directory/file size, or None for remote/cache-only models."""
    resolved_path = path.resolve()

    if not resolved_path.exists() and not resolved_path.is_symlink():
        return None

    if resolved_path.is_file():
        return round(resolved_path.stat().st_size / 1024**2, 2)

    total_bytes = 0
    for item in resolved_path.rglob("*"):
        try:
            if item.is_file():
                total_bytes += item.stat().st_size
        except (FileNotFoundError, PermissionError):
            continue

    return round(total_bytes / 1024**2, 2)


def run_metadata() -> dict[str, str]:
    """Capture reproducibility metadata without assuming a particular edge board."""
    return {
        "execution_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "processor": platform.processor() or "unknown",
    }


def write_json(path: Path, value: Any) -> None:
    """Write UTF-8 JSON, creating the parent directory when necessary."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def current_timestamp_utc() -> str:
    """Return an ISO-8601 UTC timestamp for the current instant.

    Call this once per engine run (not once for the whole benchmark) when the
    goal is to record *when that engine actually ran*, since engines run
    sequentially and can take very different amounts of time.
    """
    return datetime.now(timezone.utc).isoformat()