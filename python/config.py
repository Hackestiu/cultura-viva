"""
Centralized configuration for the 'Project Personality' app.

Modify paths, devices, and dimensions only here -- all other modules
(camera_module, microphone_module, model_module, location_module, vision_module,
audio_playback_module, main) import from here and do not hardcode values.
"""

from pathlib import Path

# ---------- Paths ----------
# Inside the app's own directory (visible from host at ~/ArduinoApps/<app-id>/python/...)
APP_DIR = Path(__file__).resolve().parent

# Core AI and hardware directories
CORE_DIR = APP_DIR / "core"
HW_DIR = APP_DIR / "hw"
ASSETS_DIR = APP_DIR / "assets"
MODELS_DIR = APP_DIR / "models"
DATA_DIR = APP_DIR / "data"

# Runtime output data directories
PHOTOS_DIR = DATA_DIR / "photos"
RECORDINGS_DIR = DATA_DIR / "recordings"
RESPONSES_DIR = DATA_DIR / "responses"

# Directory for personality/voice/response models configuration
MODELS_CONFIG_FILE = MODELS_DIR / "models.json"

# Directory for minimap content (switch D6 OFF)
MINIMAP_DIR = APP_DIR / "minimapa"

# Directory for Location (Park Güell / Sagrada Família) coordinates
LOCATIONS_DIR = APP_DIR / "locations"
LOCATIONS_CONFIG_FILE = LOCATIONS_DIR / "locations.json"

# Default fallback location when GPS has no fix (e.g. testing indoors)
# Options: 'park_guell' | 'sagrada_familia'
DEFAULT_LOCATION = "park_guell"

# Ensure all runtime output and model folders exist on startup
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

# ---------- Microphone (question recording, button D7 toggle mode) ----------
# ALSA identifier for the microphone -- confirmed: "hw:0,0" (Logitech Brio 105)
MIC_DEVICE = "hw:0,0"

# ---------- Audio Playback (Jack 3.5mm headphones, volume via Modulino Knob) ----------
# ALSA output device for wired headphones connected via 3.5mm jack.
# "default" routes to the standard system audio output.
PLAYBACK_DEVICE = "default"

# Default volume percentage (0 - 100%)
DEFAULT_VOLUME_PERCENT = 70

# Recording chunk size in seconds for toggle recording with D7
RECORD_CHUNK_SECONDS = 0.5
# Maximum safety recording duration in seconds
RECORD_MAX_SECONDS = 60.0

# ---------- Camera (Logitech Brio 105, USB) ----------
# Video device index for V4L2 on UNO Q (/dev/video2 for capture)
CAMERA_DEVICE_INDEX = 2

# Full resolution photo capture settings
CAMERA_PHOTO_WIDTH = 1920
CAMERA_PHOTO_HEIGHT = 1080
CAMERA_FOURCC = "MJPG"

# ---------- Camera LCD Live View (switch D6 ON) ----------
# Thumbnail parameters sent over RPC in chunks to sketch.ino
CAM_THUMB_W = 48
CAM_THUMB_H = 36
CAM_CHUNK_PIXELS = 72
CAMERA_CHUNK_DELAY_S = 0.00
CAMERA_SEND_INTERVAL = 0.01

# ---------- Main Loop ----------
POLL_INTERVAL = 0.1

# ---------- Cultura Viva Pipeline — Model Paths ----------
# All paths point inside MODELS_DIR to keep paths centralized.
# If you change models or filenames, update them here.

# STT: faster-whisper model directory (contains model.bin, config.json, vocabulary.txt).
# Auto-detects if files are placed directly in models/stt or in a subdirectory.
STT_MODEL_PATH = (
    MODELS_DIR / "stt"
    if (MODELS_DIR / "stt" / "model.bin").exists()
    else MODELS_DIR / "stt" / "faster-whisper-base.en"
)

# SLM: Qwen2.5 model in GGUF format (llama-cpp-python).
SLM_MODEL_PATH = MODELS_DIR / "slm" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"
# Download URL (HuggingFace):
#   wget -P models/slm/ https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf
# Compile llama-cpp-python for Arduino UNO Q (ARM Cortex-A53 / aarch64):
#   CMAKE_ARGS="-DGGML_NATIVE=OFF -march=armv8-a -mtune=cortex-a53" pip install llama-cpp-python

# KG: Gaudí element sheets — detailed per-element info for vision-to-SLM context.
# Indexed by element id (e.g. 'drac_park_guell', 'banc_serpentejant').
KG_PATH = MODELS_DIR / "knowledge" / "element_sheets.json"

# KG: General knowledge base — monument overviews, Gaudí biography, etc.
# Used to enrich context when no specific element is detected.
KG_BASE_PATH = MODELS_DIR / "knowledge" / "knowledge_base.json"

# TTS: Piper voice models (.onnx + .onnx.json pairs) live in MODELS_DIR / "tts".
# The AudioPlayer in hw/audio_playback_module.py discovers them automatically via
# its voice registry (PERSONALITY_VOICE). No single-file path is needed here.
TTS_MODEL_DIR = MODELS_DIR / "tts"

# Vision: Vision ONNX models directory containing park_guell/ and sagrada_familia/
VISION_MODEL_DIR = MODELS_DIR / "vision"