"""Text-to-speech via Piper."""

import wave

from piper import PiperVoice

from config import TTS_MODEL_PATH


def synthesize(text: str, output_path: str) -> None:
    """Synthesize speech from text using Piper and save to a WAV file."""
    print(f"[TTS] Synthesizing speech to {output_path}...")
    voice = PiperVoice.load(TTS_MODEL_PATH)
    with wave.open(output_path, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)
    print(f"[TTS] Done, saved to {output_path}")
