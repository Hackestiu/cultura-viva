"""Command-line entry point for the Cultura Viva English edge STT benchmark."""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
from pathlib import Path

from benchmark import export_reports, run_benchmark

APP_DIR = Path(__file__).resolve().parent


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
    """Resolve which dataset to run.

    An explicit --audio-dir/--manifest (flag or AUDIO_DIR/MANIFEST env var, as
    App Lab sets for Arduino) is used as-is and never overridden. Otherwise —
    the plain `python main.py` case — this prefers the recorded human-speech
    set at data_audio/recorded/ over the synthetic one, since real speech is
    the more representative test; it falls back to the synthetic set,
    generating it first if needed, only when no usable recorded set is found.
    """
    if args.audio_dir is not None or args.manifest is not None:
        if args.audio_dir is None or args.manifest is None:
            raise ValueError("--audio-dir and --manifest must both be set, or both left unset.")
        print(f"Using explicit dataset: {args.audio_dir}")
        return

    recorded_dir = APP_DIR /"data_audio" / "recorded"
    recorded_manifest = recorded_dir / "manifest.json"
    if dataset_has_audio(recorded_dir, recorded_manifest):
        args.audio_dir = str(recorded_dir)
        args.manifest = str(recorded_manifest)
        print(f"Using recorded dataset (preferred): {recorded_dir}")
        return

    synthetic_dir = APP_DIR / "data_audio"
    synthetic_manifest = synthetic_dir / "manifest.json"
    if not dataset_has_audio(synthetic_dir, synthetic_manifest):
        print("Recorded audio is unavailable; generating the synthetic dataset.")
        try:
            subprocess.run(
                [sys.executable, str(APP_DIR / "dataset_generator.py")],
                cwd=APP_DIR,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise RuntimeError(
                "No usable recorded or synthetic audio was found. "
                "Run 'python dataset_generator.py' on a computer with internet access."
            ) from error
    args.audio_dir = str(synthetic_dir)
    args.manifest = str(synthetic_manifest)
    print(f"Recorded dataset not found at {recorded_dir}; using synthetic dataset: {synthetic_dir}")


def parse_args() -> argparse.Namespace:
    """Build the command-line interface for configuring and running the benchmark."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-dir", default=os.getenv("AUDIO_DIR"))
    parser.add_argument("--manifest", default=os.getenv("MANIFEST"))
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
    parser.add_argument("--cpu-threads", type=int, default=None, help="CPU threads for CTranslate2 / faster-whisper")
    parser.add_argument("--whisper-beam-size", type=int, default=1, help="Whisper beam size (1 = greedy, fastest)")
    parser.add_argument("--whisper-initial-prompt", default=None)
    parser.add_argument("--enable-domain-bias", action="store_true", default=True, help="Enable domain prompt and hotwords biasing (default: True)")
    parser.add_argument("--no-domain-bias", dest="enable_domain_bias", action="store_false", help="Disable domain biasing")
    parser.add_argument("--wandb", action="store_true")
    parser.add_argument("--wandb-project", default="cultura-viva-stt-benchmark")
    return parser.parse_args()


def main() -> None:
    """Run and export the configured benchmark, optionally tracked in Weights & Biases."""
    args = parse_args()
    resolve_dataset(args)

    if args.wandb:
        import wandb

        dataset_source = "recorded" if "recorded" in Path(args.audio_dir).parts else "synthetic"
        wandb.init(
            project=args.wandb_project,
            config=vars(args),
            tags=[
                dataset_source,
                "domain-bias-on" if args.enable_domain_bias else "domain-bias-off",
                args.device,
            ],
        )
        wandb.config.update({"dataset_source": dataset_source, "host": platform.node()})

    results, engine_started_at = run_benchmark(args)
    export_reports(results, Path(args.output_dir), engine_started_at, use_wandb=args.wandb)

    if args.wandb:
        import wandb

        wandb.finish()

    print(f"Exported {len(results)} measurements to {args.output_dir}")


if __name__ == "__main__":
    main()