"""Ragas evaluation of a Gaudí RAG + SLM pipeline's outputs.

Joins predictions with the curated reference answers in eval/testset.json
and scores them with ragas using a fully local, free judge:
  - Judge LLM:        any Ollama model (default: qwen2.5:7b)
  - Judge embeddings: sentence-transformers/all-MiniLM-L6-v2

All settings come from config.yaml (with optional .env overrides).

Usage:
    uv run python -m eval.evaluate [--predictions PATH]
    uv run python main.py eval [--predictions PATH]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import ChatOllama
from ragas import EvaluationDataset, evaluate
from ragas.dataset_schema import SingleTurnSample
from ragas.metrics import AnswerRelevancy, ContextPrecision, ContextRecall, Faithfulness

from core.config import cfg


def load_json(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Provide a valid predictions file with --predictions. "
            "See eval/predictions.example.json for the expected schema."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def build_dataset(testset: list[dict], predictions: list[dict]) -> EvaluationDataset:
    predictions_by_id = {p["id"]: p for p in predictions}

    missing = [item["id"] for item in testset if item["id"] not in predictions_by_id]
    if missing:
        raise ValueError(f"Predictions file is missing entries for ids: {missing}")

    samples = [
        SingleTurnSample(
            user_input=item["question"],
            retrieved_contexts=predictions_by_id[item["id"]].get(
                "contexts", [predictions_by_id[item["id"]].get("context", "")]
            ),
            response=predictions_by_id[item["id"]]["answer"],
            reference=item["reference"],
        )
        for item in testset
    ]
    return EvaluationDataset(samples=samples)


def build_judge():
    judge_llm = ChatOllama(
        base_url=cfg.judge_base_url,
        model=cfg.judge_model,
        temperature=cfg.judge_temperature,
    )
    judge_embeddings = HuggingFaceEmbeddings(model_name=cfg.embedding_model)
    return judge_llm, judge_embeddings


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Gaudí RAG + SLM pipeline outputs with ragas.")
    parser.add_argument(
        "--predictions",
        type=Path,
        default=cfg.predictions_path,
        help="Path to the predictions JSON. See eval/predictions.example.json for the schema.",
    )
    args = parser.parse_args()

    print(f"Judge LLM      : {cfg.judge_model} @ {cfg.judge_base_url}")
    print(f"Judge embeddings: {cfg.embedding_model} (local)")
    print(f"Testset         : {cfg.testset_path}")
    print(f"Predictions     : {args.predictions}\n")

    testset = load_json(cfg.testset_path)
    predictions = load_json(args.predictions)
    dataset = build_dataset(testset, predictions)

    judge_llm, judge_embeddings = build_judge()
    metrics = [Faithfulness(), AnswerRelevancy(), ContextPrecision(), ContextRecall()]

    print(f"Running ragas evaluation over {len(dataset)} Gaudí questions...")
    result = evaluate(dataset=dataset, metrics=metrics, llm=judge_llm, embeddings=judge_embeddings)

    print("\n=== Ragas scores ===")
    print(result)

    cfg.results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = cfg.results_dir / f"eval_{timestamp}.csv"
    result.to_pandas().to_csv(csv_path, index=False)
    print(f"\nPer-question results saved to {csv_path}")


if __name__ == "__main__":
    main()
