"""Command-line entry point for the Cultura Viva English edge STT benchmark."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from benchmark import export_reports, run_benchmark

APP_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    """Build a small CLI suitable for Arduino App Lab environment variables."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-dir", default=os.getenv("AUDIO_DIR", str(APP_DIR / "data_audio")))
    parser.add_argument("--manifest", default=os.getenv("MANIFEST", str(APP_DIR / "data_audio" / "manifest.json")))
    parser.add_argument("--output-dir", default=os.getenv("OUTPUT_DIR", str(APP_DIR / "results_computer")))
    parser.add_argument(
        "--engines",
        nargs="+",
        default=[
            "faster-whisper:tiny.en", "faster-whisper:base.en",
            "vosk", "sherpa-onnx"
        ],
    )
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda"))
    parser.add_argument("--compute-type", default="int8")
    return parser.parse_args()


def main() -> None:
    """Run and export the configured benchmark."""
    args = parse_args()
    results = run_benchmark(args)
    export_reports(results, Path(args.output_dir))
    print(f"Exported {len(results)} measurements to {args.output_dir}")


if __name__ == "__main__":
    main()