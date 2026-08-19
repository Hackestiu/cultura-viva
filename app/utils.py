"""Small, dependency-light helpers shared by the STT benchmark."""

from __future__ import annotations

import csv
import json
import math
import os
import platform
import re
import sys
import unicodedata
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


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


def normalize_text(text: str) -> str:
    """Normalize punctuation and whitespace while preserving accented words."""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"[^\w\s']", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


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


def find_domain_keywords(text: str) -> list[str]:
    """Return canonical Cultura Viva keywords explicitly present in text."""
    normalized = normalize_text(text)
    return [
        keyword
        for keyword, aliases in DOMAIN_KEYWORD_ALIASES.items()
        if any(alias in normalized for alias in aliases)
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
    if not path.exists():
        return None
    if path.is_file():
        return round(path.stat().st_size / 1024**2, 2)
    return round(sum(item.stat().st_size for item in path.rglob("*") if item.is_file()) / 1024**2, 2)


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


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    """Write a stable CSV report for spreadsheet and embedded-tool workflows."""
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)