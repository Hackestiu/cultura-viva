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

from utils import (
    character_error_rate,
    current_rss_mb,
    directory_size_mb,
    find_domain_keywords,
    keyword_spotting_accuracy,
    run_metadata,
    wav_duration_seconds,
    word_error_rate,
    write_json,
)


APP_DIR = Path(__file__).resolve().parent


class Recognizer(Protocol):
    """Minimal interface implemented by each optional STT backend."""

    def transcribe(self, audio_path: Path, language: str) -> str: ...


@dataclass(frozen=True)
class DatasetItem:
    filename: str
    language: str
    reference: str
    keywords: tuple[str, ...] = ()


class FasterWhisperRecognizer:
    """faster-whisper adapter; CPU INT8 is the default for UNO Q."""

    def __init__(self, model_name: str, device: str, compute_type: str) -> None:
        from faster_whisper import WhisperModel

        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)

    def transcribe(self, audio_path: Path, language: str) -> str:
        segments, _ = self.model.transcribe(
            str(audio_path), language=language, beam_size=1, vad_filter=True
        )
        return " ".join(segment.text.strip() for segment in segments).strip()


class VoskRecognizer:
    """Vosk adapter using a local model directory and the standard WAV reader."""

    def __init__(self, model_path: str) -> None:
        from vosk import KaldiRecognizer, Model

        self._recognizer_type = KaldiRecognizer
        self.model = Model(model_path)

    def transcribe(self, audio_path: Path, language: str) -> str:
        import wave

        with wave.open(str(audio_path), "rb") as audio:
            recognizer = self._recognizer_type(self.model, audio.getframerate())
            while chunk := audio.readframes(4000):
                recognizer.AcceptWaveform(chunk)
            return json.loads(recognizer.FinalResult()).get("text", "")


class SherpaOnnxRecognizer:
    """sherpa-onnx adapter; configure model files through SHERPA_ONNX_MODEL_DIR."""

    def __init__(self, model_dir: str) -> None:
        import sherpa_onnx

        model = Path(model_dir)
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
            return

        required_files = ("encoder.onnx", "decoder.onnx", "joiner.onnx", "tokens.txt")
        missing = [name for name in required_files if not (model / name).is_file()]
        if missing:
            raise FileNotFoundError(
                f"sherpa-onnx model directory needs Whisper *-encoder.onnx files or: {', '.join(required_files)}"
            )
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(model / "encoder.onnx"),
            decoder=str(model / "decoder.onnx"),
            joiner=str(model / "joiner.onnx"),
            tokens=str(model / "tokens.txt"),
            sample_rate=16000,
            feature_dim=80,
            decoding_method="greedy_search",
        )

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
            tuple(item.get("keywords", find_domain_keywords(item["text"]))),
        )
        for item in raw
    ]
    non_english = [item.filename for item in items if item.language != "en"]
    if non_english:
        raise ValueError(f"English benchmark received non-English files: {non_english}")
    return items


def build_recognizer(name: str, args: Any) -> Recognizer:
    """Create one backend lazily so missing optional dependencies are isolated."""
    if name.startswith("faster-whisper:"):
        return FasterWhisperRecognizer(name.split(":", 1)[1], args.device, args.compute_type)
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
        return SherpaOnnxRecognizer(str(model_path))
    raise ValueError(f"Unknown engine: {name}")


def measure_transcription(recognizer: Recognizer, audio_path: Path, language: str) -> tuple[str, float, float, str]:
    """Transcribe while sampling process RSS, without retaining audio in memory."""
    stop = threading.Event()
    peak = [current_rss_mb()]

    def sample_memory() -> None:
        while not stop.wait(0.01):
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


def run_benchmark(args: Any) -> list[dict[str, Any]]:
    """Run all requested engines and return per-utterance measurements."""
    dataset = load_manifest(Path(args.manifest))
    audio_dir = Path(args.audio_dir)
    results: list[dict[str, Any]] = []
    for engine_name in args.engines:
        try:
            recognizer = build_recognizer(engine_name, args)
        except Exception as error:
            print(f"[SKIP] {engine_name}: {error}")
            continue
        for item in dataset:
            audio_path = audio_dir / item.filename
            if not audio_path.exists():
                print(f"[SKIP] missing audio: {audio_path}")
                continue
            duration = wav_duration_seconds(audio_path)
            transcription, elapsed, peak_ram_mb, error_message = measure_transcription(
                recognizer, audio_path, item.language
            )
            results.append({
                "filename": item.filename,
                "language": item.language,
                "engine": engine_name,
                "ground_truth": item.reference,
                "transcription": transcription,
                "inference_time_sec": round(elapsed, 4),
                "audio_duration_sec": round(duration, 4),
                "rtf": round(elapsed / duration, 4) if duration else None,
                "wer": round(word_error_rate(item.reference, transcription), 4),
                "cer": round(character_error_rate(item.reference, transcription), 4),
                "keyword_spotting_accuracy": round(
                    keyword_spotting_accuracy(item.reference, transcription, item.keywords), 4
                ) if item.keywords else None,
                "inference_latency_ms": round(elapsed * 1000, 2),
                "peak_ram_mb": round(peak_ram_mb, 2),
                "model_size_mb": model_size_mb(engine_name),
                "domain_keywords": list(item.keywords),
                "error": error_message,
            })
        del recognizer
        gc.collect()
    return results


def model_size_mb(engine_name: str) -> float | None:
    """Measure local model assets when the configured engine has a local path."""
    if engine_name.startswith("faster-whisper:"):
        return directory_size_mb(Path(engine_name.split(":", 1)[1]))
    if engine_name == "vosk":
        path = os.environ.get("VOSK_MODEL_DIR", str(APP_DIR / "models" / "vosk-model-small-en-us-0.15"))
        return directory_size_mb(Path(path))
    if engine_name == "sherpa-onnx":
        path = os.environ.get("SHERPA_ONNX_MODEL_DIR", str(APP_DIR / "models" / "sherpa-onnx-en"))
        return directory_size_mb(Path(path))
    return None


def export_reports(results: list[dict[str, Any]], output_dir: Path) -> None:
    """Export JSON-only reports with one prediction file per engine."""
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
        result.setdefault("model_size_mb", model_size_mb(result["engine"]))
        result.setdefault("domain_keywords", keywords)
        normalized_results.append(result)
    results = normalized_results
    metadata = run_metadata()
    by_engine: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        by_engine.setdefault(result["engine"], []).append(result)
    predictions_dir = output_dir / "predictions"
    for engine, rows in by_engine.items():
        filename = re.sub(r"[^A-Za-z0-9_.-]+", "_", engine).strip("_")
        write_json(predictions_dir / f"{filename}.json", {
            "schema_version": 2,
            "metadata": {**metadata, "model_name": engine},
            "predictions": rows,
        })
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for result in results:
        grouped.setdefault((result["engine"], result["language"]), []).append(result)
    summary = []
    for (engine, language), rows in grouped.items():
        summary.append({
            "engine": engine,
            "language": language,
            "samples": len(rows),
            "avg_inference_time_sec": round(
                sum(row["inference_time_sec"] for row in rows) / len(rows), 4
            ),
            "avg_wer": round(sum(row["wer"] for row in rows) / len(rows), 4),
            "avg_cer": round(sum(row["cer"] for row in rows) / len(rows), 4),
            "avg_keyword_spotting_accuracy": round(
                sum(row["keyword_spotting_accuracy"] for row in rows if row["keyword_spotting_accuracy"] is not None)
                / max(1, sum(row["keyword_spotting_accuracy"] is not None for row in rows)), 4
            ),
            "avg_rtf": round(sum(row["rtf"] for row in rows) / len(rows), 4),
            "avg_inference_latency_ms": round(sum(row["inference_latency_ms"] for row in rows) / len(rows), 2),
            "max_peak_ram_mb": max(row["peak_ram_mb"] for row in rows),
            "model_size_mb": next((row["model_size_mb"] for row in rows if row["model_size_mb"] is not None), None),
        })
    write_json(output_dir / "summary.json", summary)
    export_plots(summary, output_dir / "plots")


def export_plots(summary: list[dict[str, Any]], plots_dir: Path) -> None:
    """Write comparison plots from the JSON summary."""
    plots_dir.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        print(f"[WARN] plots skipped; install matplotlib: {error}")
        return

    labels = [row["engine"] for row in summary]
    positions = list(range(len(labels)))
    figures = (
        (
            "model_quality.png",
            (
                ([row["avg_wer"] for row in summary], "WER"),
                ([row["avg_cer"] for row in summary], "CER"),
                ([row["avg_keyword_spotting_accuracy"] for row in summary], "Keyword accuracy"),
            ),
            "Recognition quality by engine",
            "Score",
        ),
        (
            "resource_usage.png",
            (
                ([row["max_peak_ram_mb"] for row in summary], "Peak RAM (MB)"),
                ([row["model_size_mb"] or 0 for row in summary], "Model size (MB)"),
            ),
            "Resource usage by engine",
            "MB",
        ),
            (
                "avg_inference_time.png",
                (([row["avg_inference_time_sec"] for row in summary], "Average inference time"),),
                "Average inference time by engine",
                "Seconds",
            ),
            (
                "avg_wer.png",
                (([row["avg_wer"] for row in summary], "Average WER"),),
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
            row["avg_wer"],
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
