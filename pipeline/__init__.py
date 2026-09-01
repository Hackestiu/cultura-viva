"""Production-ready STT adapters extracted from the benchmark."""

from .faster_whisper_base import FasterWhisperBaseSTT
from .whisper_cpp_base_q5_1 import WhisperCppBaseQ5_1STT

__all__ = ["FasterWhisperBaseSTT", "WhisperCppBaseQ5_1STT"]