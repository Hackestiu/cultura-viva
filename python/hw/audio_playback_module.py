"""
Audio playback management -- designed for TTS synthesized voice responses
from the Cultura Viva pipeline played through 3.5mm jack headphones (or ALSA speaker),
with volume controlled dynamically via the Modulino Knob.

Uses 'aplay' (alsa-utils) and 'amixer' via subprocess.
"""

import subprocess
import time
from pathlib import Path

from config import DEFAULT_VOLUME_PERCENT, PLAYBACK_DEVICE, RESPONSES_DIR


class AudioPlayer:
    def __init__(self):
        self._device = PLAYBACK_DEVICE or "default"
        self._current_volume = DEFAULT_VOLUME_PERCENT

    def _resolve_device(self):
        """Returns the ALSA device string for aplay (-D flag)."""
        return self._device or "default"

    def set_volume(self, volume_percent: int) -> bool:
        """Sets the system audio output volume percentage (0 - 100%) using amixer.
        Tries common ALSA control names ('Master', 'Headphone', 'Speaker', 'PCM').
        """
        clamped = max(0, min(100, int(volume_percent)))
        self._current_volume = clamped

        # Try setting volume on common ALSA mixer control channels
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

    def synthesize_and_play(self, text: str) -> bool:
        """Synthesizes text to speech with Piper TTS, saves the .wav to RESPONSES_DIR,
        and plays it through 3.5mm jack headphones.
        Returns True if successful, False otherwise.
        """
        from config import TTS_CONFIG_PATH, TTS_MODEL_PATH

        if not TTS_MODEL_PATH.exists():
            print(
                f"[WARN] Piper TTS model not found at {TTS_MODEL_PATH}. "
                "Download it following instructions in audio_playback_module.README.md. "
                "No response will be played."
            )
            return False

        if not TTS_CONFIG_PATH.exists():
            print(
                f"[WARN] Piper TTS config not found at {TTS_CONFIG_PATH}. "
                "Ensure the .onnx.json file is present next to the .onnx model. "
                "No response will be played."
            )
            return False

        if not text.strip():
            print("[WARN] synthesize_and_play: text is empty, nothing to synthesize.")
            return False

        try:
            result = subprocess.run(
                [
                    "piper",
                    "--model", str(TTS_MODEL_PATH),
                    "--config", str(TTS_CONFIG_PATH),
                    "--output_raw",
                ],
                input=text.encode("utf-8"),
                capture_output=True,
                check=True,
                timeout=30,
            )
        except FileNotFoundError:
            print(
                "[ERROR] 'piper' binary not found on system. "
                "Install piper-tts (pip install piper-tts or from official repo)."
            )
            return False
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode(errors="replace") if exc.stderr else ""
            print(f"[ERROR] Piper TTS failed: {stderr.strip()}")
            return False
        except subprocess.TimeoutExpired:
            print("[ERROR] Piper TTS timed out (>30s) — interrupted.")
            return False

        audio_bytes = _pcm_to_wav(result.stdout, sample_rate=22050)
        out_file = self.save_response(audio_bytes)
        return self.play(out_file)


# ---------------------------------------------------------------------------
# Helper function (wraps raw PCM into valid WAV container)
# ---------------------------------------------------------------------------

def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 22050,
                channels: int = 1, sampwidth: int = 2) -> bytes:
    """Wraps raw PCM bytes (int16 little-endian emitted by Piper --output_raw)
    into a valid WAV byte stream that aplay can directly execute."""
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()
