"""
Audio recording via the Logitech Brio 105 microphone, triggered by the D7 toggle button.
Recordings are saved to RECORDINGS_DIR tagged with the selected personality.

STT: faster-whisper with Gaudí domain optimizations (see transcribe()).
"""

import time
import wave
import re

import numpy as np

from config import (
    MIC_DEVICE,
    MIC_SAMPLE_RATE,
    RECORD_CHUNK_SECONDS,
    RECORD_MAX_SECONDS,
    RECORDINGS_DIR,
    SILENCE_CALIBRATION_SECONDS,
    SILENCE_HANGOVER_SECONDS,
    SILENCE_LEADIN_SECONDS,
    SILENCE_RMS_ABSOLUTE,
    SILENCE_RMS_CEILING,
    SILENCE_RMS_NOISE_FACTOR,
    SILENCE_TRIM_PADDING_SECONDS,
)
from logging_setup import logger

try:
    import sounddevice as sd  # type: ignore[import]
except ModuleNotFoundError:
    sd = None

try:
    from arduino.app_peripherals.microphone import Microphone  # type: ignore[import]
except ModuleNotFoundError:
    Microphone = None


# Encoder window, in seconds. See transcribe().
STT_CHUNK_LENGTH_S = 15

# Gaudí domain vocabulary — hotwords biasing faster-whisper toward terms that
# appear frequently in the audioguide context.
#
# Deliberately short. Every hotword is prepended to the decoder context on each
# window and costs prefill time before a single word is transcribed, so a term
# only earns its place here if _CORRECTIONS below cannot already recover it.
# Terms whose misspelling is predictable (gaudi, park guell, trencadis, cupula,
# facana ...) are fixed for free by canonicalize_domain_entities() instead, and
# terms base.en already gets right (Barcelona, basilica, facade, dragon) need no
# help at all. Note this is an English-only model with an English-only
# vocabulary: accented Catalan has no clean token representation, so it is weak
# bias at full price.
DOMAIN_KEYWORD_ALIASES = [
    "Sagrada Família",
    "Temple Expiatori",
    "Passeig de Gràcia",
    "Eixample",
    "La Pedrera",
    "catenary arch",
    "Viaductes",
]

# Post-transcription corrections: ASR commonly misspells these nouns.
_CORRECTIONS = {
    r"\bsagrada familia\b": "Sagrada Família",
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
    r"\bplaca (de la )?natura\b": "Plaça de la Natura",
    r"\bsala hipostila\b": "Sala Hipòstila",
    r"\bturo (de les )?tres creus\b": "Turó de les Tres Creus",
    r"\bturo 3 creus\b": "Turó de les 3 Creus",
    r"\bfacana (del )?naixement\b": "Façana del Naixement",
    r"\bfacana (de la )?passio\b": "Façana de la Passió",
    r"\bcupula\b": "cúpula",
    r"\bescalinata (del )?drac\b": "Escalinata del drac",
    r"\bpavellons (de )?consergeria\b": "Pavellons de consergeria",
    r"\bcasa museu\b": "Casa Museu",
}


def as_int16(audio: np.ndarray) -> np.ndarray:
    """Normalizes a captured buffer to flat 16-bit PCM, accepting the unsigned 8-bit,
    floating-point and signed 16-bit layouts the different capture backends produce.

    Shared by save() and transcribe() so the samples the model hears are bit-identical
    to the samples on disk: a recording that produced a strange transcription can be
    replayed and will reproduce it.
    """
    audio = np.asarray(audio).reshape(-1)
    if len(audio) == 0:
        return audio.astype(np.int16)

    if audio.dtype == np.uint8:
        return (audio.astype(np.int16) - 128) << 8
    if np.issubdtype(audio.dtype, np.floating):
        peak = float(np.max(np.abs(audio)))
        if peak <= 1.5:  # already normalised to [-1, 1]
            return (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
        return np.clip(audio, -32768, 32767).astype(np.int16)
    return audio.astype(np.int16)


def rms(samples: np.ndarray) -> float:
    """Returns the root-mean-square level of a block of samples, in int16 units (0..32767)."""
    if len(samples) == 0:
        return 0.0
    block = samples.astype(np.float32)
    return float(np.sqrt(np.mean(block * block)))


def silence_threshold(noise_floor: float) -> float:
    """Returns the RMS level below which audio counts as silence, given the room noise
    floor. A block has to be quiet in absolute terms *and* quiet relative to the room,
    so a recording made in a busy plaza still ends instead of running to
    RECORD_MAX_SECONDS -- but never above SILENCE_RMS_CEILING, which keeps a very loud
    room from raising the bar above the visitor's own voice."""
    return min(
        SILENCE_RMS_CEILING,
        max(SILENCE_RMS_ABSOLUTE, noise_floor * SILENCE_RMS_NOISE_FACTOR),
    )


class SilenceGate:
    """Decides, block by block, when a recording has ended by itself.

    The first SILENCE_CALIBRATION_SECONDS of audio measure the room noise floor; from
    then on every block is classified as speech or silence against that floor. The
    recording ends after SILENCE_HANGOVER_SECONDS of continuous silence once the visitor
    has spoken, or after SILENCE_LEADIN_SECONDS if they never do -- a button pressed by
    accident should not hold the whole pipeline open for a minute.

    Consecutive, not cumulative: the pause between two sentences resets the count, so a
    question asked in two parts is captured whole as long as the gap is under the
    hangover.
    """

    def __init__(self, sample_rate: int):
        self.sample_rate = sample_rate
        self.speech_detected = False
        self._calibration_target = int(SILENCE_CALIBRATION_SECONDS * sample_rate)
        self._calibration: list[np.ndarray] = []
        self._calibrated_frames = 0
        self._threshold = float(SILENCE_RMS_ABSOLUTE)
        self._silent_frames = 0

    def feed(self, samples: np.ndarray) -> bool:
        """Consumes one block of int16 samples. Returns True once the recording should stop."""
        if self._calibrated_frames < self._calibration_target:
            self._calibration.append(samples)
            self._calibrated_frames += len(samples)
            if self._calibrated_frames >= self._calibration_target:
                noise_floor = rms(np.concatenate(self._calibration))
                self._threshold = silence_threshold(noise_floor)
                self._calibration = []
                logger.debug(
                    "Silence gate calibrated: noise floor {:.0f} RMS, threshold {:.0f} RMS",
                    noise_floor,
                    self._threshold,
                )
            return False

        if rms(samples) >= self._threshold:
            self.speech_detected = True
            self._silent_frames = 0
            return False

        self._silent_frames += len(samples)
        limit = (
            SILENCE_HANGOVER_SECONDS if self.speech_detected else SILENCE_LEADIN_SECONDS
        )
        return self._silent_frames >= limit * self.sample_rate


def trim_silence(audio: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
    """Crops the silence off both ends of a recording, keeping
    SILENCE_TRIM_PADDING_SECONDS either side of the speech.

    This is the part that is actually paid for downstream: Whisper pads every window to
    a fixed length before the encoder runs, so the room tone between the last word and
    the button press is encoded at the same price as speech. The visitor is silent for a
    moment at both ends of nearly every recording, and cropping it is pure saving on the
    critical path between the question and the answer.

    The noise floor is taken as the 10th percentile of the frame levels, so it adapts to
    the room rather than to a fixed number. Audio with no frame above the threshold is
    returned unchanged: a whispered question is better transcribed in full than cropped
    away to nothing.
    """
    audio = np.asarray(audio).reshape(-1)
    frame = max(1, int(0.02 * sample_rate))  # 20 ms
    if len(audio) <= frame:
        return audio

    frames = audio[: len(audio) - len(audio) % frame].reshape(-1, frame).astype(np.float32)
    levels = np.sqrt(np.mean(frames * frames, axis=1))
    threshold = silence_threshold(float(np.percentile(levels, 10)))

    voiced = np.flatnonzero(levels >= threshold)
    if len(voiced) == 0:
        logger.debug("Silence trim skipped: no frame above {:.0f} RMS", threshold)
        return audio

    padding = int(SILENCE_TRIM_PADDING_SECONDS * sample_rate)
    start = max(0, int(voiced[0]) * frame - padding)
    end = min(len(audio), (int(voiced[-1]) + 1) * frame + padding)
    trimmed = audio[start:end]

    dropped = (len(audio) - len(trimmed)) / sample_rate
    if dropped > 0.05:
        logger.info(
            "Trimmed {:.1f}s of silence ({:.1f}s -> {:.1f}s of audio to transcribe)",
            dropped,
            len(audio) / sample_rate,
            len(trimmed) / sample_rate,
        )
    return trimmed


def build_hotwords() -> str:
    """Returns the domain keyword aliases joined into a single space-separated string for Whisper hotword biasing."""
    return " ".join(DOMAIN_KEYWORD_ALIASES)


def canonicalize_domain_entities(text: str) -> str:
    """Normalizes known ASR misspellings of domain proper nouns and architectural terms in transcribed text (e.g. 'gaudi' to 'Gaudí', 'park guell' to 'Park Güell'), leaving text with no matching pattern unchanged."""
    for pattern, replacement in _CORRECTIONS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text.strip()


class MicrophoneManager:
    def __init__(self):
        """Initializes the manager, configuring the Arduino Microphone peripheral at 16kHz mono if the app_peripherals module is available; recording otherwise falls back to sounddevice."""
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
        return sd is not None or self._mic is not None

    def start(self) -> None:
        if sd is None and self._mic is not None:
            self._mic.start()

    def record_until_stopped(self, is_recording):
        """Captures audio continuously — via sounddevice if available, otherwise via successive
        Microphone.record_wav() chunks — checking the is_recording predicate between chunks and
        stopping once it returns false, the visitor falls silent, or RECORD_MAX_SECONDS is
        reached.

        Silence ends the recording on its own (see SilenceGate), so the visitor does not have
        to reach for D7 to stop it; pressing D7 still works and stops it immediately. Whatever
        silence is left at either end is cropped before returning, so the seconds of room tone
        between the last word and the stop are never handed to Whisper.

        When sounddevice is used the stream is opened at the device's native sample rate
        (MIC_SAMPLE_RATE) and the result is resampled to 16 kHz so that faster-whisper
        always receives audio at its expected rate, regardless of the hardware.

        Returns the captured samples as a 1D int16 numpy array at 16 kHz, or None on error.
        """
        TARGET_RATE = 16000
        chunks = []
        if sd is not None:
            capture_rate = MIC_SAMPLE_RATE
            block_size = int(capture_rate * 0.05)   # ~50 ms blocks
            max_frames = int(RECORD_MAX_SECONDS * capture_rate)
            frames_read = 0
            gate = SilenceGate(capture_rate)

            try:
                with sd.InputStream(
                    device=MIC_DEVICE,
                    samplerate=capture_rate,
                    channels=1,
                    dtype="int16",
                    blocksize=block_size,
                    latency="high",
                ) as stream:
                    while frames_read < max_frames:
                        chunk, overflowed = stream.read(
                            min(block_size, max_frames - frames_read)
                        )
                        if overflowed:
                            logger.warning("ALSA input overflow while recording")
                        samples = np.asarray(chunk, dtype=np.int16).reshape(-1)
                        if len(samples) > 0:
                            chunks.append(samples.copy())
                            frames_read += len(samples)
                            if gate.feed(samples):
                                logger.info(
                                    "Recording stopped on silence after {:.1f}s ({}).",
                                    frames_read / capture_rate,
                                    "speech captured"
                                    if gate.speech_detected
                                    else "nothing was said",
                                )
                                break
                        if not is_recording():
                            break
            except Exception as exc:
                logger.exception("Continuous microphone capture failed: {}", exc)
                return None

            if not chunks:
                return None

            audio = np.concatenate(chunks)

            # Resample to 16 kHz if the hardware runs at a different rate
            if capture_rate != TARGET_RATE:
                try:
                    import soxr  # type: ignore[import]
                    audio_f = audio.astype(np.float32) / 32768.0
                    resampled_f = soxr.resample(audio_f, capture_rate, TARGET_RATE)
                    audio = (resampled_f * 32768.0).astype(np.int16)
                    logger.success(
                        "Resampled mic audio {} Hz -> {} Hz (soxr)",
                        capture_rate,
                        TARGET_RATE,
                    )
                except ImportError:
                    # soxr not available — try scipy
                    try:
                        from scipy.signal import resample_poly  # type: ignore[import]
                        import math as _math
                        g = _math.gcd(capture_rate, TARGET_RATE)
                        audio_f = audio.astype(np.float32)
                        audio_f = resample_poly(audio_f, TARGET_RATE // g, capture_rate // g)
                        audio = np.clip(audio_f, -32768, 32767).astype(np.int16)
                        logger.success(
                            "Resampled mic audio {} Hz -> {} Hz (scipy)",
                            capture_rate,
                            TARGET_RATE,
                        )
                    except ImportError:
                        # Last resort: integer decimation with a simple anti-alias FIR
                        # Works correctly when capture_rate is an exact integer multiple of TARGET_RATE
                        # (e.g. 48000 / 16000 = 3).  For other ratios it still works but is
                        # less accurate — good enough for speech recognition.
                        import math as _math
                        ratio = capture_rate / TARGET_RATE
                        if ratio == int(ratio):
                            n = int(ratio)
                            # Simple n-tap moving-average anti-alias filter before decimation
                            kernel = np.ones(n, dtype=np.float32) / n
                            audio_f = np.convolve(audio.astype(np.float32), kernel, mode="same")
                            audio = audio_f[::n].astype(np.int16)
                        else:
                            # Non-integer ratio: use numpy linear interpolation (crude but functional)
                            old_len = len(audio)
                            new_len = int(old_len * TARGET_RATE / capture_rate)
                            x_old = np.arange(old_len)
                            x_new = np.linspace(0, old_len - 1, new_len)
                            audio = np.interp(x_new, x_old, audio.astype(np.float32)).astype(np.int16)
                        logger.success(
                            "Resampled mic audio {} Hz -> {} Hz (numpy fallback)",
                            capture_rate,
                            TARGET_RATE,
                        )
            return trim_silence(audio, TARGET_RATE)

        elif self._mic is not None:
            # This backend already delivers 16 kHz, so the gate and the trim share its rate.
            gate = SilenceGate(TARGET_RATE)
            elapsed = 0.0
            while elapsed < RECORD_MAX_SECONDS:
                chunk = as_int16(self._mic.record_wav(duration=RECORD_CHUNK_SECONDS))
                chunks.append(chunk)
                elapsed += RECORD_CHUNK_SECONDS
                if gate.feed(chunk):
                    logger.info(
                        "Recording stopped on silence after {:.1f}s ({}).",
                        elapsed,
                        "speech captured" if gate.speech_detected else "nothing was said",
                    )
                    break
                if not is_recording():
                    break
        else:
            return None

        if not chunks:
            return None
        return trim_silence(np.concatenate(chunks), TARGET_RATE)

    @staticmethod
    def save(button_id: str, model_name: str, audio: np.ndarray):
        """Writes raw audio samples to RECORDINGS_DIR as a 16-bit PCM, 16kHz mono WAV file, tagging the filename with a timestamp, button_id, and model_name. Normalizes unsigned 8-bit, floating-point, and signed 16-bit input formats to 16-bit PCM before writing. Returns the path to the written file."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_file = (
            RECORDINGS_DIR / f"recording_{timestamp}_{button_id}-{model_name}.wav"
        )

        audio = np.asarray(audio).reshape(-1)

        logger.debug(
            "Mic buffer: dtype={}, length={}, min={:.2f}, max={:.2f}, mean={:.2f}",
            audio.dtype,
            len(audio),
            float(np.min(audio)) if len(audio) > 0 else 0.0,
            float(np.max(audio)) if len(audio) > 0 else 0.0,
            float(np.mean(audio)) if len(audio) > 0 else 0.0,
        )

        samples = as_int16(audio)

        max_sample = int(np.max(np.abs(samples))) if len(samples) > 0 else 0
        with wave.open(str(out_file), "wb") as wf:
            wf.setnchannels(1)  # Microphone.CHANNELS_MONO
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(16000)  # Microphone.RATE_16K
            wf.writeframes(samples.tobytes())
        logger.success(
            "Audio saved to: {} (button {}, model {!r}, max amplitude: {}/32767, "
            "duration: {:.1f}s)",
            out_file,
            button_id,
            model_name,
            max_sample,
            len(samples) / 16000,
        )
        return out_file

    def _ensure_whisper(self):
        """Loads and caches the WhisperModel on first call, returning it (or None if the
        model directory is missing or faster-whisper is not installed). Subsequent calls
        are a no-op, so this is safe to call from both preload() and transcribe()."""
        if hasattr(self, "_whisper"):
            return self._whisper

        from config import STT_MODEL_PATH

        if not STT_MODEL_PATH.exists():
            logger.warning(
                "faster-whisper model not found at {}. Download it following the "
                "instructions in models/stt/README.md.",
                STT_MODEL_PATH,
            )
            self._whisper = None
            return None

        try:
            from faster_whisper import WhisperModel  # type: ignore[import]

            # int8 quantization + 4 threads: benchmark-validated for Cortex-A53 (UNO Q)
            self._whisper = WhisperModel(
                str(STT_MODEL_PATH),
                device="cpu",
                compute_type="int8",
                cpu_threads=4,
            )
            logger.success(
                "faster-whisper model loaded: {}", STT_MODEL_PATH.name
            )
        except ImportError:
            logger.warning(
                "faster-whisper is not installed. Add 'faster-whisper>=1.0.0' to "
                "requirements.txt and reinstall. Returning empty transcription string."
            )
            self._whisper = None
        except Exception as exc:
            logger.exception("Could not load faster-whisper model: {}", exc)
            self._whisper = None

        return self._whisper

    def preload(self) -> bool:
        """Eagerly loads the STT weights so the first transcription does not pay the
        cold-start cost. Returns True if the model is ready. Safe to call more than once;
        transcribe() still loads on demand if this was never called or failed."""
        return self._ensure_whisper() is not None

    def transcribe(self, audio) -> str:
        """Transcribes a question to text with faster-whisper, biasing recognition toward
        Gaudí domain vocabulary via an initial prompt and hotwords, and canonicalizing
        known misspellings in the result. Lazily loads the WhisperModel on first call.

        Accepts either the captured samples as a numpy array or a path to a WAV file.
        Prefer the array: given a path, faster-whisper imports PyAV, opens the container,
        decodes the PCM and resamples it — rebuilding, on the critical path between the
        user finishing their question and hearing an answer, the very array the caller
        already holds at the right rate and layout. The path form stays for fixtures and
        for re-running a saved recording offline.

        Returns the transcribed text, or an empty string if the model file is missing,
        faster-whisper isn't installed, or transcription fails.
        """
        from config import STT_MODEL_PATH

        if not STT_MODEL_PATH.exists():
            logger.warning(
                "faster-whisper model not found at {}. Download it following the "
                "instructions in models/stt/README.md. Returning empty "
                "transcription string.",
                STT_MODEL_PATH,
            )
            return ""

        if self._ensure_whisper() is None:
            return ""

        # float32 in [-1, 1] at 16 kHz is what faster-whisper decodes a file down to,
        # so handing it that directly skips the decode entirely.
        source = (
            as_int16(audio).astype(np.float32) / 32768.0
            if isinstance(audio, np.ndarray)
            else str(audio)
        )

        try:
            segments, _ = self._whisper.transcribe(
                source,
                language="en",
                beam_size=1,
                temperature=0.0,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500),
                condition_on_previous_text=False,
                # hotwords only: initial_prompt fed the same vocabulary through
                # the same decoder prefix a second time. It was also the weaker
                # of the two here -- condition_on_previous_text=False resets the
                # prompt after every window, so it conditioned only the first.
                hotwords=build_hotwords(),
                # Whisper pads every window to chunk_length seconds before the
                # encoder runs, so a 4 s question otherwise costs the same as a
                # 30 s one. Halving the window halves the encoder input
                # (3000 -> 1500 mel frames). Questions longer than 15 s are not
                # truncated -- they are processed as successive windows.
                chunk_length=STT_CHUNK_LENGTH_S,
                # Timestamp tokens are interleaved with text tokens and then
                # discarded below, so decoding them is wasted work.
                without_timestamps=True,
            )
            raw_text = " ".join(s.text for s in segments).strip()
            text = canonicalize_domain_entities(raw_text)
            logger.success(
                "Transcription: {!r}",
                text[:80] + ("..." if len(text) > 80 else ""),
            )
            return text
        except Exception as exc:
            logger.exception(
                "faster-whisper failed transcribing {}: {}",
                audio if not isinstance(audio, np.ndarray) else f"{len(audio)} samples",
                exc,
            )
            return ""
