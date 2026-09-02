"""
Audio recording using the Logitech Brio 105 microphone, triggered via Modulino A/B/C
or D7 toggle button. Recordings are saved to RECORDINGS_DIR tagged with the selected personality.

Technical note: The Microphone API exposes record_wav(duration=X) without streaming start/stop.
Variable-length recording is achieved by recording short consecutive chunks (RECORD_CHUNK_SECONDS)
while is_still_held() remains True, then concatenating them into a single .wav file.

STT: faster-whisper with Gaudí domain optimizations (see transcribe()).
"""

import time
import wave
import re

import numpy as np

from config import MIC_DEVICE, RECORD_CHUNK_SECONDS, RECORD_MAX_SECONDS, RECORDINGS_DIR

try:
    from arduino.app_peripherals.microphone import Microphone
except ModuleNotFoundError:
    Microphone = None


# ---------------------------------------------------------------------------
# Gaudí domain vocabulary — used by faster-whisper to bias recognition
# towards terms that appear frequently in the audioguide context.
# ---------------------------------------------------------------------------

DOMAIN_PROMPT = (
    "Cultura Viva audio guide in Barcelona about Antoni Gaudí, Sagrada Família basilica, "
    "Nativity, Passion, and Glory facades, Catalan modernisme architecture, Casa Batlló, "
    "Casa Milà, Park Güell, dragon and salamander sculptures, and trencadís mosaics."
)

DOMAIN_KEYWORD_ALIASES = [
    "Antoni Gaudí", "Gaudí", "Barcelona", "Passeig de Gràcia", "Temple Expiatori",
    "Sagrada Família", "basilica", "facade", "Nativity facade", "Passion facade",
    "Glory facade", "modernisme", "Catalan", "Casa Batlló", "Casa Milà",
    "La Pedrera", "Park Güell", "Eixample", "trencadís", "salamander", "dragon",
    "catenary arch"
]

# Post-transcription corrections: ASR commonly misspells these proper nouns.
_CORRECTIONS = {
    r"\bgaudi\b": "Gaudí",
    r"\bgaudy\b": "Gaudí",
    r"\bcasa batl[óo]\b": "Casa Batlló",
    r"\bcasa batio\b": "Casa Batlló",
    r"\bcasa batlow\b": "Casa Batlló",
    r"\bcasa bortlow\b": "Casa Batlló",
    r"\bcasa mila\b": "Casa Milà",
    r"\bpark guell\b": "Park Güell",
    r"\bparkway\b": "Park Güell",
    r"\btrencadis\b": "trencadís",
    r"\btrincadis\b": "trencadís",
    r"\bmodernism\b": "modernisme",
    r"\bcatalonian\b": "Catalan",
    r"\bdrag on\b": "dragon",
}


def build_hotwords() -> str:
    """Return the shared domain vocabulary for faster-whisper hotword biasing."""
    return " ".join(DOMAIN_KEYWORD_ALIASES)


def canonicalize_domain_entities(text: str) -> str:
    """Normalize common ASR spellings without changing unrelated speech."""
    for pattern, replacement in _CORRECTIONS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text.strip()


# ---------------------------------------------------------------------------
# MicrophoneManager
# ---------------------------------------------------------------------------

class MicrophoneManager:
    def __init__(self):
        self._mic = None
        if Microphone is not None:
            self._mic = Microphone(
                MIC_DEVICE,
                sample_rate=Microphone.RATE_16K,
                channels=Microphone.CHANNELS_MONO,
                buffer_size=Microphone.BUFFER_SIZE_SAFE,
                shared=False,
            )

    @property
    def available(self) -> bool:
        return self._mic is not None

    def start(self) -> None:
        if self._mic is not None:
            self._mic.start()

    def record_while_held(self, is_still_held):
        """Records in chunks of RECORD_CHUNK_SECONDS while is_still_held()
        returns True (up to RECORD_MAX_SECONDS as a safety limit).
        Returns the complete concatenated audio as np.ndarray, or None if empty."""
        if self._mic is None:
            return None

        chunks = []
        elapsed = 0.0
        while elapsed < RECORD_MAX_SECONDS:
            chunk = self._mic.record_wav(duration=RECORD_CHUNK_SECONDS)
            chunks.append(chunk)
            elapsed += RECORD_CHUNK_SECONDS
            if not is_still_held():
                break

        if not chunks:
            return None
        return np.concatenate(chunks)

    @staticmethod
    def save(button_id: str, model_name: str, audio: np.ndarray):
        """Saves audio to RECORDINGS_DIR as a valid WAV file (16-bit PCM, 16 kHz mono),
        tagged with button/model identifier in the filename.
        Writing a proper WAV header is required so that Whisper (pywhispercpp)
        can read the file -- raw PCM bytes would silently produce empty transcriptions."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_file = RECORDINGS_DIR / f"recording_{timestamp}_{button_id}-{model_name}.wav"
        samples = audio.astype(np.int16)
        with wave.open(str(out_file), "wb") as wf:
            wf.setnchannels(1)       # mono (Microphone.CHANNELS_MONO)
            wf.setsampwidth(2)       # 16-bit = 2 bytes
            wf.setframerate(16000)   # 16 kHz (Microphone.RATE_16K)
            wf.writeframes(samples.tobytes())
        print(f"[OK] Audio saved to: {out_file} (button {button_id}, model '{model_name}')")
        return out_file

    def transcribe(self, audio_path) -> str:
        """Transcribes a recorded .wav file using faster-whisper.
        Returns the transcribed text as a string, or '' if the model is unavailable.

        Optimizations applied (from stt-benchmark pipeline):
        - compute_type='int8', cpu_threads=4  (Cortex-A53 tuned)
        - beam_size=1, temperature=0.0        (greedy — faster, more deterministic)
        - vad_filter=True                     (removes silence, reduces hallucinations)
        - initial_prompt=DOMAIN_PROMPT        (biases ASR to Gaudí vocabulary)
        - hotwords=build_hotwords()           (domain keyword list)
        - canonicalize_domain_entities()      (post-correction of ASR spelling errors)

        The faster-whisper model is loaded lazily on the first call and reused thereafter.
        Does not alter record_while_held() or save().
        """
        from config import STT_MODEL_PATH

        if not STT_MODEL_PATH.exists():
            print(
                f"[WARN] faster-whisper model not found at {STT_MODEL_PATH}. "
                "Download it following the instructions in models/stt/README.md. "
                "Returning empty transcription string."
            )
            return ""

        # Lazy load model instance
        if not hasattr(self, "_whisper"):
            try:
                from faster_whisper import WhisperModel

                # int8 quantization + 4 threads: benchmark-validated for Cortex-A53 (UNO Q)
                self._whisper = WhisperModel(
                    str(STT_MODEL_PATH),
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=4,
                )
                print(f"[OK] faster-whisper model loaded: {STT_MODEL_PATH.name}")
            except ImportError:
                print(
                    "[WARN] faster-whisper is not installed. "
                    "Add 'faster-whisper>=1.0.0' to requirements.txt and reinstall. "
                    "Returning empty transcription string."
                )
                self._whisper = None

        if self._whisper is None:
            return ""

        try:
            # Greedy search + VAD + domain biasing (from stt-benchmark pipeline)
            segments, _ = self._whisper.transcribe(
                str(audio_path),
                language="en",
                beam_size=1,
                temperature=0.0,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500),
                condition_on_previous_text=False,
                initial_prompt=DOMAIN_PROMPT,
                hotwords=build_hotwords(),
            )
            raw_text = " ".join(s.text for s in segments).strip()
            text = canonicalize_domain_entities(raw_text)
            print(f"[OK] Transcription: '{text[:80]}{'...' if len(text) > 80 else ''}'")
            return text
        except Exception as exc:
            print(f"[ERROR] faster-whisper failed transcribing {audio_path}: {exc}")
            return ""
