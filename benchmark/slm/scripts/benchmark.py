"""CulturaViva: SLM Benchmarking Suite for Gaudí Audio Guide

Generates predictions over eval/testset.json for each candidate model and each
guide personality, then invokes Ragas evaluation to score them.

Neither the prompt nor the knowledge renderer is defined here. Both are imported
from the device application (arduino/python/guide_prompt.py and knowledge_store.py)
via core.device_prompt, so a benchmark run measures what actually ships rather than
a copy of an older one. This project used to import the prompt but keep its own
renderer, which is how the personality study ended up scoring context the board
never produced.

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
import subprocess
import sys
import time

from core.config import cfg
from core.device_prompt import PERSONALITIES, build_messages, display_name
from core.knowledge import SemanticKnowledgeStore
from core.ollama import ollama_chat


# ==========================================
# 2. PREDICTION GENERATOR
# ==========================================
def load_testset() -> list[dict]:
    if not cfg.testset_path.exists():
        print(f"Testset not found at {cfg.testset_path}. Ensure eval/testset.json exists.")
        sys.exit(1)
    with open(cfg.testset_path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_predictions(
    model_tag: str, personality: str, store: SemanticKnowledgeStore, testset: list[dict]
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
            # Resolved the way the device resolves it, so a snake_case vision label
            # never reaches the prompt. No item in the current testset carries an
            # element_id, so this is inert today -- and wrong the moment one does.
            element_name=display_name(element_id),
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

    store = SemanticKnowledgeStore()
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
