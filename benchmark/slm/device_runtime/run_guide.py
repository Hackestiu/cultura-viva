#!/usr/bin/env python3
"""CulturaViva runtime for the Arduino UNO Q.

Takes the element id from the upstream CV model (or free text for general
questions), looks up grounding context, and generates a short spoken answer with
the local SLM in the guide personality you pick.

The prompt is not defined here -- `guide_prompt.build_messages` is the same
function the board's `main.py` calls, and the knowledge rendering is the same
`knowledge_store.KnowledgeStore`. Both were copied into this bundle by
`scripts/prepare.py` from `arduino/python/`. See `device_runtime/README.md`.
"""

import argparse
import json
from pathlib import Path

from llama_cpp import Llama

from guide_prompt import PERSONALITIES, build_messages
from knowledge_store import KnowledgeStore

BUNDLE_DIR = Path(__file__).resolve().parent
BUNDLE_CONFIG = BUNDLE_DIR / "bundle_config.json"


def load_bundle_config() -> dict:
    """Sampling parameters and the default model, generated from config.yaml.

    Read from disk rather than hardcoded so the bundle cannot drift from the
    benchmark it is supposed to reproduce.
    """
    if not BUNDLE_CONFIG.exists():
        raise SystemExit(
            f"{BUNDLE_CONFIG.name} is missing. Re-run "
            "`uv run python main.py prepare --export-arduino` to rebuild the bundle."
        )
    return json.loads(BUNDLE_CONFIG.read_text(encoding="utf-8"))


def main():
    cfg = load_bundle_config()
    inference = cfg["inference"]

    parser = argparse.ArgumentParser(description="CulturaViva audio guide runtime")
    parser.add_argument("--model", default=str(BUNDLE_DIR / "models" / cfg["default_gguf"]),
                        help="Path to the GGUF model file")
    parser.add_argument("--element-id", default=None, help="Element id from the CV model, if any")
    parser.add_argument("--personality", default=PERSONALITIES[0], choices=list(PERSONALITIES),
                        help="Guide personality")
    parser.add_argument("--n-threads", type=int, default=inference["threads"],
                        help="CPU threads (the UNO Q has 4 Cortex-A53 cores)")
    args = parser.parse_args()

    print(f"Loading {args.model} on Qualcomm QRB2210 (ARM Cortex-A53)...")
    llm = Llama(
        model_path=args.model,
        n_ctx=inference["context_window"],
        n_threads=args.n_threads,
        n_batch=inference["batch_size"],
        verbose=False,
    )
    store = KnowledgeStore()
    print(f"Model and knowledge store loaded. Guide: {args.personality}\n")

    element_id = args.element_id
    while True:
        try:
            if element_id is None:
                element_id = input("Element id (blank for a general question): ").strip() or None
            query = input("Visitor question (or 'exit'): ").strip()
            if query.lower() in ("exit", "quit"):
                break

            # Element ids come from vision and are looked up directly; a free-text
            # question falls back to keyword search. The device has no fallback --
            # get_kg_context returns "" for an unknown element -- so it is opted
            # into here at the call site rather than hidden inside the store.
            context = ""
            if element_id:
                context = store.context_for_element(element_id)
            if not context:
                context = store.context_for_topic(query)

            messages = build_messages(
                question=query,
                element=element_id,
                personality=args.personality,
                kg_context=context,
                element_name=store.display_name(element_id),
            )

            print("\nCulturaViva: ", end="", flush=True)
            for chunk in llm.create_chat_completion(
                messages=messages,
                max_tokens=inference["max_tokens"],
                temperature=inference["temperature"],
                repeat_penalty=inference["repeat_penalty"],
                stop=inference["stop"],
                stream=True,
            ):
                delta = chunk["choices"][0].get("delta", {})
                if "content" in delta:
                    print(delta["content"], end="", flush=True)
            print("\n" + "-" * 50 + "\n")

            element_id = None
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
