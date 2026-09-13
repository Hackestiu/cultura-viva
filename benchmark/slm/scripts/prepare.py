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
import shutil
import subprocess
import sys
import urllib.request

from core.config import cfg


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
# 3. ARDUINO EXPORT — embedded source templates
# ==========================================
KNOWLEDGE_STORE_MODULE_SOURCE = '''\
"""Shared id-based knowledge lookup for the CulturaViva audio guide.

Kept as a standalone module so the Arduino export bundle is completely self-contained.
"""

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
KB_PATH = BASE_DIR / "knowledge_base.json"
SHEETS_PATH = BASE_DIR / "element_sheets.json"


class GaudiKnowledgeStore:
    def __init__(self, kb_path: Path = KB_PATH, sheets_path: Path = SHEETS_PATH):
        self.kb = self._load_json(kb_path) or {}
        sheets_data = self._load_json(sheets_path) or {}
        self.sheets_by_id = {s["id"]: s for s in sheets_data.get("sheets", [])}

    @staticmethod
    def _load_json(path: Path):
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def context_for_element(self, element_id: str, include_similar: bool = True) -> str:
        sheet = self.sheets_by_id.get(element_id)
        if sheet is None:
            return self.context_for_topic(element_id)

        parts = [self._render_sheet(sheet)]
        parent = self.sheets_by_id.get(sheet.get("parent"))
        if parent is not None:
            parts.append(self._render_sheet(parent))
        if include_similar:
            for note in sheet.get("similarities", []):
                parts.append(f"Related: {note}")

        return "\\n---\\n".join(parts)

    def context_for_topic(self, query: str) -> str:
        words = set(re.findall(r"\\w+", query.lower()))
        best_key, best_score = None, 0
        for key, entry in self.kb.items():
            haystack = " ".join([entry.get("name", ""), *entry.get("aliases", []), key]).lower()
            score = sum(1 for w in words if w in haystack)
            if score > best_score:
                best_key, best_score = key, score

        if best_key is None:
            return (
                "No specific context available. Answer only with widely known, "
                "well-established facts about Antoni Gaudi, and say so if unsure."
            )
        return self._render_kb_entry(self.kb[best_key])

    @staticmethod
    def _render_sheet(sheet: dict) -> str:
        materials = ", ".join(sheet.get("materials", []))
        facts = " ".join(sheet.get("technical_facts", []) + sheet.get("artistic_facts", []))
        return (
            f"{sheet.get('name')} (part of {sheet.get('parent', sheet.get('name'))}). "
            f"Materials: {materials}. {sheet.get('inspiration', '')} {facts}"
        ).strip()

    @staticmethod
    def _render_kb_entry(entry: dict) -> str:
        """Renders all available structured fields so the SLM receives full grounding."""
        lines = [f"Name: {entry.get('name', '')}"]
        
        # Include all key metadata fields if present
        for key, label in [
            ("born", "Born"),
            ("died", "Died"),
            ("nationality", "Nationality"),
            ("style", "Style"),
            ("education", "Education"),
            ("location", "Location"),
            ("architect", "Architect"),
            ("height", "Height"),
            ("consecrated", "Consecrated"),
            ("commissioned_by", "Commissioned By"),
            ("timeline", "Timeline"),
            ("status", "Status"),
            ("unesco_status", "UNESCO Status"),
            ("burial", "Burial"),
        ]:
            if val := entry.get(key):
                lines.append(f"{label}: {val}")

        if facts := entry.get("notable_facts"):
            lines.append("Notable Facts:\n- " + "\n- ".join(facts))

        return "\n".join(lines).strip()

'''

RUN_GUIDE_SOURCE_TEMPLATE = '''\
#!/usr/bin/env python3
"""
CulturaViva runtime for the Arduino UNO Q.

Takes the element id from the upstream CV model (or free text for general
questions), looks up grounding context from the knowledge files, and
generates a short spoken answer with the local SLM.
"""

import argparse
from llama_cpp import Llama
from gaudi_knowledge_store import GaudiKnowledgeStore

DEFAULT_MODEL_PATH = "models/{default_gguf_file}"

SYSTEM_INSTRUCTIONS = (
    "You are CulturaViva, an audio guide for Antoni Gaudi's monuments in Barcelona. "
    "Answer the visitor's question in 2-3 sentences, using only the context provided. "
    "If the context does not contain the answer, say you are not sure rather than guessing."
)


def build_prompt(context: str, question: str) -> str:
    return f"{{SYSTEM_INSTRUCTIONS}}\\n\\nContext:\\n{{context}}\\n\\nVisitor: {{question}}\\nGuide:"


def main():
    parser = argparse.ArgumentParser(description="CulturaViva audio guide runtime")
    parser.add_argument("--model", default=DEFAULT_MODEL_PATH, help="Path to the GGUF model file")
    parser.add_argument("--element-id", default=None, help="Element id from the CV model, if any")
    parser.add_argument("--n-threads", type=int, default=4, help="CPU threads (UNO Q has 4 Cortex-A53 cores)")
    args = parser.parse_args()

    print(f"Loading {{args.model}} on Qualcomm QRB2210 (ARM Cortex-A53)...")
    llm = Llama(model_path=args.model, n_ctx=2048, n_threads=args.n_threads, n_batch=256, verbose=False)
    store = GaudiKnowledgeStore()
    print("Model and knowledge store loaded.\\n")

    element_id = args.element_id
    while True:
        try:
            if element_id is None:
                element_id = input("Element id (blank for a general question): ").strip() or None
            query = input("Visitor question (or 'exit'): ").strip()
            if query.lower() in ("exit", "quit"):
                break

            context = store.context_for_element(element_id) if element_id else store.context_for_topic(query)
            prompt = build_prompt(context, query)

            print("\\nCulturaViva: ", end="", flush=True)
            for chunk in llm(prompt, max_tokens=150, temperature=0.2, stream=True):
                print(chunk["choices"][0]["text"], end="", flush=True)
            print("\\n" + "-" * 50 + "\\n")

            element_id = None
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
'''

SETUP_SH_TEMPLATE = """\
#!/usr/bin/env bash
set -e
echo "CulturaViva: setting up Arduino UNO Q (Debian ARM64)"
sudo apt update
sudo apt install -y build-essential python3 python3-pip python3-venv git cpufrequtils

sudo cpufreq-set -g performance || true

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

    (cfg.arduino_export_dir / "gaudi_knowledge_store.py").write_text(
        KNOWLEDGE_STORE_MODULE_SOURCE, encoding="utf-8"
    )
    (cfg.arduino_export_dir / "setup_arduino.sh").write_text(
        SETUP_SH_TEMPLATE.format(compiler_flags=cfg.arduino_compiler_flags), encoding="utf-8"
    )
    (cfg.arduino_export_dir / "run_guide.py").write_text(
        RUN_GUIDE_SOURCE_TEMPLATE.format(default_gguf_file=default_model["gguf_file"]), encoding="utf-8"
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
