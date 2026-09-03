#!/usr/bin/env python3
"""
CulturaViva Benchmark Runner for Arduino UNO Q (ARM64 Debian).

Runs the 38 curated Gaudí test questions through on-device llama-cpp-python,
measures inference latency and token generation speed on the ARM Cortex-A53 cores,
and outputs a predictions JSON file formatted for Ragas evaluation.
"""

import argparse
import json
import time
from pathlib import Path
from llama_cpp import Llama
from gaudi_knowledge_store import GaudiKnowledgeStore

DEFAULT_MODEL_PATH = "models/qwen2.5-1.5b-instruct-q4_k_m.gguf"
DEFAULT_TESTSET_PATH = "testset.json"
DEFAULT_OUTPUT_PATH = "predictions_arduino.json"

SYSTEM_INSTRUCTIONS = (
    "You are CulturaViva, an audio guide for Antoni Gaudi's monuments in Barcelona. "
    "Answer the visitor's question accurately and concisely, using only the context below. "
    "If the context does not contain the answer, say you are not sure rather than guessing."
)


def build_prompt(context: str, question: str) -> str:
    return f"{SYSTEM_INSTRUCTIONS}\n\nContext:\n{context}\n\nQuestion: {question}\nAnswer:"


def main():
    parser = argparse.ArgumentParser(description="Run SLM benchmark on Arduino UNO Q")
    parser.add_argument("--model", default=DEFAULT_MODEL_PATH, help="Path to GGUF model file")
    parser.add_argument("--testset", default=DEFAULT_TESTSET_PATH, help="Path to testset.json")
    parser.add_argument("--output", default=None, help="Output JSON path for predictions")
    parser.add_argument("--n-threads", type=int, default=4, help="CPU threads (default: 4 for UNO Q Cortex-A53)")
    parser.add_argument("--n-ctx", type=int, default=2048, help="Context window size (default: 2048)")
    parser.add_argument("--max-tokens", type=int, default=128, help="Max generated tokens (default: 128)")
    parser.add_argument("--temperature", type=float, default=0.1, help="Inference temperature (default: 0.1)")
    args = parser.parse_args()

    model_path = Path(args.model)
    testset_path = Path(args.testset)

    if not model_path.exists():
        print(f"Error: Model file not found at {model_path}")
        return

    if not testset_path.exists():
        print(f"Error: Testset file not found at {testset_path}")
        return

    # Derive output name if not specified
    if args.output:
        output_path = Path(args.output)
    else:
        model_name = model_path.stem.lower()
        output_path = Path(f"predictions_arduino_{model_name}.json")

    print(f"============================================================")
    print(f" CulturaViva SLM Benchmark on Arduino UNO Q (ARM64)")
    print(f"============================================================")
    print(f" Model       : {model_path}")
    print(f" Testset     : {testset_path}")
    print(f" Threads     : {args.n_threads}")
    print(f" Context Win : {args.n_ctx}")
    print(f" Max Tokens  : {args.max_tokens}")
    print(f" Output      : {output_path}\n")

    print(f"Loading GGUF model into memory...")
    t0 = time.time()
    llm = Llama(
        model_path=str(model_path),
        n_ctx=args.n_ctx,
        n_threads=args.n_threads,
        n_batch=256,
        verbose=False,
    )
    load_time = time.time() - t0
    print(f"Model loaded in {load_time:.2f}s.")

    print("Initializing knowledge store...")
    store = GaudiKnowledgeStore()

    with open(testset_path, "r", encoding="utf-8") as f:
        testset = json.load(f)

    predictions = []
    total_tokens = 0
    start_total_time = time.time()

    print(f"\nRunning benchmark across {len(testset)} questions...\n")
    for i, item in enumerate(testset, 1):
        q_id = item["id"]
        question = item["question"]
        element_id = item.get("element_id")

        if element_id:
            contexts = [store.context_for_element(element_id)]
        else:
            contexts = [store.context_for_topic(question)]
        context_str = "\n\n---\n\n".join(contexts)

        prompt = build_prompt(context_str, question)

        t_start = time.time()
        output = llm(
            prompt,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            stop=["Question:", "\n\n\n"],
        )
        elapsed = time.time() - t_start

        answer = output["choices"][0]["text"].strip()
        usage = output.get("usage", {})
        completion_tokens = usage.get("completion_tokens", len(answer.split()))
        total_tokens += completion_tokens
        tok_per_sec = completion_tokens / max(elapsed, 0.001)

        print(f"  [{i:2d}/{len(testset):2d}] {elapsed:5.2f}s ({tok_per_sec:4.1f} t/s) | {q_id}")

        predictions.append({
            "id": q_id,
            "question": question,
            "reference": item.get("reference", ""),
            "contexts": contexts,
            "answer": answer,
            "elapsed_s": round(elapsed, 3),
            "tokens": completion_tokens,
        })

    total_wall_time = time.time() - start_total_time
    avg_latency = total_wall_time / len(testset)
    avg_tokens_per_sec = total_tokens / max(total_wall_time, 0.001)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(predictions, f, indent=2, ensure_ascii=False)

    print(f"\n============================================================")
    print(f" Benchmark Complete!")
    print(f"============================================================")
    print(f" Total Questions : {len(testset)}")
    print(f" Total Wall Time : {total_wall_time:.2f}s")
    print(f" Average Latency : {avg_latency:.2f}s / query")
    print(f" Generation Speed: ~{avg_tokens_per_sec:.1f} tokens/s")
    print(f" Predictions Saved: {output_path}")
    print(f" To evaluate on PC: scp debian@arduino:{output_path} eval/ && uv run python main.py eval --predictions eval/{output_path.name}")


if __name__ == "__main__":
    main()
