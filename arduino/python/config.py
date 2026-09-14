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

# Site used when GPS cannot place the visitor (no fix, or a fix outside every
# site's radius). locations.json may name a different one in its "default" key;
# this is the last resort if that file is missing or names an unknown site.
DEFAULT_LOCATION = "sagrada_familia"

for _dir in (
    PHOTOS_DIR,
    RECORDINGS_DIR,
    RESPONSES_DIR,
    DATA_DIR / "prefix_cache",
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

# Logging is configured here, before device discovery runs, so the discovery
# decisions (which camera/mic/playback device was picked, and whether it came
# from a real match or a fallback) land in this run's log file too.
from logging_setup import logger, setup_logging

setup_logging()

try:
    from hw.device_discovery import discover_all as _discover_all
    _discovered = _discover_all()
except Exception as _exc:
    logger.exception(
        "Device discovery failed: {}. Using hardcoded fallbacks.", _exc
    )
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
    _discovered.get("camera") if _discovered.get("camera") is not None else 2,
)

# Microphone settings  (env override: CULTURA_MIC_DEVICE, CULTURA_MIC_RATE)
# discover_mic_device() now returns a dict: {alsa_device, card_index, sample_rate}
_mic_info = _discovered.get("mic") or {}
MIC_DEVICE: str = _os.environ.get("CULTURA_MIC_DEVICE") or _mic_info.get("alsa_device", "hw:1,0")
MIC_SAMPLE_RATE: int = _env_int("CULTURA_MIC_RATE", _mic_info.get("sample_rate", 48000))

# ALSA plughw string for headphone output  (env override: CULTURA_PLAYBACK_DEVICE)
PLAYBACK_DEVICE: str = _env_str(
    "CULTURA_PLAYBACK_DEVICE",
    # `or` (not .get's default): now that discovery actually runs, it returns an
    # explicit None for "nothing found", which .get would have passed through.
    _discovered.get("playback") or "plughw:0,0",  # fallback to card 0
)

# Forces a site regardless of GPS (env override: CULTURA_LOCATION), for testing
# away from the monuments and for a device whose GPS cannot see the sky. Must be
# an id from locations.json; an unknown id is refused and logged, and GPS decides
# as usual. Can also be set and cleared at runtime via LocationRegistry.
LOCATION_OVERRIDE = _os.environ.get("CULTURA_LOCATION") or None

DEFAULT_VOLUME_PERCENT = 70

RECORD_CHUNK_SECONDS = 0.5
RECORD_MAX_SECONDS = 60.0

# ---------------------------------------------------------------------------
# Silence detection (see hw/microphone_module.py).
#
# Two uses, one measurement: a recording stops by itself once the visitor stops
# talking, and the silence still left at either end is cropped off before the
# samples reach Whisper -- the encoder pads every window to a fixed length, so
# seconds of room tone between the last word and the button cost real time on
# the critical path.
#
# Levels are RMS in int16 units (0..32767). A block counts as silence when it is
# below SILENCE_RMS_ABSOLUTE *and* below SILENCE_RMS_NOISE_FACTOR times the room
# noise floor measured at the start of the recording, so a noisy plaza raises the
# bar instead of keeping the recording open forever.
# ---------------------------------------------------------------------------

SILENCE_RMS_ABSOLUTE = 300
SILENCE_RMS_NOISE_FACTOR = 3.0

# Ceiling on the threshold the factor above can produce. Speech a hand's length from
# the Brio sits a few thousand RMS, so a very loud room could otherwise raise the bar
# above the visitor's own voice -- the gate would hear speech as silence and cut the
# question off. Capping it means a room that loud simply stops auto-detecting: the
# recording runs until D7 or RECORD_MAX_SECONDS, as it did before.
SILENCE_RMS_CEILING = 1500

# Room tone sampled at the start of each recording to set the noise floor.
SILENCE_CALIBRATION_SECONDS = 0.3

# Silence after the visitor has spoken that ends the recording. Long enough to
# survive the pause between two sentences, short enough not to be noticed.
SILENCE_HANGOVER_SECONDS = 5.0

# Silence *before* any speech that ends the recording, so a button pressed by
# accident does not hold the pipeline open until RECORD_MAX_SECONDS.
SILENCE_LEADIN_SECONDS = 6.0

# Kept either side of the speech when cropping, so a soft first or last
# consonant is not clipped off.
SILENCE_TRIM_PADDING_SECONDS = 0.25

# Continuous silence after which the transcription of what has been said so far is
# started speculatively, on a background thread, while the hangover above runs out.
# The visitor has already stopped talking at this point, so the rest of the hangover
# is dead time on the critical path -- this spends it on Whisper instead. Must stay
# below SILENCE_HANGOVER_SECONDS, or the recording ends before the head start begins;
# raising it costs overlap, lowering it makes a mid-question breath more likely to
# launch a run that is thrown away. Set to 0 to disable.
SILENCE_SPECULATIVE_SECONDS = 0.6

# ---------------------------------------------------------------------------
# Speech to text (see hw/microphone_module.py).
# ---------------------------------------------------------------------------

# Whisper pads every window to chunk_length seconds of mel frames before the encoder
# runs, so the encoder cost is set by this number and not by how long the visitor
# actually spoke. STT_CHUNK_LENGTH_S is the ceiling (audio longer than this is split
# into successive windows); a recording shorter than that is transcribed in a window
# cut down to its own duration, never below STT_MIN_CHUNK_LENGTH_S.
STT_CHUNK_LENGTH_S = 15
STT_MIN_CHUNK_LENGTH_S = 6

# Silero VAD inside faster-whisper. Off by default: trim_silence() already crops the
# room tone off both ends from the RMS levels the silence gate has measured anyway,
# so the VAD pass is a second ONNX model over the same audio for what is, on a cropped
# question, almost always the same span.
STT_VAD_FILTER = False

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

# Whisper weights. base.en transcribes at roughly 1.3x realtime on these four
# Cortex-A53 cores; faster-whisper-tiny.en is about 2.5x faster for a modest accuracy
# cost on short tourist questions. Drop that model into models/stt/ and point
# CULTURA_STT_MODEL at it to trade one for the other without editing this file.
_STT_MODEL_OVERRIDE = _os.environ.get("CULTURA_STT_MODEL")
STT_MODEL_PATH = (
    Path(_STT_MODEL_OVERRIDE)
    if _STT_MODEL_OVERRIDE
    else (
        MODELS_DIR / "stt"
        if (MODELS_DIR / "stt" / "model.bin").exists()
        else MODELS_DIR / "stt" / "faster-whisper-base.en"
    )
)
if not STT_MODEL_PATH.is_absolute():
    STT_MODEL_PATH = MODELS_DIR / "stt" / STT_MODEL_PATH

_SLM_MODEL_OVERRIDE = _os.environ.get("CULTURA_SLM_MODEL")
SLM_MODEL_PATH = (
    Path(_SLM_MODEL_OVERRIDE)
    if _SLM_MODEL_OVERRIDE
    else MODELS_DIR / "slm" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"
)
if not SLM_MODEL_PATH.is_absolute():
    SLM_MODEL_PATH = MODELS_DIR / "slm" / SLM_MODEL_PATH

# ---------------------------------------------------------------------------
# SLM prefix cache (see core/model_module.py, warm_prefix()).
#
# Prefilling the ~400-token prompt costs ~27s on these Cortex-A53 cores, and it is
# the same arithmetic every time: the KV cache llama.cpp builds is a pure function of
# the model file and the tokens. So it is computed once per element and kept on disk.
#
# Only the *facts* head of the prompt is cached, not the personality instructions that
# follow it -- llama.cpp reuses a prefix and nothing else, so a cached block has to sit
# at the very front. That leaves the ~94-token personality tail to prefill live (~6s,
# overlapped with the recording), and buys the property that editing a personality
# prompt does not invalidate a single cached state. Editing a knowledge sheet or
# swapping the model does, and the filename hash makes that automatic.
#
# Disposable by construction: deleting this directory costs one slow prefill per
# element, never a wrong answer.
# ---------------------------------------------------------------------------

SLM_PREFIX_CACHE_DIR = DATA_DIR / "prefix_cache"
SLM_PREFIX_CACHE_MAX_MB = 400
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
