from typing import Optional
from llama_cpp import Llama

SLM_MODEL_PATH = "./models/qwen2.5-1.5b-instruct-q4_k_m.gguf"

#tests
USER_QUESTION = "When was the construction of Sagrada Familia started and who designed it?"
MOCK_IMAGE_LABELS = ["basílica de la sagrada família (95% confidence)"]


def ask_llm(prompt_text: str, image_labels: Optional[list[str]] = None) -> str:
    """Ask the SLM a question and return the response."""

    print("[SLM] Loading Qwen2.5 and generating response...\n")

    # computer vision model context
    vision_context = ""
    if image_labels:
        vision_context = f"The image shows: {', '.join(image_labels)}.\n\n"

    
    system_prompt= (
        "You are a helpful museum guide. "
        "Answer the user's question directly using the provided visual context and knowledge base context. "
        "Do not repeat the visual context labels in your answer, do not use hashtags or social media formats."
    )
    # final prompt to send to the SLM

    full_prompt = f"{system_prompt}\n\n{vision_context}User question: {prompt_text}\n\nAnswer:"
    

    print("=" * 60)
    print("PROMPT SENT TO THE SLM:")
    print("=" * 60)
    print(full_prompt)
    print("=" * 60 + "\n")

    llm = Llama(
        model_path=SLM_MODEL_PATH,
        n_ctx=2048,
        n_threads=4,
        verbose=False
    )

    output = llm(full_prompt, max_tokens=200, stop=["</s>"])
    reply = output["choices"][0]["text"].strip()
    return reply


def main() -> None:
    """Main function to run the test for SLM."""

    print("--- TEST: SLM ---")
    print(f"User question: '{USER_QUESTION}'")
    print(f"Simulated image labels: {MOCK_IMAGE_LABELS}\n")

    # generate response from the slm
    llm_response = ask_llm(USER_QUESTION, MOCK_IMAGE_LABELS)

    # show final response
    print("\n" + "=" * 60)
    print("FINAL RESPONSE FROM THE SLM:")
    print("=" * 60)
    print(llm_response)
    print("=" * 60)


if __name__ == "__main__":
    main()
