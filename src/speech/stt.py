"""Speech-to-text via Whisper.cpp."""

from pywhispercpp.model import Model as WhisperModel

from config import STT_MODEL_PATH


def transcribe(audio_path: str) -> str:
    """Transcribe the given audio file using Whisper.cpp."""
    print(f"[STT] Transcribing {audio_path}...")
    model = WhisperModel(STT_MODEL_PATH)
    segments = model.transcribe(audio_path)
    text = " ".join(segment.text.strip() for segment in segments)
    print(f"[STT] Transcribed text: {text}")
    return text
