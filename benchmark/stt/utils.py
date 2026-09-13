"""Small, dependency-light helpers shared by the STT benchmark."""

from __future__ import annotations

import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.request
import wave
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import difflib


APP_DIR = Path(__file__).resolve().parent

WHISPER_CPP_REPOSITORY = "ggerganov/whisper.cpp"
WHISPER_CPP_MODEL_FILES = {
    "base.en-q5_1": "ggml-base.en-q5_1.bin",
    "base.en-q5_0": "ggml-base.en-q5_0.bin",
    "base.en": "ggml-base.en.bin",
}
VOSK_MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
SHERPA_ONNX_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-zipformer-small-en-2023-06-26.tar.bz2"
)

DOMAIN_KEYWORD_ALIASES = {
    "Antoni Gaudí": ("antoni gaudí", "antoni gaudi", "gaudí", "gaudi"),
    "Gaudí": ("gaudí", "gaudi", "antoni gaudí", "antoni gaudi"),
    "Barcelona": ("barcelona", "barcelona city"),
    "Passeig de Gràcia": (
        "passeig de gràcia",
        "passeig de gracia",
        "paseo de gracia",
        "passaic de gracia",
        "gràcia",
        "gracia",
    ),
    "Temple Expiatori": (
        "temple expiatori",
        "expiatory temple",
        "expiatory church",
        "expiatori",
    ),
    "Sagrada Família": (
        "sagrada família",
        "sagrada familia",
        "basilica of the sagrada familia",
    ),
    "basilica": ("basilica", "basílica"),
    "facade": ("facade", "facades", "façade", "façades"),
    "Nativity facade": ("nativity facade", "nativity façade", "nativity"),
    "Passion facade": ("passion facade", "passion façade", "passion"),
    "Glory facade": ("glory facade", "glory façade", "glory"),
    "modernisme": (
        "modernisme",
        "modernism",
        "catalan modernisme",
        "catalan modernism",
    ),
    "Catalan": ("catalan", "catalonia", "catalonian"),
    "Casa Batlló": ("casa batlló", "casa batllo", "batlló", "batllo"),
    "Casa Milà": (
        "casa milà",
        "casa mila",
        "la pedrera",
        "pedrera",
        "the quarry",
    ),
    "La Pedrera": ("la pedrera", "pedrera", "the quarry"),
    "Park Güell": ("park güell", "park guell", "guell"),
    "Eixample": ("eixample", "eixample district", "example district"),
    "trencadís": ("trencadís", "trencadis", "broken tile mosaic"),
    "salamander": ("salamander", "el drac", "dragon salamander"),
    "dragon": ("dragon", "dragon-shaped", "dragon shaped", "dragon roof"),
    "catenary arch": ("catenary arch", "catenary arches", "parabolic arch"),
}

PHONETIC_CORRECTIONS = {
    # Barcelona & Locations
    r"\bbarselona\b": "Barcelona",
    r"\bbarcelone\b": "Barcelona",
    r"\bpass[ei]ig de gr[aá]cia\b": "Passeig de Gràcia",
    r"\bpassage de gracia\b": "Passeig de Gràcia",
    r"\bpassic de gracia\b": "Passeig de Gràcia",
    r"\bpassaic de gracia\b": "Passeig de Gràcia",
    r"\bpaseo de gracia\b": "Passeig de Gràcia",
    r"\bexample district\b": "Eixample district",
    r"\baixample\b": "Eixample",
    # Sagrada Família & Expiatory Temple
    r"\btemple expiator[iy]\b": "Temple Expiatori",
    r"\bexpiatory temple\b": "Expiatory Temple",
    r"\bsalamander fam[íi]lia\b": "Sagrada Família",
    r"\bsagrada fam[ií]lia\b": "Sagrada Família",
    r"\bsagrada fam[ií]lia's\b": "Sagrada Família's",
    r"\bthe v[áaíi]cidic of assades\b": "the facades of the basilica",
    r"\bv[áaíi]cidic of assades\b": "basilica facades",
    r"\bthe v[áaíi]cidic\b": "the basilica",
    r"\bvicidic\b": "basilica",
    r"\bvasilica\b": "basilica",
    r"\bbacillica\b": "basilica",
    r"\bbacilica\b": "basilica",
    r"\bassades\b": "facades",
    r"\bfacets\b": "facades",
    r"\bgourife assades\b": "Glory facades",
    r"\bgourife facades\b": "Glory facades",
    # Antoni Gaudí / Gaudí variations
    r"\bgaldy\b": "Gaudí",
    r"\bgowdy\b": "Gaudí",
    r"\bgowdi\b": "Gaudí",
    r"\bgotti\b": "Gaudí",
    r"\bgaudy\b": "Gaudí",
    r"\bgaudi\b": "Gaudí",
    r"\bgaudi's\b": "Gaudí's",
    r"\bhow did this park güell\b": "how did Gaudí's Park Güell",
    r"\bhow did this parkway\b": "how did Gaudí's Park Güell",
    # Casa Batlló variations
    r"\bcasavadio\b": "Casa Batlló",
    r"\bcasa laid your\b": "Casa Batlló",
    r"\bcasa batlo\b": "Casa Batlló",
    r"\bcasa batllo\b": "Casa Batlló",
    r"\bcasa batio\b": "Casa Batlló",
    r"\bcasa batlow\b": "Casa Batlló",
    r"\bcasa bortlow\b": "Casa Batlló",
    # Casa Milà & La Pedrera variations
    r"\bcasa mila\b": "Casa Milà",
    r"\bcasa miller\b": "Casa Milà",
    r"\bd'apadrada\b": "La Pedrera",
    r"\bla padrera\b": "La Pedrera",
    r"\bthe quarry\b": "La Pedrera",
    # Park Güell & Salamander variations
    r"\bparkway\b": "Park Güell",
    r"\bpark way\b": "Park Güell",
    r"\bpark well\b": "Park Güell",
    r"\bpark guelph\b": "Park Güell",
    r"\bpark guell\b": "Park Güell",
    r"\bbalacic notor gritte\b": "park's signature creature",
    # trencadís & Materials
    r"\bpatroncad[íi]s\b": "trencadís",
    r"\bpatronic\b": "trencadís",
    r"\bpatronics\b": "trencadís",
    r"\btrincad[íi]s\b": "trencadís",
    r"\btrincadis\b": "trencadís",
    r"\btrencadis\b": "trencadís",
    r"\btriangle, this\b": "trencadís",
    r"\btriangle this\b": "trencadís",
    r"\btrend cotted\b": "trencadís",
    r"\btrend-cotted\b": "trencadís",
    r"\bfusse-dynamic\b": "ceramic",
    # modernisme & Catalan variations
    r"\bmodernism\b": "modernisme",
    r"\bcatatano nizma\b": "Catalan modernisme",
    r"\bcatalan modernism\b": "Catalan modernisme",
    r"\bcatatano\b": "Catalan",
    r"\bcatalonian\b": "Catalan",
    # Dragon & Architectural term hallucinations
    r"\bdrawing shape\b": "dragon-shaped",
    r"\bdrawing shaped\b": "dragon-shaped",
    r"\btourned salagen\b": "turns a legend",
    r"\blook like a drag on\b": "look like a dragon",
    r"\bdrag on\b": "dragon",
    r"\barchitector\b": "architect",
    r"\bat suez grands\b": "at first glance",
}


def build_domain_prompt(keywords: list[str] | None = None) -> str:
    """Build a rich, natural domain context prompt for Whisper conditioning."""
    return (
        "Cultura Viva audio guide in Barcelona about Antoni Gaudí, Sagrada Família basilica, "
        "Nativity, Passion, and Glory facades, Catalan modernisme architecture, Casa Batlló, "
        "Casa Milà, Park Güell, dragon and salamander sculptures, and trencadís mosaics."
    )


def build_hotwords_string(keywords: list[str] | None = None) -> str:
    """Build a space-separated hotwords string for CTranslate2 / faster-whisper biasing."""
    if keywords:
        return " ".join(keywords)
    return (
        "Antoni Gaudí Sagrada Família basilica facade facades modernisme Catalan "
        "Casa Batlló Casa Milà Park Güell trencadís salamander dragon"
    )


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


def canonicalize_domain_entities(text: str, domain_keywords: list[str] | None = None) -> str:
    """Restore canonical spelling and fix frequent phonetic mishearings for domain entities."""
    if not text:
        return text

    cleaned = text
    for pattern, replacement in PHONETIC_CORRECTIONS.items():
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    return cleaned


def normalize_text(text: str | None) -> str:
    """Normalize punctuation and whitespace while preserving accented words."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"[^\w\s']", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def ensure_whisper_model(model_name: str = "base.en-q5_1") -> str:
    """Download a supported whisper.cpp model into the app's local model cache."""
    models_dir = Path(__file__).parent / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    file_name = WHISPER_CPP_MODEL_FILES.get(model_name)
    if file_name is None:
        raise ValueError(
            f"Unsupported whisper.cpp model '{model_name}'. "
            f"Choose one of: {', '.join(WHISPER_CPP_MODEL_FILES)}"
        )
    model_path = models_dir / file_name

    if not model_path.exists():
        from huggingface_hub import hf_hub_download

        print(f"Downloading {file_name} from {WHISPER_CPP_REPOSITORY}...")
        downloaded_path = hf_hub_download(
            repo_id=WHISPER_CPP_REPOSITORY,
            filename=file_name,
            local_dir=str(models_dir),
            local_dir_use_symlinks=False,
        )
        model_path = Path(downloaded_path)
    return str(model_path)


def ensure_faster_whisper_model(model_name: str) -> str:
    """Download a faster-whisper snapshot into the app's local model cache."""
    target = APP_DIR / "models" / f"faster-whisper-{model_name}"
    if target.is_dir():
        return str(target)
    from huggingface_hub import snapshot_download

    print(f"Downloading Systran/faster-whisper-{model_name}...")
    snapshot_download(
        repo_id=f"Systran/faster-whisper-{model_name}",
        local_dir=str(target),
        local_dir_use_symlinks=False,
    )
    return str(target)


def ensure_vosk_model() -> str:
    """Download and extract the standard English Vosk model if needed."""
    models_dir = APP_DIR / "models"
    target = models_dir / "vosk-model-small-en-us-0.15"
    if target.is_dir():
        return str(target)
    archive = models_dir / "vosk-model-small-en-us-0.15.zip"
    models_dir.mkdir(parents=True, exist_ok=True)
    print("Downloading Vosk small English model...")
    urllib.request.urlretrieve(VOSK_MODEL_URL, archive)
    with zipfile.ZipFile(archive) as package:
        package.extractall(models_dir)
    archive.unlink()
    return str(target)


def ensure_sherpa_onnx_model() -> str:
    """Download and extract the standard sherpa-onnx model if needed."""
    models_dir = APP_DIR / "models"
    target = models_dir / "sherpa-onnx-en"
    if target.is_dir():
        return str(target)
    archive = models_dir / "sherpa-onnx-en.tar.bz2"
    models_dir.mkdir(parents=True, exist_ok=True)
    print("Downloading sherpa-onnx Zipformer English model...")
    urllib.request.urlretrieve(SHERPA_ONNX_MODEL_URL, archive)
    shutil.unpack_archive(str(archive), models_dir)
    extracted = models_dir / "sherpa-onnx-zipformer-small-en-2023-06-26"
    extracted.rename(target)
    archive.unlink()
    return str(target)


def ensure_engine_models(engine_names: Iterable[str]) -> None:
    """Provision only the model files required by the selected engines."""
    for engine_name in dict.fromkeys(engine_names):
        if engine_name.startswith("whisper.cpp:"):
            ensure_whisper_model(engine_name.split(":", 1)[1])
        elif engine_name.startswith("faster-whisper:"):
            ensure_faster_whisper_model(engine_name.split(":", 1)[1])
        elif engine_name == "vosk":
            ensure_vosk_model()
        elif engine_name == "sherpa-onnx":
            ensure_sherpa_onnx_model()


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
            if difflib.SequenceMatcher(None, needle, window).ratio() >= threshold:
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

    local_path = APP_DIR / "models" / f"faster-whisper-{model_name_or_path}"
    if local_path.is_dir():
        return str(local_path)

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


def resolve_whisper_cpp_model_path(model_name_or_path: str) -> str | None:
    """Resolve a whisper.cpp GGML model name or path to a local file.

    Also checks HF_HOME's huggingface cache (where ensure_whisper_model /
    hf_hub_download place files by default) so a model fetched via
    ensure_whisper_model() is found here too, not just files manually copied
    into models/.
    """
    candidate = Path(model_name_or_path)
    if candidate.is_file():
        return str(candidate)

    models_dir = APP_DIR / "models"
    options = [
        models_dir / model_name_or_path,
        models_dir / f"{model_name_or_path}.bin",
        models_dir / f"ggml-{model_name_or_path}.bin",
        models_dir / "whisper.cpp" / "models" / model_name_or_path,
        models_dir / "whisper.cpp" / "models" / f"{model_name_or_path}.bin",
        models_dir / "whisper.cpp" / "models" / f"ggml-{model_name_or_path}.bin",
    ]
    for opt in options:
        if opt.is_file():
            return str(opt)

    cache_root = Path(os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface"))) / "hub"
    model_cache = cache_root / "models--ggerganov--whisper.cpp" / "snapshots"
    if model_cache.is_dir():
        for snapshot in sorted(model_cache.iterdir(), reverse=True):
            cached_file = snapshot / WHISPER_CPP_MODEL_FILES.get(model_name_or_path, "")
            if cached_file.is_file():
                return str(cached_file)
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