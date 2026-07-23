from typing import Any, Optional
import re
from llama_cpp import Llama
from retrieve import RagIndex

SLM_MODEL_PATH = "./models/qwen2.5-1.5b-instruct-q4_k_m.gguf"
RAG_INDEX_PATH = "rag_index.npz"

# tests
USER_QUESTION = "When was the construction of Sagrada Familia started and who designed it?"
MOCK_IMAGE_LABELS = ["basílica de la sagrada família (95% confidence)"]

_llm = None


def _get_llm() -> Llama:
    """Get the Llama model instance, loading it if necessary."""
    global _llm
    if _llm is None:
        print("[SLM] Loading Qwen2.5...")
        _llm = Llama(model_path=SLM_MODEL_PATH, n_ctx=2048, n_threads=4, verbose=False)
    return _llm


def _clean_label(label: str) -> str:
    """Strips the confidence suffix, e.g. 'X (95% confidence)' -> 'X'."""
    return re.sub(r"\s*\(.*?\)\s*$", "", label).strip()


def ask_llm(
    prompt_text: str,
    image_labels: Optional[list[str]] = None,
    rag_docs: Optional[list[dict[str, Any]]] = None,
) -> str:
    """Ask the SLM a question and return the response."""

    system_prompt = (
        "You are a helpful museum guide. Answer the user's question using ONLY the "
        "knowledge base context and visual context provided below. Do not mix facts "
        "from different parts of the context unless they clearly refer to the same event. "
        "If the context does not contain the answer, say you don't know. "
        "Do not repeat the visual context labels verbatim, do not use hashtags or social media formats. "
        "Answer in 1-3 sentences."
    )

    user_parts = []

    if rag_docs:
        context_lines = [f"- {doc['text']}" for doc in rag_docs]
        user_parts.append("Knowledge base context:\n" + "\n".join(context_lines))

    if image_labels:
        clean_labels = [_clean_label(label) for label in image_labels]
        user_parts.append(f"Visual context: the image shows {', '.join(clean_labels)}.")

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
        temperature=0.2,  # baja para respuestas factuales con RAG
    )
    reply = output["choices"][0]["message"]["content"].strip()
    return reply


def main() -> None:
    """Main function to run the test for RAG + SLM integration."""

    print("--- TEST: RAG + SLM ---")
    print(f"User question: '{USER_QUESTION}'")
    print(f"Simulated image labels: {MOCK_IMAGE_LABELS}\n")

    print("[RAG] Loading index and starting query...")
    rag = RagIndex(RAG_INDEX_PATH)

    # use the cleaned label (not the raw "(95% confidence)" string) to anchor the search
    clean_labels = [_clean_label(label) for label in MOCK_IMAGE_LABELS]
    search_query = f"{' '.join(clean_labels)} {USER_QUESTION}" if clean_labels else USER_QUESTION

    rag_docs = rag.retrieve(search_query, top_k=2)

    llm_response = ask_llm(USER_QUESTION, MOCK_IMAGE_LABELS, rag_docs)

    print("\n" + "=" * 60)
    print("FINAL RESPONSE FROM THE SLM:")
    print("=" * 60)
    print(llm_response)
    print("=" * 60)


if __name__ == "__main__":
    main()