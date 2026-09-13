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

DEFAULT_MODEL_PATH = "models/qwen2.5-1.5b-instruct-q4_k_m.gguf"

SYSTEM_INSTRUCTIONS = (
    "You are CulturaViva, an audio guide for Antoni Gaudi's monuments in Barcelona. "
    "Answer the visitor's question in 2-3 sentences, using only the context provided. "
    "If the context does not contain the answer, say you are not sure rather than guessing."
)


def build_prompt(context: str, question: str) -> str:
    return f"{SYSTEM_INSTRUCTIONS}\n\nContext:\n{context}\n\nVisitor: {question}\nGuide:"


def main():
    parser = argparse.ArgumentParser(description="CulturaViva audio guide runtime")
    parser.add_argument("--model", default=DEFAULT_MODEL_PATH, help="Path to the GGUF model file")
    parser.add_argument("--element-id", default=None, help="Element id from the CV model, if any")
    parser.add_argument("--n-threads", type=int, default=4, help="CPU threads (UNO Q has 4 Cortex-A53 cores)")
    args = parser.parse_args()

    print(f"Loading {args.model} on Qualcomm QRB2210 (ARM Cortex-A53)...")
    llm = Llama(model_path=args.model, n_ctx=2048, n_threads=args.n_threads, n_batch=256, verbose=False)
    store = GaudiKnowledgeStore()
    print("Model and knowledge store loaded.\n")

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

            print("\nCulturaViva: ", end="", flush=True)
            for chunk in llm(prompt, max_tokens=150, temperature=0.2, stream=True):
                print(chunk["choices"][0]["text"], end="", flush=True)
            print("\n" + "-" * 50 + "\n")

            element_id = None
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
