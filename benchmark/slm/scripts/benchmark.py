"""CulturaViva: SLM Benchmarking Suite for Gaudí Audio Guide

Generates predictions over eval/testset.json for each candidate model and each
guide personality, then invokes Ragas evaluation to score them.

The prompt is not defined here. It is imported from the device application
(arduino/python/core/model_module.py) via core.device_prompt, so a benchmark run
measures the prompt that actually ships rather than a copy of an older one.

Retrieval is the one deliberate difference from the device. On the board, vision
names the element and the knowledge sheet is looked up by id; the testset has no
element ids and asks architect-level and cross-monument questions, so passages
are retrieved semantically here instead.

All settings come from config.yaml via core.config.cfg.

Usage (via main.py):
    uv run python main.py benchmark
    uv run python main.py benchmark --model qwen2.5:1.5b
    uv run python main.py benchmark --personality technical
    uv run python main.py benchmark --skip-eval
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from core.config import cfg
from core.device_prompt import PERSONALITIES, build_messages


# ==========================================
# 1. KNOWLEDGE STORE (Semantic Vector Retrieval)
# ==========================================
class GaudiKnowledgeStore:
    """
    Dense semantic vector retrieval over the Gaudí knowledge base and element sheets.
    Indexes granular passages using sentence-transformers (all-MiniLM-L6-v2) to eliminate
    brittle keyword matching and preposition biases. Multi-hop and multi-aspect questions
    retrieve top-k semantically relevant chunks to maximize Context Recall.
    """

    def __init__(self):
        self.kb = self._load_json(cfg.knowledge_base_path) or {}
        sheets_data = self._load_json(cfg.element_sheets_path) or {}
        raw_sheets = sheets_data.get("sheets", [])
        self.sheets_by_id = {s["id"]: s for s in raw_sheets}

        print(f"Initializing semantic retriever with {cfg.embedding_model}...")
        self.embedder = SentenceTransformer(cfg.embedding_model)
        self.chunks = self._build_chunks(raw_sheets)
        chunk_texts = [c["text"] for c in self.chunks]
        self.chunk_embeddings = self.embedder.encode(chunk_texts, normalize_embeddings=True)
        print(f"Indexed {len(self.chunks)} semantic knowledge chunks.")

    @staticmethod
    def _load_json(path: Path):
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _build_chunks(self, sheets: list[dict]) -> list[dict]:
        chunks = []
        # 1. Knowledge Base entries: overview chunk + per-fact chunks
        for k, v in self.kb.items():
            name = v.get("name", k)
            loc = v.get("location", "")
            arch = v.get("architect", "")
            style = v.get("style", "")
            status = v.get("status", "")
            unesco = v.get("unesco_status", "")
            overview = f"{name}. Location: {loc}. Architect: {arch}. Style: {style}. Status: {status}. UNESCO: {unesco}."
            chunks.append({"id": f"{k}_overview", "title": name, "text": overview.strip()})

            for i, fact in enumerate(v.get("notable_facts", [])):
                chunks.append({"id": f"{k}_fact_{i}", "title": name, "text": f"{name}: {fact}"})

        # 2. Element sheets
        for s in sheets:
            s_name = s.get("name")
            parent = s.get("parent", s_name)
            mats = ", ".join(s.get("materials", []))
            tech = " ".join(s.get("technical_facts", []))
            art = " ".join(s.get("artistic_facts", []))
            text = f"{s_name} (part of {parent}). Materials: {mats}. {s.get('inspiration', '')} {tech} {art}".strip()
            chunks.append({"id": s.get("id"), "title": s_name, "text": text})

        return chunks

    def retrieve_top_k(self, query: str, k: int = 3) -> list[str]:
        """Retrieve top-k most semantically relevant text chunks for a question."""
        q_emb = self.embedder.encode([query], normalize_embeddings=True)
        sims = np.dot(self.chunk_embeddings, q_emb.T).squeeze()
        top_idx = np.argsort(-sims)[:k]
        return [self.chunks[i]["text"] for i in top_idx]

    def context_for_topic(self, query: str, k: int = 3) -> str:
        """Joined context string for prompt formatting."""
        return "\n\n---\n\n".join(self.retrieve_top_k(query, k=k))

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

        return "\n---\n".join(parts)

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



# ==========================================
# 2. PREDICTION GENERATOR
# ==========================================
def ollama_chat(
    model_tag: str,
    messages: list[dict],
    base_url: str | None = None,
    options: dict | None = None,
) -> dict:
    """One /api/chat call. Returns answer, wall-clock, and why generation stopped.

    /api/chat rather than /api/generate: the device calls llama.cpp's
    create_chat_completion, which applies the model's chat template to a system
    and a user turn. Flattening that into one completion prompt, as this script
    used to, measures a prompt shape the device never sends.

    `base_url` and `options` default to the candidate model's endpoint and the
    device's sampling parameters. They are overridable so a judge can be driven
    through the same function rather than a second copy of this urllib block.

    done_reason matters: at max_tokens=60 an answer can be cut off mid-sentence,
    and a caller that only looks at the text cannot tell a finished answer from a
    truncated one.
    """
    opts = {
        "temperature": cfg.inference_temperature,
        "num_predict": cfg.inference_max_tokens,
        "repeat_penalty": cfg.inference_repeat_penalty,
        "num_ctx": cfg.inference_context_window,
        "stop": list(cfg.inference_stop),
        # Ollama picks a random seed when none is given, so without this a rerun
        # is not reproducible and a same-prompt control could not be measured.
        "seed": cfg.inference_seed,
    }
    if options:
        opts.update(options)

    payload = json.dumps({
        "model": model_tag,
        "messages": messages,
        "stream": False,
        "options": opts,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{(base_url or cfg.ollama_base_url).rstrip('/')}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    start = time.time()
    result: dict = {}
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            answer = (result.get("message") or {}).get("content", "").strip()
            error = None
    except Exception as e:
        answer = f"Error during inference: {e}"
        error = str(e)

    return {
        "answer": answer,
        "elapsed_s": round(time.time() - start, 3),
        "done_reason": result.get("done_reason"),
        "eval_count": result.get("eval_count"),
        "prompt_eval_count": result.get("prompt_eval_count"),
        "error": error,
    }


def load_testset() -> list[dict]:
    if not cfg.testset_path.exists():
        print(f"Testset not found at {cfg.testset_path}. Ensure eval/testset.json exists.")
        sys.exit(1)
    with open(cfg.testset_path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_predictions(
    model_tag: str, personality: str, store: GaudiKnowledgeStore, testset: list[dict]
) -> list[dict]:
    """Answer every testset question as one guide personality."""
    predictions = []
    print(f"\nGenerating predictions for: {model_tag}  [{personality}]")

    for i, item in enumerate(testset, 1):
        question = item["question"]

        element_id = item.get("element_id")
        if element_id:
            contexts = [store.context_for_element(element_id)]
        else:
            contexts = store.retrieve_top_k(question, k=cfg.retrieval_top_k)

        # The device's own prompt builder: retrieved facts first, personality
        # instructions second, question alone in the user turn.
        messages = build_messages(
            question=question,
            element=element_id,
            personality=personality,
            kg_context="\n\n---\n\n".join(contexts),
        )

        result = ollama_chat(model_tag, messages)
        answer, elapsed = result["answer"], result["elapsed_s"]

        print(f"  [{i}/{len(testset)}] {elapsed:.2f}s  {item['id']}")
        predictions.append({
            "id": item["id"],
            "question": question,
            "reference": item.get("reference", ""),
            "contexts": contexts,
            "answer": answer,
            "personality": personality,
            "elapsed_s": round(elapsed, 3),
        })

    return predictions


# ==========================================
# 3. BENCHMARK RUNNER
# ==========================================
def predictions_path(model_tag: str, personality: str) -> Path:
    """eval/predictions_<model>_<personality>.json"""
    return cfg.eval_dir / f"predictions_{model_tag.replace(':', '_')}_{personality}.json"


def run_benchmark(
    target_model_tag: str | None = None,
    target_personality: str | None = None,
    skip_eval: bool = False,
):
    models_to_run = [
        m for m in cfg.candidates
        if target_model_tag is None or m["ollama_tag"] == target_model_tag
    ]
    if not models_to_run:
        known = [m["ollama_tag"] for m in cfg.candidates]
        print(f"Model tag '{target_model_tag}' not found in candidates from config.yaml. Known: {known}")
        sys.exit(1)

    personalities = [target_personality] if target_personality else list(cfg.personalities)
    unknown = [p for p in personalities if p not in PERSONALITIES]
    if unknown:
        print(f"Unknown personality {unknown}. The device defines: {list(PERSONALITIES)}")
        sys.exit(1)

    store = GaudiKnowledgeStore()
    testset = load_testset()

    total = len(models_to_run) * len(personalities)
    print(f"\nStarting benchmark: {len(models_to_run)} model(s) x {len(personalities)} "
          f"personality(ies) = {total} run(s) over {len(testset)} questions.")

    for model in models_to_run:
        model_tag = model["ollama_tag"]
        for personality in personalities:
            preds = generate_predictions(model_tag, personality, store, testset)
            pred_file = predictions_path(model_tag, personality)
            with open(pred_file, "w", encoding="utf-8") as f:
                json.dump(preds, f, indent=2, ensure_ascii=False)
            print(f"Saved predictions -> {pred_file.name}")

            if skip_eval:
                print("Skipping Ragas evaluation stage (--skip-eval).")
                continue

            print(f"Scoring {model_tag} [{personality}] with judge ({cfg.judge_model})...")
            subprocess.run(
                [sys.executable, "-m", "eval.evaluate", "--predictions", str(pred_file)],
                check=False,
            )


def main():
    parser = argparse.ArgumentParser(description="CulturaViva SLM Benchmarking Suite")
    parser.add_argument(
        "--model", default=None,
        help="Ollama model tag to benchmark (e.g. qwen2.5:1.5b). Omit to benchmark all candidates.",
    )
    parser.add_argument(
        "--personality", default=None,
        help=f"Guide personality to benchmark ({', '.join(PERSONALITIES)}). Omit to run all of them.",
    )
    parser.add_argument("--skip-eval", action="store_true", help="Skip Ragas scoring after generating predictions")

    args = parser.parse_args()
    run_benchmark(
        target_model_tag=args.model,
        target_personality=args.personality,
        skip_eval=args.skip_eval,
    )


if __name__ == "__main__":
    main()
