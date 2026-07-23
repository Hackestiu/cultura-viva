import sys
import wave
import torch
from pywhispercpp.model import Model as WhisperModel
from llama_cpp import Llama
from piper import PiperVoice
from transformers import AutoImageProcessor, MobileNetV2ForImageClassification
from PIL import Image
from retrieve import RagIndex
from typing import Any, Optional

# set configuration paths for the models
STT_MODEL_PATH = "./models/stt/ggml-small.en.bin"
SLM_MODEL_PATH = "./models/qwen2.5-1.5b-instruct-q4_k_m.gguf"
TTS_MODEL_PATH = "./models/tts/en_US-lessac-medium.onnx"
VISION_MODEL_NAME = "google/mobilenet_v2_1.0_224"
OUTPUT_WAV = "output.wav"


def transcribe(audio_path: str) -> str:
    """Transcribe the given audio file using Whisper.cpp."""
    print(f"[STT] Transcribing {audio_path}...")
    model = WhisperModel(STT_MODEL_PATH)
    segments = model.transcribe(audio_path)
    text = " ".join(segment.text.strip() for segment in segments)
    print(f"[STT] Transcribed text: {text}")
    return text


def classify_image(image_path: str, confidence_threshold: int=0.15, max_labels: int=3) -> list[str]:
    """Classify the given image and return the top labels."""
    print(f"[VISION] Classifying {image_path}...")
    processor = AutoImageProcessor.from_pretrained(VISION_MODEL_NAME)
    model = MobileNetV2ForImageClassification.from_pretrained(VISION_MODEL_NAME)

    image = Image.open(image_path).convert("RGB")
    inputs = processor(images=image, return_tensors="pt")
    outputs = model(**inputs)
    logits = outputs.logits

    probs = torch.softmax(logits[0], dim=0) #tensor of probabilities
    top_probs, top_indices = probs.topk(max_labels) #values, indices

    results = []
    for prob, idx in zip(list(top_probs), list(top_indices)):
        if prob >= confidence_threshold:
            label = model.config.id2label[idx]
            results.append(f"{label} ({prob*100:.0f}% confidence)")

    if not results:
        best_idx = top_indices[0].item()
        results = [f"{model.config.id2label[best_idx]} (uncertain)"]

    print(f"[VISION] Top labels: {results}")
    return results


def ask_slm(prompt_text: str, image_labels: Optional[list[str]] = None, rag_docs: Optional[list[dict[str, Any]]] = None) -> str:
    """Ask the SLM a question and return the response."""
    print("[SLM] Loading Qwen2.5 and generating response...")

    # RAG context
    rag_context = ""
    if rag_docs:
        context_lines = [f"- {doc['text']}" for doc in rag_docs]
        rag_context = "Knowledge base context:\n" + "\n".join(context_lines) + "\n\n"

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
    full_prompt = f"{system_prompt}\n\n{rag_context}{vision_context}User question: {prompt_text}\n\nAnswer:"

    print(f"[SLM] Full prompt sent:\n{full_prompt}")

    llm = Llama(
        model_path=SLM_MODEL_PATH,
        n_ctx=2048,
        n_threads=4,
        verbose=False
    )

    output = llm(full_prompt, max_tokens=200, stop=["</s>"])
    reply = output["choices"][0]["text"].strip()
    print(f"[SLM] Response: {reply}")
    return reply

def synthesize(text: str, output_path: str) -> None:
    """Synthesize speech from text using Piper and save to a WAV file."""
    print(f"[TTS] Synthesizing speech to {output_path}...")
    voice = PiperVoice.load(TTS_MODEL_PATH)
    with wave.open(output_path, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)
    print(f"[TTS] Done, saved to {output_path}")


def main() -> None:
    """Main function to run the full pipeline: STT -> VISION -> RAG -> LLM -> TTS."""
    if len(sys.argv) < 2:
        print("Usage: python3 pipeline.py <input.wav> [image.jpg]")
        sys.exit(1)

    input_wav = sys.argv[1]
    image_path = sys.argv[2] if len(sys.argv) > 2 else None

    # stt
    transcribed_text = transcribe(input_wav)
    if not transcribed_text.strip():
        print("No speech detected in the audio file.")
        sys.exit(1)

    # image classification
    image_labels = classify_image(image_path) if image_path else None

    # RAG context retrieval
    print("[RAG] Querying vector index...")
    rag = RagIndex("rag_index.npz")

    # combine RAG search query with transcribed text and image labels
    search_query = transcribed_text
    if image_labels:
        search_query = f"{' '.join(image_labels)} {transcribed_text}"

    rag_docs = rag.retrieve(search_query, top_k=2)

    # generate response from the SLM
    llm_response = ask_slm(transcribed_text, image_labels, rag_docs)

    # tts
    synthesize(llm_response, OUTPUT_WAV)

    print("\n--- Pipeline complete ---")
    print(f"Transcribed text: {transcribed_text}")
    print(f"RAG contexts used: {len(rag_docs)}")
    print(f"SLM response:     {llm_response}")


if __name__ == "__main__":
    main()