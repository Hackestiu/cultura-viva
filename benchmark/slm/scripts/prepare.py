"""CulturaViva: Model Preparation & Arduino Deployment Packager

Pulls Ollama models for PC evaluation, downloads GGUF binaries for
the Arduino UNO Q, and assembles a self-contained arduino_export/ bundle.

All settings come from config.yaml via core.config.cfg.

Usage (via main.py):
    uv run python main.py prepare --all
    uv run python main.py prepare --download-only
    uv run python main.py prepare --export-arduino [--model qwen2.5:1.5b]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.request

from core.config import cfg
from core.device_paths import DEVICE_APP_DIR, REPO_ROOT

# Entry-point scripts that ship inside the bundle. See device_runtime/README.md.
DEVICE_RUNTIME_DIR = REPO_ROOT / "benchmark" / "slm" / "device_runtime"


# ==========================================
# 1. PC MODEL SETUP (Ollama)
# ==========================================
def check_ollama_running() -> bool:
    try:
        urllib.request.urlopen(f"{cfg.ollama_base_url.rstrip('/')}/api/tags", timeout=3)
        return True
    except Exception:
        return False


def setup_pc_models():
    """Pulls candidate models and judge model in Ollama for evaluation."""
    print("\n[1/3] Preparing Ollama models for local evaluation...")
    if not check_ollama_running():
        print(f"Ollama is not reachable at {cfg.ollama_base_url}. Start it with `ollama serve` and try again.")
        sys.exit(1)

    print(f"Pulling judge model: {cfg.judge_model}")
    subprocess.run(["ollama", "pull", cfg.judge_model], check=True)

    for model in cfg.candidates:
        print(f"Pulling candidate model: {model['ollama_tag']}")
        subprocess.run(["ollama", "pull", model["ollama_tag"]], check=True)

    print("All Ollama models ready.")


# ==========================================
# 2. GGUF DOWNLOAD
# ==========================================
def download_gguf_models():
    """Downloads quantized GGUF models from HuggingFace for Arduino deployment."""
    print("\n[2/3] Downloading quantized GGUF models for Arduino UNO Q...")
    cfg.models_dir.mkdir(parents=True, exist_ok=True)

    for model in cfg.candidates:
        dest = cfg.models_dir / model["gguf_file"]
        if dest.exists() and dest.stat().st_size > 100_000:
            print(f"  {model['gguf_file']} already present ({dest.stat().st_size / (1024 * 1024):.1f} MB)")
            continue

        print(f"  Downloading {model['gguf_file']}...")
        try:
            subprocess.run(
                ["huggingface-cli", "download", model["gguf_repo"], model["gguf_file"],
                 "--local-dir", str(cfg.models_dir)],
                check=True,
            )
        except Exception:
            print(f"  huggingface-cli unavailable, falling back to direct download for {model['gguf_file']}")
            urllib.request.urlretrieve(model["gguf_url"], dest)

    print(f"GGUF models saved to {cfg.models_dir}")


# ==========================================
# 3. ARDUINO EXPORT
# ==========================================
SETUP_SH_TEMPLATE = """\
#!/usr/bin/env bash
set -e
echo "CulturaViva: setting up Arduino UNO Q (Debian ARM64)"
sudo apt update
sudo apt install -y build-essential python3 python3-pip python3-venv git

if command -v cpufreq-set >/dev/null 2>&1; then
    sudo cpufreq-set -g performance || true
else
    echo "cpufreq-set not available; continuing without changing the CPU governor."
fi

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip

echo "Compiling llama-cpp-python for Cortex-A53 ({compiler_flags})..."
CMAKE_ARGS="-DCMAKE_C_FLAGS='{compiler_flags}'" pip install llama-cpp-python

echo "Setup complete. Run with: ./venv/bin/python run_guide.py --model models/<file>.gguf"
"""


def export_arduino_package(model_tag: str | None = None):
    """Creates a self-contained folder ready to copy to the Arduino UNO Q."""
    tag = model_tag or cfg.arduino_default_model
    default_model = cfg.model_by_tag(tag)

    print("\n[3/3] Assembling deployment bundle for Arduino UNO Q...")
    cfg.arduino_export_dir.mkdir(parents=True, exist_ok=True)
    (cfg.arduino_export_dir / "models").mkdir(parents=True, exist_ok=True)

    copied_any = False
    for model in cfg.candidates:
        src = cfg.models_dir / model["gguf_file"]
        if src.exists():
            print(f"  Copying {model['gguf_file']} -> arduino_export/models/")
            shutil.copyfile(src, cfg.arduino_export_dir / "models" / model["gguf_file"])
            copied_any = True
    if not copied_any:
        print("  Warning: no GGUF models found in ./models/. Run --download-only first.")

    for data_file in (cfg.knowledge_base_path, cfg.element_sheets_path, cfg.testset_path):
        if data_file.exists():
            shutil.copyfile(data_file, cfg.arduino_export_dir / data_file.name)
        else:
            print(f"  Warning: {data_file.name} not found at {data_file}.")

    # The device's own modules, copied rather than regenerated from a source string.
    # They used to be embedded in this file as a Python literal, and the bundle's copy
    # was hand-edited afterwards -- so the generator and its output each grew a
    # different half and this step silently reverted whichever one it overwrote.
    # Copying the real file makes the two incapable of disagreeing.
    for module in ("knowledge_store.py", "guide_prompt.py"):
        shutil.copyfile(DEVICE_APP_DIR / module, cfg.arduino_export_dir / module)

    # The bundle's entry points. Real, reviewable files under device_runtime/, for the
    # same reason.
    for script in ("run_guide.py", "benchmark_arduino.py"):
        shutil.copyfile(DEVICE_RUNTIME_DIR / script, cfg.arduino_export_dir / script)

    # Sampling parameters travel with the bundle instead of being baked into the
    # scripts, so the board cannot disagree with config.yaml about how to generate.
    bundle_config = {
        "default_gguf": default_model["gguf_file"],
        "retrieval_top_k": cfg.retrieval_top_k,
        "inference": {
            "temperature": cfg.inference_temperature,
            "max_tokens": cfg.inference_max_tokens,
            "repeat_penalty": cfg.inference_repeat_penalty,
            "stop": list(cfg.inference_stop),
            "context_window": cfg.inference_context_window,
            "threads": cfg.inference_threads,
            "batch_size": cfg.inference_batch_size,
        },
    }
    (cfg.arduino_export_dir / "bundle_config.json").write_text(
        json.dumps(bundle_config, indent=2) + "\n", encoding="utf-8"
    )

    (cfg.arduino_export_dir / "setup_arduino.sh").write_text(
        SETUP_SH_TEMPLATE.format(compiler_flags=cfg.arduino_compiler_flags), encoding="utf-8"
    )

    print(f"Default model: {default_model['name']} ({default_model['gguf_file']})")
    print(f"Arduino package exported to: {cfg.arduino_export_dir}")


# ==========================================
# 4. CLI
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="CulturaViva Model Preparation & Arduino Deployment Packager")
    parser.add_argument("--all", action="store_true", help="Download Ollama & GGUF models, then export Arduino bundle")
    parser.add_argument("--download-only", action="store_true", help="Download Ollama and GGUF models only")
    parser.add_argument("--export-arduino", action="store_true", help="Assemble export package for Arduino")
    parser.add_argument(
        "--model", default=cfg.arduino_default_model,
        help=f"Default model for the Arduino export (default: {cfg.arduino_default_model})",
    )

    args = parser.parse_args()

    if args.all or len(sys.argv) == 1:
        setup_pc_models()
        download_gguf_models()
        export_arduino_package(args.model)
    elif args.download_only:
        setup_pc_models()
        download_gguf_models()
    elif args.export_arduino:
        export_arduino_package(args.model)


if __name__ == "__main__":
    main()
