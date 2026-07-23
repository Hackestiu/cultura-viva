import sys
import wave
from pywhispercpp.model import Model as WhisperModel
from llama_cpp import Llama
from piper import PiperVoice
from transformers import AutoImageProcessor, MobileNetV2ForImageClassification
from PIL import Image

# set configuration paths for the models
STT_MODEL_PATH = "./models/stt/ggml-small.en-q5_1.bin"

def transcribe(audio_path: str) -> str:
    """Transcribe the given audio file using Whisper.cpp."""
    print(f"[STT] Transcribing {audio_path}...")
    model = WhisperModel(STT_MODEL_PATH)
    segments = model.transcribe(audio_path)
    text = " ".join(segment.text.strip() for segment in segments)
    print(f"[STT] Transcribed text: {text}")
    return text

def main() -> None:
    """Main function to run the speech-to-text (stt)test."""
    if len(sys.argv) < 1:
        print("Usage: python3 pipeline.py <input.wav>")
        sys.exit(1)

    input_wav = sys.argv[1]

    transcribed_text = transcribe(input_wav)
    if not transcribed_text.strip():
        print("No speech detected in the audio file.")
        sys.exit(1)

    print(f"Transcribed text: {transcribed_text}")


if __name__ == "__main__":
    main()