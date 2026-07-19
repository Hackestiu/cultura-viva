"""Configuration for the Gaudí ragas evaluation pipeline, loaded from environment variables.

This repo only evaluates — it does not run the RAG + SLM pipeline under test (that lives in
a separate repo, which produces a predictions file consumed here). Every model used for
evaluation is free and local:
  - Judge LLM: any Ollama model (OLLAMA_JUDGE_BASE_URL / OLLAMA_JUDGE_MODEL). Prefer a
    larger/stronger model than the SLM under test, since self-grading is unreliable.
  - Judge embeddings: a local sentence-transformers model, used by embedding-based metrics.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
TESTSET_PATH = Path(os.getenv("TESTSET_PATH", ROOT_DIR / "eval" / "testset.json"))
PREDICTIONS_PATH = Path(os.getenv("PREDICTIONS_PATH", ROOT_DIR / "eval" / "predictions.json"))
RESULTS_DIR = Path(os.getenv("RESULTS_DIR", ROOT_DIR / "eval" / "results"))

# --- Judge LLM (served by Ollama, run by whoever executes the evaluation) ---
OLLAMA_JUDGE_BASE_URL = os.getenv("OLLAMA_JUDGE_BASE_URL", "http://localhost:11434")
OLLAMA_JUDGE_MODEL = os.getenv("OLLAMA_JUDGE_MODEL", "qwen2.5:7b")
JUDGE_TEMPERATURE = float(os.getenv("JUDGE_TEMPERATURE", "0.0"))

# --- Judge embeddings (local, free, no API key required) ---
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
