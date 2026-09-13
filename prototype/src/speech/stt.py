"""Speech-to-text via Whisper.cpp, with a mock backend for local dev without a model file."""

from loguru import logger
from pywhispercpp.model import Model as WhisperModel

from config import MOCK_MODELS, STT_MODEL_PATH
from models.mock_stt import transcribe as mock_transcribe


def transcribe(audio_path: str) -> str:
    """Transcribe the given audio file using Whisper.cpp (or the mock backend)."""
    if MOCK_MODELS:
        return mock_transcribe(audio_path)

    logger.info(f"[STT] Transcribing {audio_path}...")
    model = WhisperModel(STT_MODEL_PATH)
    segments = model.transcribe(audio_path)
    text = " ".join(segment.text.strip() for segment in segments)
    logger.info(f"[STT] Transcribed text: {text}")
    return text
