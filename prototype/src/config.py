"""Loads model paths and other static settings from config.yaml."""

from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).parent / "config.yaml"

with open(_CONFIG_PATH, "r", encoding="utf-8") as _f:
    _config = yaml.safe_load(_f)

MOCK_MODELS = bool(_config.get("mock", False))

STT_MODEL_PATH = _config["models"]["stt_path"]
SLM_MODEL_PATH = _config["models"]["slm_path"]
TTS_MODEL_PATH = _config["models"]["tts_path"]
OUTPUT_WAV = _config["output"]["wav_path"]
