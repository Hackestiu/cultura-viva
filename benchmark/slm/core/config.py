"""Shared configuration loader for the CulturaViva SLM benchmark.

Loads config.yaml once from the repository root and exposes typed, resolved
attributes. Every script (scripts/prepare.py, scripts/benchmark.py,
eval/evaluate.py) imports from here instead of duplicating the loading logic.

Priority order for each value:
  1. Environment variable (via .env or shell export)
  2. config.yaml value
  3. Built-in default

Usage:
    from core.config import cfg
    print(cfg.judge_model)
    print(cfg.testset_path)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

# The repository root is always two levels up from this file (core/config.py).
ROOT = Path(__file__).resolve().parent.parent
CONFIG_YAML = ROOT / "config.yaml"


def _load_yaml() -> dict:
    if not CONFIG_YAML.exists():
        raise FileNotFoundError(
            f"config.yaml not found at {CONFIG_YAML}. "
            "It must exist at the repository root."
        )
    with open(CONFIG_YAML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@dataclass(frozen=True)
class Config:
    # --- Candidate models ---
    candidates: list[dict] = field(default_factory=list)

    # --- Judge LLM ---
    judge_model: str = "qwen2.5:7b"
    judge_base_url: str = "http://localhost:11434"
    judge_temperature: float = 0.0

    # --- Embeddings ---
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # --- Endpoint serving the candidate models (distinct from the judge's) ---
    ollama_base_url: str = "http://localhost:11434"

    # --- Inference parameters (mirror arduino/python/core/model_module.py) ---
    inference_temperature: float = 0.1
    inference_max_tokens: int = 60
    inference_repeat_penalty: float = 1.1
    inference_stop: tuple[str, ...] = ("\n\n", "<|im_end|>")
    inference_seed: int = 0
    inference_context_window: int = 2048
    inference_threads: int = 4
    inference_batch_size: int = 256
    personalities: tuple[str, ...] = ("artistic", "technical", "child")

    # --- Retrieval ---
    retrieval_top_k: int = 3

    # --- Resolved absolute paths ---
    knowledge_base_path: Path = ROOT / "data" / "knowledge_base.json"
    element_sheets_path: Path = ROOT / "data" / "element_sheets.json"
    testset_path: Path = ROOT / "eval" / "testset.json"
    predictions_path: Path = ROOT / "eval" / "predictions.json"
    results_dir: Path = ROOT / "eval" / "results"
    models_dir: Path = ROOT / "models"
    arduino_export_dir: Path = ROOT / "arduino_export"
    eval_dir: Path = ROOT / "eval"

    # --- Arduino deployment ---
    arduino_default_model: str = "qwen2.5:1.5b"
    arduino_compiler_flags: str = "-march=armv8-a -mtune=cortex-a53"

    def model_by_tag(self, tag: str) -> dict:
        """Return the candidate model entry matching the given Ollama tag."""
        for model in self.candidates:
            if model["ollama_tag"] == tag:
                return model
        known = [m["ollama_tag"] for m in self.candidates]
        raise ValueError(f"Unknown model tag: {tag!r}. Known tags: {known}")


def _build_config() -> Config:
    raw = _load_yaml()

    paths = raw.get("paths", {})
    ollama = raw.get("ollama", {})
    judge = raw.get("judge", {})
    retrieval = raw.get("retrieval", {})
    embeddings = raw.get("embeddings", {})
    inference = raw.get("inference", {})
    arduino = raw.get("arduino", {})

    def p(env_key: str, yaml_rel: str | None, default_rel: str) -> Path:
        """Resolve a path: env var > config.yaml relative > hard-coded default."""
        rel = os.getenv(env_key) or yaml_rel or default_rel
        return ROOT / rel

    return Config(
        candidates=raw.get("candidates", []),

        ollama_base_url=os.getenv(
            "OLLAMA_BASE_URL", ollama.get("base_url", "http://localhost:11434")
        ),

        judge_model=os.getenv("OLLAMA_JUDGE_MODEL", judge.get("model", "qwen2.5:7b")),
        judge_base_url=os.getenv("OLLAMA_JUDGE_BASE_URL", judge.get("base_url", "http://localhost:11434")),
        judge_temperature=float(os.getenv("JUDGE_TEMPERATURE", str(judge.get("temperature", 0.0)))),

        embedding_model=os.getenv("EMBEDDING_MODEL", embeddings.get("model", "sentence-transformers/all-MiniLM-L6-v2")),

        inference_temperature=inference.get("temperature", 0.1),
        inference_max_tokens=inference.get("max_tokens", 60),
        inference_repeat_penalty=inference.get("repeat_penalty", 1.1),
        inference_stop=tuple(inference.get("stop", ["\n\n", "<|im_end|>"])),
        inference_seed=int(inference.get("seed", 0)),
        inference_context_window=inference.get("context_window", 2048),
        inference_threads=inference.get("threads", 4),
        inference_batch_size=inference.get("batch_size", 256),
        personalities=tuple(inference.get("personalities", ["artistic", "technical", "child"])),

        retrieval_top_k=int(retrieval.get("top_k", 3)),

        knowledge_base_path=p("", paths.get("knowledge_base"), "data/knowledge_base.json"),
        element_sheets_path=p("", paths.get("element_sheets"), "data/element_sheets.json"),
        testset_path=p("TESTSET_PATH", paths.get("testset"), "eval/testset.json"),
        predictions_path=p("PREDICTIONS_PATH", None, "eval/predictions.json"),
        results_dir=p("RESULTS_DIR", paths.get("results_dir"), "eval/results"),
        models_dir=ROOT / paths.get("models_dir", "models"),
        arduino_export_dir=ROOT / paths.get("arduino_export_dir", "arduino_export"),
        eval_dir=ROOT / paths.get("eval_dir", "eval"),

        arduino_default_model=arduino.get("default_model", "qwen2.5:1.5b"),
        arduino_compiler_flags=arduino.get("compiler_flags", "-march=armv8-a -mtune=cortex-a53"),
    )


# Single shared instance — imported by all scripts.
cfg = _build_config()
