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
    "semaine_spike":     ("en_GB-semaine-medium", 1),
    "semaine_prudence":  ("en_GB-semaine-medium", 0),
}

PERSONALITY_VOICE: dict[str, str] = {
    "artistic":  "semaine_spike",
    "technical": "libriTTS_r_medium",
    "child":     "semaine_prudence",
}

DEFAULT_VOICE = "libriTTS_r_medium"

_DEFAULT_TTS_MODELS_DIR = MODELS_DIR / "tts"


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

    def play(self, audio_path, bridge=None) -> bool:
        """Plays a .wav file. If bridge is provided, monitors volume via
        Bridge.call("get_volume") during playback so the Modulino knob can
        dynamically adjust volume in real-time while audio is playing.
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
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            last_vol = self._current_volume
            start_time = time.time()
            while proc.poll() is None:
                if time.time() - start_time > 60:
                    proc.kill()
                    print(f"[ERROR] aplay timed out playing {path} (>60s) -- interrupted")
                    return False
                if bridge is not None:
                    try:
                        vol = bridge.call("get_volume")
                        if vol is not None and vol != last_vol:
                            last_vol = vol
                            self.set_volume(vol)
                    except Exception:
                        pass
                time.sleep(0.05)

            if proc.returncode != 0:
                stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
                print(f"[ERROR] aplay failed playing {path}: {stderr.strip()}")
                return False

            print(f"[OK] Played: {path}" + (f" (device: {device})" if device else ""))
            return True
        except FileNotFoundError:
            print("[ERROR] 'aplay' not found on system -- install alsa-utils")
            return False
        except Exception as exc:
            print(f"[ERROR] aplay error playing {path}: {exc}")
            return False

    @staticmethod
    def save_response(audio_bytes: bytes):
        """Saves .wav bytes (e.g. from TTS synthesis) to RESPONSES_DIR with a unique timestamp."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_file = RESPONSES_DIR / f"response_{timestamp}.wav"
        out_file.write_bytes(audio_bytes)
        print(f"[OK] TTS response saved to: {out_file}")
        return out_file

    def synthesize(self, text: str, personality: str | None = None) -> Optional[Path]:
        """Synthesizes text as speech using the voice associated with personality,
        saves the result to RESPONSES_DIR, and returns the path to the saved .wav file,
        or None on error."""
        if not text or not text.strip():
            print("[WARN] AudioPlayer: synthesize called with empty text — skipping.")
            return None

        voice_key = PERSONALITY_VOICE.get(personality, DEFAULT_VOICE) if personality else DEFAULT_VOICE
        wav_bytes = self._synthesize(text, voice_key)
        if wav_bytes is None:
            return None

        return self.save_response(wav_bytes)

    def synthesize_and_play(self, text: str, personality: str | None = None, bridge=None) -> bool:
        """Synthesizes text as speech using the voice associated with personality,
        saves the result to RESPONSES_DIR, and plays it through the configured audio device.
        Switches Bridge state from processing (generating) to playback (speaking) when audio begins.
        Returns True on success, False if text is empty or any step fails.

        :param text:        The text to speak.
        :param personality: 'artistic' | 'technical' | 'child', or None for the default voice.
        :param bridge:      Optional Bridge object to monitor volume and update UI status during playback.
        """
        out_file = self.synthesize(text, personality=personality)
        if out_file is None:
            return False

        if bridge is not None:
            try:
                if not bridge.call("is_processing_active"):
                    print("[INFO] AudioPlayer: Generation was cancelled before playback.")
                    return False
                bridge.call("set_processing_active", False)
                bridge.call("set_playback_active", True)
            except Exception as exc:
                print(f"[WARN] AudioPlayer: failed to set playback active on bridge: {exc}")

        try:
            return self.play(out_file, bridge=bridge)
        finally:
            if bridge is not None:
                try:
                    bridge.call("set_playback_active", False)
                except Exception:
                    pass

    def _synthesize(self, text: str, voice_key: str) -> Optional[bytes]:
        """Returns WAV audio bytes for text spoken in the voice identified by voice_key,
        or None if the voice cannot be loaded or synthesis fails."""
        voice_obj = self._load_voice(voice_key)
        if voice_obj is None:
            return None

        _, speaker_id = _VOICE_REGISTRY[voice_key]
        try:
            from piper import SynthesisConfig  # type: ignore[import]

            cfg = getattr(voice_obj, "config", None)
            length_scale = getattr(cfg, "length_scale", None)
            noise_scale = getattr(cfg, "noise_scale", None)
            noise_w_scale = getattr(cfg, "noise_w_scale", None) or getattr(cfg, "noise_w", None)

            syn_config = SynthesisConfig(
                speaker_id=speaker_id,
                length_scale=length_scale,
                noise_scale=noise_scale,
                noise_w_scale=noise_w_scale,
            )

            buf = BytesIO()
            with wave.open(buf, "wb") as wf:
                # synthesize_wav sets channels/width/rate itself (set_wav_format=True)
                voice_obj.synthesize_wav(text, wf, syn_config=syn_config)

            wav_bytes = buf.getvalue()
            if len(wav_bytes) <= 44:
                print(f"[ERROR] AudioPlayer: synthesis generated empty audio ({len(wav_bytes)} bytes) for voice '{voice_key}'")
                return None

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