"""Production adapter for whisper.cpp Base English Q5_1."""

from __future__ import annotations

from pathlib import Path

from pipeline.common import DOMAIN_PROMPT, MODELS_DIR, transcribe_result


class WhisperCppBaseQ5_1STT:
    """Lazy, reusable native whisper.cpp transcriber for the UNO Q target."""

    model_name = "whisper.cpp:base.en-q5_1"

    def __init__(
        self,
        model_path: str | Path | None = None,
        *,
        cpu_threads: int = 2,
        initial_prompt: str = DOMAIN_PROMPT,
    ) -> None:
        self.model_path = Path(model_path) if model_path else MODELS_DIR / "ggml-base.en-q5_1.bin"
        self.cpu_threads = cpu_threads
        self.initial_prompt = initial_prompt
        self._model = None

    def _load(self):
        if self._model is None:
            from pywhispercpp.model import Model

            if not self.model_path.is_file():
                raise FileNotFoundError(
                    f"whisper.cpp model not found at {self.model_path}. "
                    "Download ggml-base.en-q5_1.bin into models/."
                )
            self._model = Model(
                str(self.model_path),
                n_threads=self.cpu_threads,
                print_progress=False,
                print_realtime=False,
                print_timestamps=False,
            )
        return self._model

    def transcribe(self, audio_path: str | Path, language: str = "en") -> str:
        """Transcribe a recorded WAV using native greedy decoding."""
        import _pywhispercpp

        segments = self._load().transcribe(
            str(audio_path),
            language=language,
            strategy=_pywhispercpp.WHISPER_SAMPLING_GREEDY,
            initial_prompt=self.initial_prompt,
        )
        return transcribe_result(" ".join(segment.text.strip() for segment in segments))