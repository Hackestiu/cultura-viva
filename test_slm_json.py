"""
Integration test for the Structured Language Model (SLM) using Qwen2.5.
This test combines the knowledge base lookup with the SLM to verify that the model responds faithfully to the curated entry, without relying on RAG (Retrieval-Augmented Generation).
The test simulates a user question and image labels, retrieves the relevant context from the knowledge base, and sends it to the SLM for a response.
Usage:
    python3 test_slm_json.py

"""
from typing import Optional
from llama_cpp import Llama
from knowledge_base_lookup import get_context_from_labels, load_knowledge_base

SLM_MODEL_PATH = "./models/qwen2.5-1.5b-instruct-q4_k_m.gguf"

# tests
USER_QUESTION = "why the Sagrada Família has its specific height?"
MOCK_IMAGE_LABELS = ["basílica de la sagrada família (95% confidence)"]

_llm = None


def _get_llm() -> Llama:
    """Get the Llama model instance, loading it if necessary."""
    global _llm
    if _llm is None:
        print("[SLM] Loading Qwen2.5...")
        _llm = Llama(model_path=SLM_MODEL_PATH, n_ctx=2048, n_threads=4, verbose=False)
    return _llm


def ask_llm(prompt_text: str, structured_context: Optional[str] = None) -> str:
    """Ask the SLM a question, grounded on structured context if available."""

    system_prompt = (
        "You are a friendly and approachable museum guide chatting with a visitor. "
        "Answer using ONLY the reference facts provided below. "
        "Speak naturally, like you're having a casual conversation, but do not add any outside information. "
        "If the facts don't have the answer, just politely say you don't know. "
        "Keep your response to 1-3 clear sentences."
    )

    user_parts: list[str] = []
    if structured_context:
        user_parts.append(f"Reference facts:\n{structured_context}")
    user_parts.append(f"Question: {prompt_text}")
    user_message = "\n\n".join(user_parts)

    print("=" * 60)
    print("MESSAGE SENT TO THE SLM:")
    print("=" * 60)
    print(f"[system]\n{system_prompt}\n\n[user]\n{user_message}")
    print("=" * 60 + "\n")

    llm = _get_llm()
    output = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        max_tokens=200,
        temperature=0.2,
    )
    return output["choices"][0]["message"]["content"].strip()


def main() -> None:
    """Main function to run the test for SLM with structured knowledge base context."""
    print("--- TEST: Structured JSON + SLM ---")
    print(f"User question: '{USER_QUESTION}'")
    print(f"Simulated image labels: {MOCK_IMAGE_LABELS}\n")

    kb = load_knowledge_base()
    kb_result = get_context_from_labels(MOCK_IMAGE_LABELS, kb)

    if kb_result:
        print(f"[KB] Matched monument: {kb_result['monument_id']}")
        structured_context = kb_result["context"]
    else:
        print("[KB] No monument matched from image labels.")
        structured_context = None

    llm_response = ask_llm(USER_QUESTION, structured_context)

    print("\n" + "=" * 60)
    print("FINAL RESPONSE FROM THE SLM:")
    print("=" * 60)
    print(llm_response)
    print("=" * 60)


if __name__ == "__main__":
    main()