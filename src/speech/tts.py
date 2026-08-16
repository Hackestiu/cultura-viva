"""Text-to-speech via Piper, with a mock backend for local dev without a model file."""

import wave
from pathlib import Path

from loguru import logger
from piper import PiperVoice

from config import MOCK_MODELS, TTS_MODEL_PATH
from models.mock_tts import synthesize as mock_synthesize


def synthesize(text: str, output_path: str) -> None:
    """Synthesize speech from text using Piper (or the mock backend) and save to a WAV file."""
    if MOCK_MODELS:
        mock_synthesize(text, output_path)
        return

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"[TTS] Synthesizing speech to {output_path}...")
    voice = PiperVoice.load(TTS_MODEL_PATH)
    with wave.open(output_path, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)
    logger.info(f"[TTS] Done, saved to {output_path}")
