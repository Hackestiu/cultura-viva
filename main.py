"""Command-line entry point for the Cultura Viva English edge STT benchmark."""

from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import subprocess
import sys
from pathlib import Path

from benchmark import export_reports, run_benchmark
from utils import ensure_engine_models

ENGINE_DEPENDENCIES = {
    "whisper.cpp:base.en-q5_1": {"module": "pywhispercpp", "pip": "pywhispercpp>=1.2.0"},
    "whisper.cpp:base.en-q5_0": {"module": "pywhispercpp", "pip": "pywhispercpp>=1.2.0"},
    "faster-whisper:base.en": {"module": "faster_whisper", "pip": "faster-whisper==1.1.1"},
    "faster-whisper:tiny.en": {"module": "faster_whisper", "pip": "faster-whisper==1.1.1"},
    "vosk": {"module": "vosk", "pip": "vosk==0.3.45"},
    "sherpa-onnx": {"module": "sherpa_onnx", "pip": "sherpa-onnx==1.12.40"},
}


def engine_dependency_requirements(engine_name: str) -> dict[str, str]:
    """Return the import- and pip-install names required for an STT engine."""
    return ENGINE_DEPENDENCIES.get(engine_name, {})


def ensure_runtime_dependencies(engine_names: list[str]) -> None:
    """Install any missing engine dependency when the selected model is used."""
    for engine_name in dict.fromkeys(engine_names):
        dependency = engine_dependency_requirements(engine_name)
        if not dependency:
            continue
        module_name = dependency["module"]
        package_spec = dependency["pip"]
        if importlib.util.find_spec(module_name) is None:
            print(
                f"Engine '{engine_name}' requires '{package_spec}', which is not installed. "
                "Installing it now..."
            )
            subprocess.run([sys.executable, "-m", "pip", "install", package_spec], check=True)

APP_DIR = Path(__file__).resolve().parent
ALL_ENGINES = (
    "whisper.cpp:base.en-q5_1",
    "faster-whisper:base.en",
    "faster-whisper:tiny.en",
    "vosk",
    "sherpa-onnx",
)


def dataset_has_audio(audio_dir: Path, manifest_path: Path) -> bool:
    """Return whether every manifest item has a matching WAV file."""
    if not manifest_path.is_file():
        return False
    try:
        import json

        items = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(items) and all((audio_dir / item.get("filename", "")).is_file() for item in items)


def resolve_dataset(args: argparse.Namespace) -> None:
    if args.audio_dir is not None or args.manifest is not None:
        if args.audio_dir is None or args.manifest is None:
            raise ValueError("--audio-dir and --manifest must both be set, or both left unset.")
        print(f"Using explicit dataset: {args.audio_dir}")
        return

    recorded_dir = APP_DIR / "data_audio" / "recorded"
    recorded_manifest = recorded_dir / "manifest.json"
    if dataset_has_audio(recorded_dir, recorded_manifest):
        args.audio_dir = str(recorded_dir)
        args.manifest = str(recorded_manifest)
        print(f"Using recorded dataset (preferred): {recorded_dir}")
        return
    
    synthetic_dir = APP_DIR / "data_audio"
    synthetic_manifest = synthetic_dir / "manifest.json"
    if not dataset_has_audio(synthetic_dir, synthetic_manifest):
        raise RuntimeError(
            "No usable recorded or synthetic audio was found. "
            "Please provide a dataset via --audio-dir and --manifest."
        )
    args.audio_dir = str(synthetic_dir)
    args.manifest = str(synthetic_manifest)
    print(f"Recorded dataset not found at {recorded_dir}; using synthetic dataset: {synthetic_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-dir", default=os.getenv("AUDIO_DIR"))
    parser.add_argument("--manifest", default=os.getenv("MANIFEST"))
    parser.add_argument("--output-dir", default=os.getenv("OUTPUT_DIR", str(APP_DIR / "results_computer")))
    parser.add_argument(
        "--engines",
        nargs="+",
        default=[
            "whisper.cpp:base.en-q5_1",
        ],
        help="STT engines to benchmark; use 'all' for every configured engine",
    )
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda"))
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument(
        "--cpu-threads",
        type=int,
        default=4,
        help="CPU threads for inference (default: 4, matching the QRB2210's 4 Cortex-A53 cores)",
    )
    parser.add_argument("--whisper-beam-size", type=int, default=1, help="Whisper beam size (1 = greedy, fastest)")
    parser.add_argument("--whisper-initial-prompt", default=None, help="Custom prompt override (domain bias prompt is used by default)")
    parser.add_argument(
        "--whisper-use-gpu",
        action="store_true",
        help="Let whisper.cpp offload to GPU if the installed build supports it",
    )
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    if "all" in args.engines:
        args.engines = list(ALL_ENGINES)
    ensure_runtime_dependencies(args.engines)
    ensure_engine_models(args.engines)
    resolve_dataset(args)

    results, engine_started_at = run_benchmark(args)
    export_reports(results, Path(args.output_dir), engine_started_at)

    print(f"Exported {len(results)} measurements to {args.output_dir}")

if __name__ == "__main__":
    main()