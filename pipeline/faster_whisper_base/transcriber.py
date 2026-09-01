"""Production adapter for the benchmark's best faster-whisper model."""

from __future__ import annotations

from pathlib import Path

from pipeline.common import DOMAIN_PROMPT, MODELS_DIR, build_hotwords, transcribe_result


class FasterWhisperBaseSTT:
    """Lazy, reusable faster-whisper Base English transcriber.

    The model is loaded once per instance. ``transcribe`` accepts the WAV path
    returned by the microphone module and returns plain text for the pipeline.
    """

    model_name = "faster-whisper:base.en"

    def __init__(
        self,
        model_path: str | Path | None = None,
        *,
        device: str = "cpu",
        compute_type: str = "int8",
        cpu_threads: int = 4,
        beam_size: int = 1,
        initial_prompt: str = DOMAIN_PROMPT,
    ) -> None:
        self.model_path = Path(model_path) if model_path else MODELS_DIR / "faster-whisper-base.en"
        self.device = device
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self.beam_size = beam_size
        self.initial_prompt = initial_prompt
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            if not self.model_path.is_dir():
                raise FileNotFoundError(
                    f"faster-whisper model not found at {self.model_path}. "
                    "Download Systran/faster-whisper-base.en into models/."
                )
            self._model = WhisperModel(
                str(self.model_path),
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=self.cpu_threads,
            )
        return self._model

    def transcribe(self, audio_path: str | Path, language: str = "en") -> str:
        """Transcribe a recorded WAV with benchmark-validated settings."""
        segments, _ = self._load().transcribe(
            str(audio_path),
            language=language,
            beam_size=self.beam_size,
            best_of=1,
            temperature=0.0,
            suppress_blank=True,
            without_timestamps=True,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False,
            initial_prompt=self.initial_prompt,
            hotwords=build_hotwords(),
        )
        return transcribe_result(" ".join(segment.text.strip() for segment in segments))