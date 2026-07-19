"""Ragas evaluation of a Gaudí RAG + SLM pipeline's outputs.

This repo only evaluates: the RAG + SLM pipeline under test lives in a separate repo and is
run there to produce a predictions file. This script joins those predictions with the
curated reference answers in `testset.json` and scores them with ragas.

Every model involved in evaluation is free and local:
  - Judge LLM: an Ollama model (must be installed & running by whoever runs this).
  - Judge embeddings: a local sentence-transformers model (no API key).

Usage:
    uv run python -m eval.evaluate [--predictions PATH]
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

from eval import config


def load_json(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Point --predictions (or PREDICTIONS_PATH) at the file your "
            f"RAG + SLM pipeline repo exports. See eval/predictions.example.json for the schema."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def build_dataset(testset: list[dict], predictions: list[dict]) -> EvaluationDataset:
    predictions_by_id = {p["id"]: p for p in predictions}

    missing = [item["id"] for item in testset if item["id"] not in predictions_by_id]
    if missing:
        raise ValueError(f"Predictions file is missing entries for ids: {missing}")

    samples = []
    for item in testset:
        pred = predictions_by_id[item["id"]]
        samples.append(
            SingleTurnSample(
                user_input=item["question"],
                retrieved_contexts=pred["contexts"],
                response=pred["answer"],
                reference=item["reference"],
            )
        )
    return EvaluationDataset(samples=samples)


def build_judge():
    judge_llm = ChatOllama(
        base_url=config.OLLAMA_JUDGE_BASE_URL,
        model=config.OLLAMA_JUDGE_MODEL,
        temperature=config.JUDGE_TEMPERATURE,
    )
    judge_embeddings = HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL)
    return judge_llm, judge_embeddings


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Gaudí RAG + SLM pipeline outputs with ragas.")
    parser.add_argument(
        "--predictions",
        type=Path,
        default=config.PREDICTIONS_PATH,
        help="Path to the predictions JSON exported by the RAG + SLM pipeline repo.",
    )
    args = parser.parse_args()

    print(f"Judge LLM: {config.OLLAMA_JUDGE_MODEL} via Ollama at {config.OLLAMA_JUDGE_BASE_URL}")
    print(f"Judge embeddings: {config.EMBEDDING_MODEL} (local)")
    print(f"Testset: {config.TESTSET_PATH}")
    print(f"Predictions: {args.predictions}\n")

    testset = load_json(config.TESTSET_PATH)
    predictions = load_json(args.predictions)
    dataset = build_dataset(testset, predictions)

    judge_llm, judge_embeddings = build_judge()
    metrics = [Faithfulness(), AnswerRelevancy(), ContextPrecision(), ContextRecall()]

    print(f"Running ragas evaluation over {len(dataset)} Gaudí questions...")
    result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=judge_llm,
        embeddings=judge_embeddings,
    )

    print("\n=== Ragas scores (Gaudí RAG + SLM pipeline) ===")
    print(result)

    config.RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = config.RESULTS_DIR / f"eval_{timestamp}.csv"
    result.to_pandas().to_csv(csv_path, index=False)
    print(f"\nPer-question results saved to {csv_path}")


if __name__ == "__main__":
    main()
