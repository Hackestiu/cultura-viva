"""
Centralized configuration module for the Cultura Viva application running on the Linux MPU.

Defines global path resolutions, directory structures, hardware ALSA/V4L2 identifiers,
and system operational parameters across vision, audio, and AI processing pipelines.
"""

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent

_EXTRA_PATHS = [
    str(APP_DIR / "lib"),
    "/usr/local/lib/python3.13/dist-packages",
    "/usr/local/lib/python3.13/site-packages",
    "/usr/lib/python3/dist-packages",
    "/usr/lib/python3.13/dist-packages",
    "/home/arduino/.local/lib/python3.13/site-packages",
]
for _p in _EXTRA_PATHS:
    if _p not in sys.path:
        sys.path.insert(0, _p)

CORE_DIR = APP_DIR / "core"
HW_DIR = APP_DIR / "hw"
ASSETS_DIR = APP_DIR / "assets"
MODELS_DIR = APP_DIR / "models"
DATA_DIR = APP_DIR / "data"

PHOTOS_DIR = DATA_DIR / "photos"
RECORDINGS_DIR = DATA_DIR / "recordings"
RESPONSES_DIR = DATA_DIR / "responses"

MODELS_CONFIG_FILE = MODELS_DIR / "models.json"
MINIMAP_DIR = APP_DIR / "minimapa"
LOCATIONS_DIR = APP_DIR / "locations"
LOCATIONS_CONFIG_FILE = LOCATIONS_DIR / "locations.json"

DEFAULT_LOCATION = "sagrada_familia"

for _dir in (
    PHOTOS_DIR,
    RECORDINGS_DIR,
    RESPONSES_DIR,
    MODELS_DIR / "stt",
    MODELS_DIR / "slm",
    MODELS_DIR / "tts",
    MODELS_DIR / "vision",
    ASSETS_DIR,
    MINIMAP_DIR,
    LOCATIONS_DIR,
):
    _dir.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Hardware device discovery (auto-detects camera, mic, headphone output).
# Override any value below by setting environment variables before launching:
#   CULTURA_CAMERA_INDEX, CULTURA_MIC_DEVICE, CULTURA_PLAYBACK_DEVICE
# ---------------------------------------------------------------------------

import os as _os

try:
    from hw.device_discovery import discover_all as _discover_all
    _discovered = _discover_all()
except Exception as _exc:
    print(f"[WARN] Device discovery failed: {_exc}. Using hardcoded fallbacks.")
    _discovered = {}

def _env_int(var: str, default) -> int:
    v = _os.environ.get(var)
    return int(v) if v is not None else default

def _env_str(var: str, default):
    v = _os.environ.get(var)
    return v if v is not None else default

# V4L2 camera index for /dev/videoN  (env override: CULTURA_CAMERA_INDEX)
CAMERA_DEVICE_INDEX: int = _env_int(
    "CULTURA_CAMERA_INDEX",
    _discovered.get("camera") if _discovered.get("camera") is not None else 0,
)

# Microphone settings  (env override: CULTURA_MIC_DEVICE, CULTURA_MIC_RATE)
# discover_mic_device() now returns a dict: {alsa_device, card_index, sample_rate}
_mic_info = _discovered.get("mic") or {}
MIC_DEVICE: str = _os.environ.get("CULTURA_MIC_DEVICE") or _mic_info.get("alsa_device", "hw:1,0")
MIC_SAMPLE_RATE: int = _env_int("CULTURA_MIC_RATE", _mic_info.get("sample_rate", 48000))

# ALSA plughw string for headphone output  (env override: CULTURA_PLAYBACK_DEVICE)
PLAYBACK_DEVICE: str = _env_str(
    "CULTURA_PLAYBACK_DEVICE",
    _discovered.get("playback", "plughw:0,0"),  # fallback to card 0
)

DEFAULT_VOLUME_PERCENT = 70

RECORD_CHUNK_SECONDS = 0.5
RECORD_MAX_SECONDS = 60.0

# Camera capture resolution / codec settings
CAMERA_PHOTO_WIDTH = 1920
CAMERA_PHOTO_HEIGHT = 1080
CAMERA_FOURCC = "MJPG"

CAM_THUMB_W = 48
CAM_THUMB_H = 36
CAM_CHUNK_PIXELS = 72
CAMERA_CHUNK_DELAY_S = 0.00
CAMERA_SEND_INTERVAL = 0.01

PHOTO_PREVIEW_W = 160
PHOTO_PREVIEW_H = 86
PHOTO_CHUNK_PIXELS = 80


POLL_INTERVAL = 0.1

STT_MODEL_PATH = (
    MODELS_DIR / "stt"
    if (MODELS_DIR / "stt" / "model.bin").exists()
    else MODELS_DIR / "stt" / "faster-whisper-base.en"
)

SLM_MODEL_PATH = MODELS_DIR / "slm" / "qwen2.5-0.5b-instruct-q4_k_m.gguf"
KG_PATH = MODELS_DIR / "knowledge" / "element_sheets.json"
KG_BASE_PATH = MODELS_DIR / "knowledge" / "knowledge_base.json"
TTS_MODEL_DIR = MODELS_DIR / "tts"
VISION_MODEL_DIR = MODELS_DIR / "vision"

VISION_NON_RECOGNIZABLE_LABELS = {
    "unknown",
    "altres",
    "desconegut",
    "other",
    "no_element",
    "background",
    "non_monument",
    "none",
    "fons",
}
VISION_UNKNOWN_LABEL = "unknown"
