#!/usr/bin/env python3
"""CulturaViva benchmark runner for the Arduino UNO Q (ARM64 Debian).

Runs the curated Gaudí test questions through on-device llama-cpp-python, measures
inference latency and token throughput on the Cortex-A53 cores, and writes a
predictions JSON formatted for Ragas.

Like `run_guide.py`, it defines no prompt of its own: `guide_prompt.build_messages`
and `knowledge_store.KnowledgeStore` are the device's, copied into this bundle by
`scripts/prepare.py`. See `device_runtime/README.md`.

Two things to know when comparing these numbers to a PC run:

- **`--personality` is part of the measurement now.** The old version had no
  personality at all, so its answers were not comparable to anything `main.py
  benchmark` produced.
- **`retrieval_top_k` matches the PC run.** The old version retrieved a single
  passage where the PC retrieved three, which made ContextPrecision and
  ContextRecall structurally incomparable between board and host. Retrieval here
  is keyword-based and on the host it is semantic -- that difference is real and
  unavoidable on a board that cannot run sentence-transformers -- but at least the
  number of passages now agrees.
"""

import argparse
import json
import time
from pathlib import Path

from llama_cpp import Llama

from guide_prompt import PERSONALITIES, build_messages
from knowledge_store import KnowledgeStore

BUNDLE_DIR = Path(__file__).resolve().parent
BUNDLE_CONFIG = BUNDLE_DIR / "bundle_config.json"


def load_bundle_config() -> dict:
    if not BUNDLE_CONFIG.exists():
        raise SystemExit(
            f"{BUNDLE_CONFIG.name} is missing. Re-run "
            "`uv run python main.py prepare --export-arduino` to rebuild the bundle."
        )
    return json.loads(BUNDLE_CONFIG.read_text(encoding="utf-8"))


def main():
    cfg = load_bundle_config()
    inference = cfg["inference"]

    parser = argparse.ArgumentParser(description="Run the SLM benchmark on an Arduino UNO Q")
    parser.add_argument("--model", default=str(BUNDLE_DIR / "models" / cfg["default_gguf"]),
                        help="Path to the GGUF model file")
    parser.add_argument("--testset", default=str(BUNDLE_DIR / "testset.json"),
                        help="Path to testset.json")
    parser.add_argument("--output", default=None, help="Output JSON path for predictions")
    parser.add_argument("--personality", default="technical", choices=list(PERSONALITIES),
                        help="Guide personality to benchmark")
    parser.add_argument("--n-threads", type=int, default=inference["threads"],
                        help="CPU threads (the UNO Q has 4 Cortex-A53 cores)")
    parser.add_argument("--top-k", type=int, default=cfg["retrieval_top_k"],
                        help="Passages retrieved per question")
    args = parser.parse_args()

    model_path = Path(args.model)
    testset_path = Path(args.testset)
    if not model_path.exists():
        raise SystemExit(f"Error: model file not found at {model_path}")
    if not testset_path.exists():
        raise SystemExit(f"Error: testset not found at {testset_path}")

    output_path = Path(args.output) if args.output else BUNDLE_DIR / (
        f"predictions_arduino_{model_path.stem.lower()}_{args.personality}.json"
    )

    print(f"Loading {model_path.name} on Qualcomm QRB2210 (ARM Cortex-A53)...")
    load_start = time.time()
    llm = Llama(
        model_path=str(model_path),
        n_ctx=inference["context_window"],
        n_threads=args.n_threads,
        n_batch=inference["batch_size"],
        verbose=False,
    )
    print(f"Model loaded in {time.time() - load_start:.1f}s")

    store = KnowledgeStore()
    testset = json.loads(testset_path.read_text(encoding="utf-8"))

    predictions = []
    total_tokens = 0
    start_total_time = time.time()

    print(f"\nRunning {len(testset)} questions as the {args.personality} guide...\n")
    for i, item in enumerate(testset, 1):
        question = item["question"]
        element_id = item.get("element_id")

        if element_id:
            contexts = [store.context_for_element(element_id)]
        else:
            contexts = store.search(question, k=args.top_k)

        messages = build_messages(
            question=question,
            element=element_id,
            personality=args.personality,
            kg_context="\n\n---\n\n".join(contexts),
            element_name=store.display_name(element_id),
        )

        t_start = time.time()
        output = llm.create_chat_completion(
            messages=messages,
            max_tokens=inference["max_tokens"],
            temperature=inference["temperature"],
            repeat_penalty=inference["repeat_penalty"],
            stop=inference["stop"],
        )
        elapsed = time.time() - t_start

        choice = output["choices"][0]
        answer = (choice.get("message") or {}).get("content", "").strip()
        usage = output.get("usage", {})
        completion_tokens = usage.get("completion_tokens", len(answer.split()))
        total_tokens += completion_tokens

        print(f"  [{i:2d}/{len(testset):2d}] {elapsed:5.2f}s "
              f"({completion_tokens / max(elapsed, 0.001):4.1f} t/s) | {item['id']}")

        predictions.append({
            "id": item["id"],
            "question": question,
            "reference": item.get("reference", ""),
            "contexts": contexts,
            "answer": answer,
            "personality": args.personality,
            "elapsed_s": round(elapsed, 3),
            "tokens": completion_tokens,
            "finish_reason": choice.get("finish_reason"),
        })

    total_wall_time = time.time() - start_total_time
    output_path.write_text(
        json.dumps(predictions, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("\n" + "=" * 60)
    print(" Benchmark complete")
    print("=" * 60)
    print(f" Questions        : {len(testset)}")
    print(f" Total wall time  : {total_wall_time:.2f}s")
    print(f" Average latency  : {total_wall_time / len(testset):.2f}s / query")
    print(f" Generation speed : ~{total_tokens / max(total_wall_time, 0.001):.1f} tokens/s")
    print(f" Predictions      : {output_path}")
    print(f"\n To evaluate on a PC:\n"
          f"   scp debian@<ARDUINO_IP>:{output_path} eval/\n"
          f"   uv run python main.py eval --predictions eval/{output_path.name}")


if __name__ == "__main__":
    main()
