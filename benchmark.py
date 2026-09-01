"""Pluggable, resource-aware benchmark for English edge STT engines."""

from __future__ import annotations

import gc
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from tqdm import tqdm

from utils import (
    DOMAIN_KEYWORD_ALIASES,
    build_domain_prompt,
    build_sherpa_hotwords_file,
    character_error_rate,
    canonicalize_domain_entities,
    current_rss_mb,
    current_timestamp_utc,
    directory_size_mb,
    ensure_16k_mono_pcm16,
    ensure_engine_models,
    ensure_whisper_model,
    find_domain_keywords,
    keyword_spotting_accuracy,
    resolve_faster_whisper_path,
    resolve_whisper_cpp_model_path,
    run_metadata,
    wav_duration_seconds,
    word_error_rate,
    write_json,
    build_hotwords_string
)


APP_DIR = Path(__file__).resolve().parent
CACHE_DIR = APP_DIR / "cache"
NORMALIZED_AUDIO_DIR = CACHE_DIR / "normalized_audio"


class Recognizer(Protocol):
    """Minimal interface implemented by each optional STT backend."""

    domain_bias_applied: bool
    model_size_mb: float | None

    def transcribe(self, audio_path: Path, language: str) -> str: ...


@dataclass(frozen=True)
class DatasetItem:
    filename: str
    language: str
    reference: str
    keywords: tuple[str, ...] = ()


class FasterWhisperRecognizer:
    def __init__(
        self,
        model_name: str,
        device: str,
        compute_type: str,
        beam_size: int = 1,
        initial_prompt: str | None = None,
        hotwords: str | None = None,
        cpu_threads: int | None = None,
    ) -> None:
        from faster_whisper import WhisperModel

        local_path = resolve_faster_whisper_path(model_name)
        threads = cpu_threads or 4
        
        self.model = WhisperModel(
            local_path or model_name,
            device=device,
            compute_type=compute_type, 
            cpu_threads=threads,
        )
        self.model_size_mb = directory_size_mb(Path(local_path)) if local_path else None

        self.beam_size = beam_size
        self.initial_prompt = initial_prompt
        self.hotwords = hotwords
        self.domain_bias_applied = (initial_prompt is not None) or (hotwords is not None)

    def transcribe(self, audio_path: Path, language: str) -> str:
        segments, _ = self.model.transcribe(
            str(audio_path),
            language=language,
            beam_size=self.beam_size,
            best_of=1,
            temperature=0.0,
            suppress_blank=True,
            without_timestamps=True,
            vad_filter=True, 
            vad_parameters=dict(min_silence_duration_ms=500),
            condition_on_previous_text=False,
            initial_prompt=self.initial_prompt,
            hotwords=self.hotwords,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()


class WhisperCppRecognizer:
    """whisper.cpp adapter running natively via pywhispercpp Python bindings with ARM NEON SIMD."""

    def __init__(
        self,
        model_name: str,
        cpu_threads: int | None = None,
        beam_size: int = 1,
        initial_prompt: str | None = None,
    ) -> None:
        from pywhispercpp.model import Model

        resolved_model = resolve_whisper_cpp_model_path(model_name)
        if resolved_model is None:
            resolved_model = ensure_whisper_model(model_name)
        model_target = resolved_model

        self.cpu_threads = cpu_threads or 2

        # Native C++ model load through the Python wrapper.
        self.model = Model(
            model_target,
            n_threads=self.cpu_threads,
            context_params={"use_gpu": False},
            print_progress=False,
            print_realtime=False,
            print_timestamps=False,
        )

        self.model_path = resolved_model
        self.model_size_mb = directory_size_mb(Path(resolved_model)) if resolved_model else None
        self.beam_size = beam_size
        self.initial_prompt = initial_prompt
        self.domain_bias_applied = initial_prompt is not None

    def transcribe(self, audio_path: Path, language: str) -> str:
        import _pywhispercpp

        kwargs: dict[str, Any] = {
            "language": language,
            "no_context": True,
            "no_timestamps": True,
            "suppress_blank": True,
            "temperature": 0.0,
            "carry_initial_prompt": True,
            "strategy": (
                _pywhispercpp.WHISPER_SAMPLING_BEAM_SEARCH
                if self.beam_size > 1
                else _pywhispercpp.WHISPER_SAMPLING_GREEDY
            ),
        }
        if self.beam_size > 1:
            kwargs["beam_search"] = {"beam_size": self.beam_size}
        else:
            kwargs["greedy"] = {"best_of": 1}
        if self.initial_prompt:
            kwargs["initial_prompt"] = self.initial_prompt

        # Direct transcription, no subprocess/CLI round-trip.
        segments = self.model.transcribe(str(audio_path), **kwargs)

        return " ".join(segment.text.strip() for segment in segments).strip()



class VoskRecognizer:
    """Vosk adapter using a local model directory and the standard WAV reader.

    Vosk's runtime grammar mechanism restricts recognition to a fixed closed
    vocabulary rather than softly biasing an open one (see alphacep/vosk-api
    issue #878), so it has no equivalent to faster-whisper's initial_prompt or
    sherpa-onnx's hotwords and always runs with domain_bias_applied = False.
    """

    def __init__(self, model_path: str) -> None:
        from vosk import KaldiRecognizer, Model

        self._recognizer_type = KaldiRecognizer
        self.model = Model(model_path)
        self.domain_bias_applied = False
        self.model_size_mb = directory_size_mb(Path(model_path))

    def transcribe(self, audio_path: Path, language: str) -> str:
        import wave

        with wave.open(str(audio_path), "rb") as audio:
            recognizer = self._recognizer_type(self.model, audio.getframerate())
            while chunk := audio.readframes(4000):
                recognizer.AcceptWaveform(chunk)
            return json.loads(recognizer.FinalResult()).get("text", "")


class SherpaOnnxRecognizer:
    """sherpa-onnx adapter; configure model files through SHERPA_ONNX_MODEL_DIR.

    Only sherpa-onnx's transducer models support hotwords/contextual biasing;
    the decoding method must also be modified_beam_search (k2-fsa hotwords
    docs). The Whisper-export branch below therefore always runs
    greedy_search with domain_bias_applied = False, regardless of
    --enable-domain-bias. The transducer branch uses modified_beam_search
    with a beam width matched to faster-whisper's --whisper-beam-size, and
    applies a hotwords file built from the same keyword list
    (utils.DOMAIN_KEYWORD_ALIASES) that faster-whisper's initial_prompt is
    built from, when one is supplied.

    Both branches assume 16 kHz mono input and do not resample — see
    utils.ensure_16k_mono_pcm16, which the benchmark loop now runs every file
    through before it reaches transcribe().
    """

    def __init__(
        self,
        model_dir: str,
        beam_size: int = 5,
        hotwords_file: Path | None = None,
        hotwords_score: float = 2.0,
    ) -> None:
        import sherpa_onnx

        model = Path(model_dir)
        self.model_size_mb = directory_size_mb(model)
        whisper_files = sorted(model.glob("*-encoder.onnx"))
        if whisper_files:
            encoder = whisper_files[0]
            decoder = model / f"{encoder.name.removesuffix('-encoder.onnx')}-decoder.onnx"
            tokens = model / f"{encoder.name.removesuffix('-encoder.onnx')}-tokens.txt"
            missing = [str(path.name) for path in (decoder, tokens) if not path.is_file()]
            if missing:
                raise FileNotFoundError(f"sherpa-onnx Whisper model is missing: {', '.join(missing)}")
            self.recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
                encoder=str(encoder),
                decoder=str(decoder),
                tokens=str(tokens),
                language="en",
                task="transcribe",
                decoding_method="greedy_search",
            )
            self.domain_bias_applied = False
            return

        required_files = ("encoder.onnx", "decoder.onnx", "joiner.onnx", "tokens.txt")
        missing = [name for name in required_files if not (model / name).is_file()]
        if missing:
            raise FileNotFoundError(
                f"sherpa-onnx model directory needs Whisper *-encoder.onnx files or: {', '.join(required_files)}"
            )
        kwargs: dict[str, Any] = dict(
            encoder=str(model / "encoder.onnx"),
            decoder=str(model / "decoder.onnx"),
            joiner=str(model / "joiner.onnx"),
            tokens=str(model / "tokens.txt"),
            sample_rate=16000,
            feature_dim=80,
            decoding_method="modified_beam_search",
            max_active_paths=beam_size,
        )
        if hotwords_file is not None:
            kwargs["hotwords_file"] = str(hotwords_file)
            kwargs["hotwords_score"] = hotwords_score
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(**kwargs)
        self.domain_bias_applied = hotwords_file is not None

    def transcribe(self, audio_path: Path, language: str) -> str:
        import soundfile as sf

        samples, sample_rate = sf.read(str(audio_path), dtype="float32")
        stream = self.recognizer.create_stream()
        stream.accept_waveform(sample_rate, samples)
        self.recognizer.decode_stream(stream)
        return stream.result.text.strip()


def load_manifest(path: Path) -> list[DatasetItem]:
    """Load the JSON dataset manifest."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = [
        DatasetItem(
            item["filename"],
            item["language"],
            item["text"],
            tuple(item.get("keywords") or find_domain_keywords(item["text"])),
        )
        for item in raw
    ]
    non_english = [item.filename for item in items if item.language != "en"]
    if non_english:
        raise ValueError(f"English benchmark received non-English files: {non_english}")
    return items


def build_recognizer(name: str, args: Any) -> Recognizer:
    """Create one backend lazily so missing optional dependencies are isolated."""
    keywords = list(DOMAIN_KEYWORD_ALIASES.keys())
    domain_prompt = build_domain_prompt(keywords)
    hotwords_str = build_hotwords_string(keywords)

    if name.startswith("whisper.cpp:"):
        model_name = name.split(":", 1)[1]
        initial_prompt = getattr(args, "whisper_initial_prompt", None) or domain_prompt
        return WhisperCppRecognizer(
            model_name=model_name,
            cpu_threads=getattr(args, "cpu_threads", 4),
            beam_size=getattr(args, "whisper_beam_size", 1),
            initial_prompt=initial_prompt,
        )
    if name.startswith("faster-whisper:"):
        initial_prompt = getattr(args, "whisper_initial_prompt", None) or domain_prompt
        return FasterWhisperRecognizer(
            name.split(":", 1)[1],
            args.device,
            args.compute_type,
            beam_size=getattr(args, "whisper_beam_size", 1),
            initial_prompt=initial_prompt,
            hotwords=hotwords_str,
            cpu_threads=getattr(args, "cpu_threads", None),
        )
    if name == "vosk":
        model_path = Path(os.environ.get(
            "VOSK_MODEL_DIR", str(APP_DIR / "models" / "vosk-model-small-en-us-0.15")
        ))
        if not (model_path / "am").is_dir() or not (model_path / "conf").is_dir():
            raise FileNotFoundError(
                f"Vosk model directory is incomplete: {model_path}. "
                "Extract the complete vosk-model-small-en-us-0.15 folder."
            )
        return VoskRecognizer(str(model_path))
    if name == "sherpa-onnx":
        model_path = Path(os.environ.get(
            "SHERPA_ONNX_MODEL_DIR", str(APP_DIR / "models" / "sherpa-onnx-en")
        ))
        if not model_path.is_dir():
            raise FileNotFoundError(f"sherpa-onnx model directory not found: {model_path}")
        hotwords_file = build_sherpa_hotwords_file(
            DOMAIN_KEYWORD_ALIASES.keys(),
            model_path,
            CACHE_DIR / "cultura_viva_hotwords.txt",
        )
        if hotwords_file is None:
            print(
                f"[INFO] sherpa-onnx: no usable bpe.model in {model_path} "
                "(Whisper models never support hotwords; transducer models need "
                "one bundled). Running this engine without domain bias — see the "
                "README for the recommended transducer model."
            )
        return SherpaOnnxRecognizer(
            str(model_path), beam_size=args.whisper_beam_size, hotwords_file=hotwords_file
        )
    raise ValueError(f"Unknown engine: {name}")


def measure_transcription(recognizer: Recognizer, audio_path: Path, language: str) -> tuple[str, float, float, str]:
    """Transcribe while sampling process RSS, without retaining audio in memory."""
    stop = threading.Event()
    peak = [current_rss_mb()]

    def sample_memory() -> None:
        while not stop.wait(0.05):
            peak[0] = max(peak[0], current_rss_mb())

    sampler = threading.Thread(target=sample_memory, daemon=True)
    sampler.start()
    started = time.perf_counter()
    try:
        transcription = recognizer.transcribe(audio_path, language)
        error_message = ""
    except Exception as error:  # Keep one bad file from losing the report.
        transcription = ""
        error_message = f"{type(error).__name__}: {error}"
    elapsed = time.perf_counter() - started
    stop.set()
    sampler.join()
    return transcription, elapsed, peak[0], error_message


def run_benchmark(args: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Run all requested engines; return per-utterance measurements and, for
    each engine, the real UTC timestamp of when that engine started running.
    Logs a per-utterance wandb.Table when args.wandb is set.
    """
    use_wandb = getattr(args, "wandb", False)
    wandb_table = None
    if use_wandb:
        import wandb

        wandb_table = wandb.Table(columns=[
            "engine", "filename", "language", "ground_truth", "raw_transcription",
            "transcription", "domain_bias_applied", "wer", "cer",
            "keyword_spotting_accuracy", "inference_latency_ms", "rtf",
            "peak_ram_mb", "model_size_mb", "error",
        ])

    dataset = load_manifest(Path(args.manifest))
    audio_dir = Path(args.audio_dir)
    results: list[dict[str, Any]] = []
    engine_started_at: dict[str, str] = {}
    engines = list(args.engines)

    for engine_idx, engine_name in enumerate(engines, start=1):
        try:
            recognizer = build_recognizer(engine_name, args)
        except Exception as error:
            tqdm.write(f"[SKIP] {engine_name}: {error}")
            continue
        engine_started_at[engine_name] = current_timestamp_utc()
        engine_model_size_mb = getattr(recognizer, "model_size_mb", None)

        pbar = tqdm(
            dataset,
            desc=f"[{engine_idx}/{len(engines)}] {engine_name}",
            unit="audio",
            dynamic_ncols=True,
            leave=True,
        )
        for item in pbar:
            raw_audio_path = audio_dir / item.filename
            if not raw_audio_path.exists():
                tqdm.write(f"[SKIP] missing audio: {raw_audio_path}")
                continue
            # Normalize to 16 kHz mono PCM16 before any engine sees it. The
            # synthetic dataset already comes out this way, but a
            # human-recorded dataset dropped into data_audio/recorded/ may not
            # — see utils.ensure_16k_mono_pcm16 for why that silently wrecks
            # sherpa-onnx accuracy in particular.
            audio_path = ensure_16k_mono_pcm16(raw_audio_path, NORMALIZED_AUDIO_DIR)
            duration = wav_duration_seconds(audio_path)
            raw_transcription, elapsed, peak_ram_mb, error_message = measure_transcription(
                recognizer, audio_path, item.language
            )
            transcription = canonicalize_domain_entities(raw_transcription)
            wer_val = word_error_rate(item.reference, transcription)
            cer_val = character_error_rate(item.reference, transcription)
            kw_acc = (
                keyword_spotting_accuracy(item.reference, transcription, item.keywords)
                if item.keywords
                else None
            )
            rtf_val = (elapsed / duration) if duration else None

            row = {
                "filename": item.filename,
                "language": item.language,
                "engine": engine_name,
                "ground_truth": item.reference,
                "raw_transcription": raw_transcription,
                "transcription": transcription,
                "domain_bias_applied": recognizer.domain_bias_applied,
                "inference_time_sec": round(elapsed, 4),
                "audio_duration_sec": round(duration, 4),
                "rtf": round(rtf_val, 4) if rtf_val is not None else None,
                "wer": round(wer_val, 4),
                "cer": round(cer_val, 4),
                "keyword_spotting_accuracy": round(kw_acc, 4) if kw_acc is not None else None,
                "inference_latency_ms": round(elapsed * 1000, 2),
                "peak_ram_mb": round(peak_ram_mb, 2),
                "model_size_mb": engine_model_size_mb,
                "domain_keywords": list(item.keywords),
                "error": error_message,
            }
            results.append(row)

            # Update progress bar with live metrics
            postfix = {
                "file": item.filename,
                "WER": f"{wer_val:.1%}",
                "RTF": f"{rtf_val:.2f}x" if rtf_val is not None else "N/A",
                "RAM": f"{peak_ram_mb:.0f}MB",
            }
            if error_message:
                postfix["status"] = "ERR"
            pbar.set_postfix(postfix)

            if wandb_table is not None:
                wandb_table.add_data(
                    row["engine"], row["filename"], row["language"], row["ground_truth"],
                    row["raw_transcription"], row["transcription"], row["domain_bias_applied"],
                    row["wer"], row["cer"], row["keyword_spotting_accuracy"],
                    row["inference_latency_ms"], row["rtf"], row["peak_ram_mb"],
                    row["model_size_mb"], row["error"],
                )
        del recognizer
        gc.collect()

    if wandb_table is not None:
        import wandb

        wandb.log({"predictions": wandb_table})

    return results, engine_started_at


def model_size_mb(engine_name: str) -> float | None:
    """Measure local model assets for an engine name alone (no live recognizer).

    Used only as a fallback in export_reports() for legacy result rows that
    predate the model_size_mb field being captured directly on each
    recognizer. New runs populate model_size_mb on every row already, so this
    function is not on the hot path anymore.
    """
    if engine_name.startswith("whisper.cpp:"):
        local_path = resolve_whisper_cpp_model_path(engine_name.split(":", 1)[1])
        return directory_size_mb(Path(local_path)) if local_path else None
    if engine_name.startswith("faster-whisper:"):
        local_path = resolve_faster_whisper_path(engine_name.split(":", 1)[1])
        return directory_size_mb(Path(local_path)) if local_path else None
    if engine_name == "vosk":
        path = os.environ.get("VOSK_MODEL_DIR", str(APP_DIR / "models" / "vosk-model-small-en-us-0.15"))
        return directory_size_mb(Path(path))
    if engine_name == "sherpa-onnx":
        path = os.environ.get("SHERPA_ONNX_MODEL_DIR", str(APP_DIR / "models" / "sherpa-onnx-en"))
        return directory_size_mb(Path(path))
    return None


def build_summary(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate per-utterance rows into one row per engine.

    BUG THIS FIXES: export_plots() expects exactly this shape (avg_wer,
    avg_cer, max_peak_ram_mb, model_size_mb, ...) but nothing in the pipeline
    ever built it — export_reports() only ever grouped raw per-utterance rows
    for the JSON prediction files. export_plots() was consequently dead code:
    it was never called, and even if it had been, it had no valid input to
    call it with. This is the real reason plots (including the Whisper
    model-size bars) never rendered — the plotting step never ran at all.
    """
    by_engine: dict[str, list[dict[str, Any]]] = {}
    for row in results:
        by_engine.setdefault(row["engine"], []).append(row)

    summary = []
    for engine, rows in by_engine.items():
        valid_wer = [row["wer"] for row in rows if row["wer"] == row["wer"]]  # drop NaN
        valid_cer = [row["cer"] for row in rows if row["cer"] == row["cer"]]
        valid_kw = [
            row["keyword_spotting_accuracy"] for row in rows
            if row["keyword_spotting_accuracy"] is not None and row["keyword_spotting_accuracy"] == row["keyword_spotting_accuracy"]
        ]
        summary.append({
            "engine": engine,
            "avg_wer": sum(valid_wer) / len(valid_wer) if valid_wer else None,
            "avg_cer": sum(valid_cer) / len(valid_cer) if valid_cer else None,
            "avg_keyword_spotting_accuracy": sum(valid_kw) / len(valid_kw) if valid_kw else None,
            "avg_inference_time_sec": sum(row["inference_time_sec"] for row in rows) / len(rows),
            "avg_inference_latency_ms": sum(row["inference_latency_ms"] for row in rows) / len(rows),
            "max_peak_ram_mb": max(row["peak_ram_mb"] for row in rows),
            "model_size_mb": rows[0].get("model_size_mb"),
            "domain_bias_applied": rows[0].get("domain_bias_applied", False),
            "num_utterances": len(rows),
        })
    return summary


def export_reports(
    results: list[dict[str, Any]],
    output_dir: Path,
    engine_started_at: dict[str, str] | None = None,
    use_wandb: bool = False,
) -> None:
    """Write per-engine JSON prediction reports, a per-engine summary.json, and
    comparison plots. When use_wandb is set, also logs per-engine aggregate
    metrics and uploads the reports as a wandb artifact.
    """
    if not results:
        print("[WARN] no results to export.")
        return

    engine_started_at = engine_started_at or {}
    model_size_cache: dict[str, float | None] = {}
    normalized_results = []
    for source in results:
        result = dict(source)
        keywords = result.get("domain_keywords") or find_domain_keywords(result["ground_truth"])
        result.setdefault("cer", round(character_error_rate(result["ground_truth"], result["transcription"]), 4))
        result.setdefault(
            "keyword_spotting_accuracy",
            round(keyword_spotting_accuracy(result["ground_truth"], result["transcription"], keywords), 4),
        )
        result.setdefault("inference_latency_ms", round(result["inference_time_sec"] * 1000, 2))
        result.setdefault("domain_bias_applied", False)
        if "model_size_mb" not in result:
            engine = result["engine"]
            if engine not in model_size_cache:
                model_size_cache[engine] = model_size_mb(engine)
            result["model_size_mb"] = model_size_cache[engine]
        result.setdefault("domain_keywords", keywords)
        normalized_results.append(result)
    results = normalized_results
    host_metadata = run_metadata()
    by_engine: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        by_engine.setdefault(result["engine"], []).append(result)
    predictions_dir = output_dir / "predictions"
    for engine, rows in by_engine.items():
        filename = re.sub(r"[^A-Za-z0-9_.-]+", "_", engine).strip("_")
        metadata = {
            **host_metadata,
            "execution_timestamp_utc": engine_started_at.get(engine, host_metadata["execution_timestamp_utc"]),
            "model_name": engine,
        }
        write_json(predictions_dir / f"{filename}.json", {
            "schema_version": 2,
            "metadata": metadata,
            "predictions": rows,
        })

    summary = build_summary(results)
    write_json(output_dir / "summary.json", summary)
    export_plots(summary, output_dir / "plots")
    print(f"Wrote summary for {len(summary)} engine(s) and plots to {output_dir / 'plots'}")

    if use_wandb:
        import wandb

        for engine, rows in by_engine.items():
            valid_wer = [row["wer"] for row in rows if row["wer"] == row["wer"]]  # drop NaN
            valid_cer = [row["cer"] for row in rows if row["cer"] == row["cer"]]
            valid_kw = [row["keyword_spotting_accuracy"] for row in rows if row["keyword_spotting_accuracy"] is not None]
            wandb.log({
                f"{engine}/avg_wer": sum(valid_wer) / len(valid_wer) if valid_wer else None,
                f"{engine}/avg_cer": sum(valid_cer) / len(valid_cer) if valid_cer else None,
                f"{engine}/avg_keyword_spotting_accuracy": sum(valid_kw) / len(valid_kw) if valid_kw else None,
                f"{engine}/avg_inference_latency_ms": sum(row["inference_latency_ms"] for row in rows) / len(rows),
                f"{engine}/max_peak_ram_mb": max(row["peak_ram_mb"] for row in rows),
                f"{engine}/model_size_mb": rows[0]["model_size_mb"],
                f"{engine}/domain_bias_applied": rows[0]["domain_bias_applied"],
            })

        artifact = wandb.Artifact("predictions", type="results")
        artifact.add_dir(str(predictions_dir))
        hotwords_cache = CACHE_DIR / "cultura_viva_hotwords.txt"
        if hotwords_cache.is_file():
            artifact.add_file(str(hotwords_cache))
        wandb.log_artifact(artifact)


def export_plots(summary: list[dict[str, Any]], plots_dir: Path) -> None:
    """Write comparison plots from the aggregated per-engine summary."""
    if not summary:
        print("[WARN] no summary rows to plot.")
        return

    plots_dir.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        print(f"[WARN] plots skipped; install matplotlib: {error}")
        return

    def safe(values: list[float | None]) -> list[float]:
        # None (e.g. an engine that produced no valid WER at all) used to be
        # passed straight into matplotlib's bar(), which raises and aborts
        # every plot for every engine, not just the affected one. Coercing to
        # 0 keeps a single failed engine from taking the whole report down.
        return [value if value is not None else 0 for value in values]

    labels = [row["engine"] for row in summary]
    positions = list(range(len(labels)))
    figures = (
        (
            "model_quality.png",
            (
                (safe([row["avg_wer"] for row in summary]), "WER"),
                (safe([row["avg_cer"] for row in summary]), "CER"),
                (safe([row["avg_keyword_spotting_accuracy"] for row in summary]), "Keyword accuracy"),
            ),
            "Recognition quality by engine",
            "Score",
        ),
        (
            "resource_usage.png",
            (
                (safe([row["max_peak_ram_mb"] for row in summary]), "Peak RAM (MB)"),
                (safe([row["model_size_mb"] for row in summary]), "Model size (MB)"),
            ),
            "Resource usage by engine",
            "MB",
        ),
        (
            "avg_inference_time.png",
            ((safe([row["avg_inference_time_sec"] for row in summary]), "Average inference time"),),
            "Average inference time by engine",
            "Seconds",
        ),
        (
            "avg_wer.png",
            ((safe([row["avg_wer"] for row in summary]), "Average WER"),),
            "Average WER by engine",
            "WER",
        ),
    )
    for filename, series, title, axis_label in figures:
        figure, axis = plt.subplots(figsize=(max(8, len(labels) * 1.5), 5))
        width = 0.8 / len(series)
        for index, (values, label) in enumerate(series):
            offset = (index - (len(series) - 1) / 2) * width
            axis.bar([position + offset for position in positions], values, width, label=label)
        axis.set_xticks(positions, labels, rotation=25, ha="right")
        axis.set_ylabel(axis_label)
        axis.set_title(title)
        axis.legend()
        figure.tight_layout()
        figure.savefig(plots_dir / filename, dpi=150)
        plt.close(figure)

    figure, axis = plt.subplots(figsize=(8, 5))
    for row in summary:
        axis.scatter(
            row["avg_inference_latency_ms"],
            row["avg_wer"] if row["avg_wer"] is not None else 0,
            s=100,
            label=row["engine"],
        )
    axis.set_xlabel("Average inference latency (ms)")
    axis.set_ylabel("Average WER, lower is better")
    axis.set_title("Accuracy versus latency")
    axis.legend(loc="upper left")
    figure.tight_layout()
    figure.savefig(plots_dir / "accuracy_latency.png", dpi=150)
    plt.close(figure)


if __name__ == "__main__":
    from main import main

    main()