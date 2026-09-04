"""
Audio playback management — TTS synthesized voice responses from the Cultura Viva
pipeline played through 3.5mm jack headphones (or ALSA speaker), with volume
controlled dynamically via the Modulino Knob.

TTS engine: Piper (piper-tts Python library, in-process synthesis via PiperVoice).
Three personality voices are supported (from tts-benchmark pipeline):

    artistic  -> libriTTS_r_medium  (en-US, neutral American English)
    technical -> semaine_spike      (en-GB, male British English)
    child     -> semaine_prudence   (en-GB, female British English)

Voice models (.onnx + .onnx.json) must be placed in python/models/tts/.
See models/tts/README.md for download instructions.

Uses 'aplay' (alsa-utils) and 'amixer' via subprocess for playback and volume.
"""

import inspect
import os
import subprocess
import time
import wave
from io import BytesIO
from pathlib import Path
from typing import Optional

from config import DEFAULT_VOLUME_PERCENT, MODELS_DIR, PLAYBACK_DEVICE, RESPONSES_DIR


# ---------------------------------------------------------------------------
# Voice registry — maps voice keys to (onnx_stem, speaker_id)
# Semaine shares one ONNX pair; speaker IDs are defined by the downloaded JSON.
# ---------------------------------------------------------------------------

_VOICE_REGISTRY: dict[str, tuple[str, Optional[int]]] = {
    "libriTTS_r_medium": ("en_US-libritts_r-medium", None),
    "semaine_spike":     ("en_GB-semaine-medium", 0),
    "semaine_prudence":  ("en_GB-semaine-medium", 1),
}

PERSONALITY_VOICE: dict[str, str] = {
    "artistic":  "libriTTS_r_medium",
    "technical": "semaine_spike",
    "child":     "semaine_prudence",
}

DEFAULT_VOICE = "libriTTS_r_medium"

_DEFAULT_TTS_MODELS_DIR = MODELS_DIR / "tts"


# ---------------------------------------------------------------------------
# Proxy for wave.Wave_write compatible with Piper synthesis
# ---------------------------------------------------------------------------

class _PiperWaveWriterProxy:
    """Proxy around wave.Wave_write providing synthesis configuration attributes
    (speaker_id, length_scale, noise_scale, noise_w, sentence_silence, etc.)
    that certain versions of PiperVoice.synthesize read directly from the wav_file argument,
    while delegating all audio writing methods to the underlying Wave_write instance."""

    def __init__(
        self,
        wf: wave.Wave_write,
        speaker_id: Optional[int] = None,
        length_scale: Optional[float] = None,
        noise_scale: Optional[float] = None,
        noise_w: Optional[float] = None,
        sentence_silence: float = 0.0,
    ):
        self._wf = wf
        self.speaker_id = speaker_id
        self.length_scale = length_scale
        self.noise_scale = noise_scale
        self.noise_w = noise_w
        self.sentence_silence = sentence_silence

    def writeframes(self, data):
        return self._wf.writeframes(data)

    def writeframesraw(self, data):
        return self._wf.writeframesraw(data)

    def getnframes(self):
        return self._wf.getnframes()

    def setnchannels(self, n):
        return self._wf.setnchannels(n)

    def setsampwidth(self, n):
        return self._wf.setsampwidth(n)

    def setframerate(self, n):
        return self._wf.setframerate(n)

    def close(self):
        return self._wf.close()

    def __getattr__(self, name: str):
        if hasattr(self._wf, name):
            return getattr(self._wf, name)
        return None


# ---------------------------------------------------------------------------
# AudioPlayer
# ---------------------------------------------------------------------------

class AudioPlayer:
    def __init__(self):
        self._device = PLAYBACK_DEVICE or "default"
        self._current_volume = DEFAULT_VOLUME_PERCENT
        self._tts_models_dir = _DEFAULT_TTS_MODELS_DIR
        self._voices: dict[str, object] = {}

    def _resolve_device(self):
        """Returns the ALSA device string for aplay (-D flag)."""
        return self._device or "default"

    def set_volume(self, volume_percent: int) -> bool:
        """Sets the system audio output volume, clamped to [0, 100].
        Always returns True; if no ALSA mixer control accepts the value, the
        level is tracked in software only."""
        clamped = max(0, min(100, int(volume_percent)))
        self._current_volume = clamped

        mixer_controls = ["Master", "Headphone", "Speaker", "PCM"]
        success = False

        for ctl in mixer_controls:
            cmd = ["amixer", "-q", "set", ctl, f"{clamped}%"]
            try:
                res = subprocess.run(cmd, capture_output=True, timeout=2)
                if res.returncode == 0:
                    success = True
            except Exception:
                pass

        print(f"[OK] Volume set to: {clamped}%" + ("" if success else " (software tracked)"))
        return True

    @property
    def current_volume(self) -> int:
        return self._current_volume

    def play(self, audio_path) -> bool:
        """Plays a .wav file synchronously (blocking).
        Returns True if played successfully, False otherwise."""
        path = Path(audio_path)
        if not path.exists():
            print(f"[ERROR] Audio file not found: {path}")
            return False

        device = self._resolve_device()
        cmd = ["aplay", "-q"]
        if device and device != "default":
            cmd += ["-D", device]
        cmd.append(str(path))

        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
            print(f"[OK] Played: {path}" + (f" (device: {device})" if device else ""))
            return True
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode(errors="replace") if exc.stderr else ""
            print(f"[ERROR] aplay failed playing {path}: {stderr.strip()}")
            return False
        except subprocess.TimeoutExpired:
            print(f"[ERROR] aplay timed out playing {path} (>60s) -- interrupted")
            return False
        except FileNotFoundError:
            print("[ERROR] 'aplay' not found on system -- install alsa-utils")
            return False

    @staticmethod
    def save_response(audio_bytes: bytes):
        """Saves .wav bytes (e.g. from TTS synthesis) to RESPONSES_DIR with a unique timestamp."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_file = RESPONSES_DIR / f"response_{timestamp}.wav"
        out_file.write_bytes(audio_bytes)
        print(f"[OK] TTS response saved to: {out_file}")
        return out_file

    def synthesize_and_play(self, text: str, personality: str | None = None) -> bool:
        """Synthesizes text as speech using the voice associated with personality,
        saves the result to RESPONSES_DIR, and plays it through the configured audio device.
        Returns True on success, False if text is empty or any step fails.

        :param text:        The text to speak.
        :param personality: 'artistic' | 'technical' | 'child', or None for the default voice.
        """
        if not text or not text.strip():
            print("[WARN] AudioPlayer: synthesize_and_play called with empty text — skipping.")
            return False

        voice_key = PERSONALITY_VOICE.get(personality, DEFAULT_VOICE) if personality else DEFAULT_VOICE
        wav_bytes = self._synthesize(text, voice_key)
        if wav_bytes is None:
            return False

        out_file = self.save_response(wav_bytes)
        return self.play(out_file)

    def _synthesize(self, text: str, voice_key: str) -> Optional[bytes]:
        """Returns WAV audio bytes for text spoken in the voice identified by voice_key,
        or None if the voice cannot be loaded or synthesis fails."""
        voice_obj = self._load_voice(voice_key)
        if voice_obj is None:
            return None

        _, speaker_id = _VOICE_REGISTRY[voice_key]
        try:
            buf = BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setframerate(voice_obj.config.sample_rate)
                wf.setsampwidth(2)
                wf.setnchannels(1)

                proxy = _PiperWaveWriterProxy(
                    wf,
                    speaker_id=speaker_id,
                    length_scale=None,
                    noise_scale=None,
                    noise_w=None,
                    sentence_silence=0.0,
                )

                # 1. Try synthesize_stream_raw (yields raw PCM byte chunks)
                if hasattr(voice_obj, "synthesize_stream_raw"):
                    try:
                        sig = inspect.signature(voice_obj.synthesize_stream_raw)
                        stream_kwargs = {}
                        if "speaker_id" in sig.parameters and speaker_id is not None:
                            stream_kwargs["speaker_id"] = speaker_id
                        for chunk in voice_obj.synthesize_stream_raw(text, **stream_kwargs):
                            if isinstance(chunk, (bytes, bytearray)):
                                wf.writeframes(chunk)
                    except Exception:
                        pass

                # 2. Fallback: synthesize(text, proxy)
                if wf.getnframes() == 0:
                    try:
                        sig = inspect.signature(voice_obj.synthesize)
                        kwargs = {}
                        if "speaker_id" in sig.parameters and speaker_id is not None:
                            kwargs["speaker_id"] = speaker_id
                        res = voice_obj.synthesize(text, proxy, **kwargs)
                    except TypeError:
                        res = voice_obj.synthesize(text, proxy)

                    if hasattr(res, "__iter__") and not isinstance(res, (bytes, bytearray)):
                        for chunk in res:
                            data = getattr(chunk, "audio_data", chunk)
                            if isinstance(data, (bytes, bytearray)):
                                wf.writeframes(data)

            wav_bytes = buf.getvalue()
            print(f"[OK] AudioPlayer: synthesised {len(wav_bytes)} bytes (voice '{voice_key}').")
            return wav_bytes
        except Exception as exc:
            print(f"[ERROR] AudioPlayer: synthesis failed for voice '{voice_key}': {exc}")
            return None

    def _load_voice(self, voice_key: str) -> Optional[object]:
        """Returns the PiperVoice instance for voice_key,
        or None if the voice is unknown, the model files are missing,
        or piper-tts is not installed."""
        if voice_key in self._voices:
            return self._voices[voice_key]

        entry = _VOICE_REGISTRY.get(voice_key)
        if entry is None:
            print(f"[WARN] AudioPlayer: unknown voice '{voice_key}'. Available: {', '.join(_VOICE_REGISTRY)}")
            return None

        onnx_stem, _ = entry
        onnx_file = self._tts_models_dir / f"{onnx_stem}.onnx"
        json_file  = self._tts_models_dir / f"{onnx_stem}.onnx.json"

        if not onnx_file.is_file():
            print(
                f"[WARN] AudioPlayer: ONNX model not found at {onnx_file}. "
                "Download it following the instructions in models/tts/README.md. "
                "Returning empty audio."
            )
            return None
        if not json_file.is_file():
            print(f"[WARN] AudioPlayer: ONNX config not found at {json_file}.")
            return None

        if not hasattr(self, "_piper_available"):
            try:
                from piper import PiperVoice  # type: ignore[import]
                self._piper_available = True
            except ImportError:
                print(
                    "[WARN] AudioPlayer: piper-tts is not installed. "
                    "Add 'piper-tts>=1.2.0' to requirements.txt and reinstall. "
                    "Returning empty audio."
                )
                self._piper_available = False

        if not self._piper_available:
            return None

        try:
            from piper import PiperVoice  # type: ignore[import]
            print(f"[OK] AudioPlayer: loading voice '{voice_key}' ...")
            voice_obj = PiperVoice.load(str(onnx_file), str(json_file))
            self._voices[voice_key] = voice_obj
            print(f"[OK] AudioPlayer: voice '{voice_key}' loaded ({voice_obj.config.sample_rate} Hz).")
            return voice_obj
        except Exception as exc:
            print(f"[ERROR] AudioPlayer: failed to load voice '{voice_key}': {exc}")
            return None


