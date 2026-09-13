"""Small language model prompting via llama.cpp (Qwen2.5), with a mock backend for local dev without a model file."""

from typing import Optional

from llama_cpp import Llama
from loguru import logger

from config import MOCK_MODELS, SLM_MODEL_PATH
from models.mock_slm import ask_slm as mock_ask_slm

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful museum guide. "
    "Answer the user's question directly using the provided visual context. "
    "Do not repeat the visual context labels in your answer, do not use hashtags or social media formats."
)


def ask_slm(
    prompt_text: str,
    image_labels: Optional[list[str]] = None,
    system_prompt: Optional[str] = None,
    kg_context: Optional[str] = None,
) -> str:
    """Ask the SLM a question and return the response (or a mock response).

    `system_prompt` and `kg_context` are injectable so callers (e.g. the
    orchestrator) can pick a personality-specific prompt and attach
    pre-generated knowledge-graph facts about the detected element.
    """
    if MOCK_MODELS:
        return mock_ask_slm(prompt_text, image_labels, system_prompt, kg_context)

    logger.info("[SLM] Loading Qwen2.5 and generating response...")

    # computer vision model context
    vision_context = ""
    if image_labels:
        vision_context = f"The image shows: {', '.join(image_labels)}.\n\n"

    if system_prompt is None:
        system_prompt = DEFAULT_SYSTEM_PROMPT

    kg_block = f"Background knowledge:\n{kg_context}\n\n" if kg_context else ""

    # final prompt to send to the SLM
    full_prompt = f"{system_prompt}\n\n{vision_context}{kg_block}User question: {prompt_text}\n\nAnswer:"

    logger.debug(f"[SLM] Full prompt sent:\n{full_prompt}")

    llm = Llama(
        model_path=SLM_MODEL_PATH,
        n_ctx=2048,
        n_threads=4,
        verbose=False
    )

    output = llm(full_prompt, max_tokens=200, stop=["</s>"])
    reply = output["choices"][0]["text"].strip()
    logger.info(f"[SLM] Response: {reply}")
    return reply
