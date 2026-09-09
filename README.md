# Cultura Viva — Arduino UNO Q

Interactive audio guide for Park Güell and the Sagrada Família. The user photographs a Gaudí element, confirms the shot, asks a question aloud, and receives a spoken answer tailored to the chosen personality (Artistic / Technical / Child).

The system combines computer vision (ONNX), speech-to-text (faster-whisper), a small language model (Qwen2.5 via llama-cpp), and text-to-speech (Piper). These run split across the Arduino UNO Q's two processors: the STM32 MCU runs the C++ sketch (real-time UI and hardware), and the Qualcomm QRB2210 Linux MPU runs the Python AI pipeline. The two sides communicate over Bridge RPC.

---

## Hardware

| Component | Details |
|---|---|
| **Arduino UNO Q** | STM32 MCU (C++ sketch, real-time) + Qualcomm QRB2210 Linux MPU (Python). Communication over Bridge RPC. |
| **LCD TFT ST7735S** | 128×160, 1.8", SPI — CS=10, DC=8, RST=9, backlight=5 |
| **Logitech Brio 105** | USB webcam — 1080p photos and live view. Built-in microphone (ALSA `hw:0,0`) |
| **Qwiic modules (I2C via Wire1)** | Modulino Buttons (A/B/C — personality selection), Modulino Knob (volume), Modulino Buzzer (photo feedback) |
| **Switch (D6)** | Toggles between camera mode and minimap mode |
| **Push button (D7)** | Takes photo (camera mode) / starts and stops audio recording (minimap mode) |
| **GPS NEO-6M** | `Serial1`, 9600 baud — automatic location detection by proximity |
| **Headphones** | 3.5mm jack (ALSA `default`) — volume controlled by Modulino Knob |

---

## File Structure

```
cultura-viva-uno-q/
│
├── README.md
├── app.yaml                     ← App manifest (name, icon)
│
├── sketch/                      ← C++ MCU code (Arduino sketch)
│   ├── sketch.ino               ← Entry point: peripheral init and Bridge RPC setup
│   ├── sketch.yaml              ← Library dependencies (pinned versions)
│   └── src/
│       ├── core/
│       │   ├── app_state.h/cpp  ← Global state variables (mode, personality, photo flags)
│       │   ├── config.h         ← Hardware pin and constant definitions
│       │   └── rpc_manager.h/cpp← Bridge.provide() registrations for all RPC endpoints
│       ├── display/
│       │   ├── ui_screens.h     ← Onboarding screens (welcome, tutorial, selection)
│       │   ├── ui_manager.h/cpp ← UI state machine: screen transitions and overlays
│       │   ├── camera_view.h/cpp← Live camera view and photo confirmation overlay
│       │   ├── minimap.h/cpp    ← Minimap render (terrain, landmark pins, location marker)
│       │   ├── landmarks_guell.h  ← Park Güell landmark coordinates and pin colors
│       │   ├── landmarks_sagrada.h← Sagrada Família landmark coordinates and pin colors
│       │   ├── tilemap_guell.h  ← Park Güell 40×28 tile map and terrain color palette
│       │   └── tilemap_sagrada.h← Sagrada Família 40×28 tile map and terrain color palette
│       ├── input/
│       │   └── controls.h/cpp   ← Button D7, switch D6, Modulino Buttons/Knob polling
│       └── location/
│           └── gps_module.h/cpp ← GPS serial reader (TinyGPSPlus wrapper)
│
└── python/                      ← Python code on the Linux MPU
    ├── main.py                  ← Main application loop (App.run)
    ├── config.py                ← Centralised configuration (paths, devices, buffer sizes)
    ├── requirements.txt         ← Python dependencies
    │
    ├── core/                    ← AI services and domain logic
    │   ├── model_module.py      ← ModelRegistry: personalities, prompts, knowledge graph, SLM
    │   ├── vision_module.py     ← VisionClassifier: ONNX element identification
    │   └── minimap_module.py    ← MinimapManager: landmark code → minimap RPC calls
    │
    ├── hw/                      ← Hardware peripheral managers
    │   ├── camera_module.py     ← CameraManager: 1080p capture + chunked live view
    │   ├── microphone_module.py ← MicrophoneManager: chunked recording + STT
    │   ├── audio_playback_module.py ← AudioPlayer: Piper TTS + ALSA playback
    │   └── location_module.py   ← LocationRegistry: GPS + Haversine → current location
    │
    ├── models/                  ← AI model files (not in repo — download separately)
    │   ├── knowledge/           ← Gaudí knowledge graph (element_sheets.json, knowledge_base.json)
    │   ├── stt/                 ← faster-whisper model (faster-whisper-base.en/)
    │   ├── slm/                 ← SLM in GGUF format (qwen2.5-1.5b-instruct-q4_k_m.gguf)
    │   ├── tts/                 ← Piper voice pairs (.onnx + .onnx.json)
    │   └── vision/              ← ONNX classifiers (park_guell/, sagrada_familia/)
    │
    ├── assets/                  ← Static assets (images, sounds)
    ├── data/                    ← Runtime data (created automatically on first run)
    │   ├── photos/              ← Captured photos (1080p .jpg)
    │   ├── recordings/          ← Recorded questions (.wav)
    │   └── responses/           ← Generated TTS responses (.wav)
    ├── minimapa/                ← Minimap data (landmarks.json, minimap_module.py)
    └── locations/               ← Optional GPS coordinate overrides (locations.json)
```

---

## Interaction Flow

### The switch selects between two modes:

| Switch D6 | Display | Push button D7 action |
|---|---|---|
| **ON — Camera mode** | Webcam live view | Takes a **photo** |
| **OFF — Map mode** | Park Güell minimap | First press **starts** recording / second press **stops** and processes |

### Full interaction sequence:

```
1. Switch ON  → Camera live view
2. Push button → Photo taken → preview shown on LCD
                → "Do you like the photo?" confirmation prompt appears
3. Switch OFF  → Photo confirmed → buzzer feedback → audio recording unlocked
4. [Optional] Buttons A/B/C → Select personality (Artistic / Technical / Child)
5. Push button D7 → Record question → second press stops recording
6. Automatic pipeline:
     STT     → Transcribe question (faster-whisper)
     Vision  → Classify Gaudí element from photo (ONNX)
     KG      → Retrieve factual context (knowledge graph)
     SLM     → Generate answer (Qwen2.5 via llama-cpp)
     TTS     → Synthesise speech (Piper) → play through headphones
```

> ⚠️ **Audio recording is blocked until a photo has been confirmed.** Attempting to record without a confirmed photo shows a warning on the LCD and discards the attempt.

### Personality buttons A/B/C:

The Modulino button LEDs reflect the active personality. During recording, all three blink in sync as visual feedback.

| Button | Personality | Piper voice | Response style |
|---|---|---|---|
| **A** | Artistic | LibriTTS-R medium (en-US) | Evocative, metaphors, passion |
| **B** | Technical | Semaine Spike (en-GB) | Precise, dimensions, materials |
| **C** | Child | Semaine Prudence (en-GB) | Simple, curious, anecdotal |

### GPS and location:

Location (Park Güell / Sagrada Família) is determined automatically by GPS proximity (Haversine distance). The sketch exposes the raw fix via RPC; `location_module.py` resolves the nearest site. If no GPS fix is available (indoors, testing), the system defaults to `park_guell`.

> ⚠️ The LCD minimap only has tile data for **Park Güell**. GPS is used exclusively to select the correct vision classifier and knowledge graph — it does not change the minimap display.

---

## RPC Interface (Bridge) — sketch ↔ Python

All functions the **sketch exposes** (`Bridge.provide`) and **Python calls** (`Bridge.call`):

| RPC function | Returns | Description |
|---|---|---|
| `photo_trigger()` | `bool` | `True` once when push button is pressed in camera mode (auto-consumed on read) |
| `confirm_photo_saved()` | — | Called by Python when the photo has been saved; triggers buzzer and shows confirmation prompt |
| `view_switch_state()` | `bool` | Debounced switch state (`True`=camera mode, `False`=map mode) |
| `camera_live_view_active()` | `bool` | Whether Python should continue sending live camera frames |
| `receive_camera_chunk(idx, total, data_b64)` | — | Receives one chunk of a Base64-encoded RGB565 live-view thumbnail |
| `get_personality_index()` | `int` 0/1/2 | Active personality selected via A/B/C |
| `is_recording_active()` | `bool` | `True` while the user's question is being recorded |
| `set_recording_active(active)` | — | Allows Python to sync or force-stop recording |
| `set_processing_active(active)` | — | `True` during STT/SLM/TTS synthesis; shows yellow overlay on LCD |
| `set_playback_active(active)` | — | `True` while TTS audio is playing; shows green overlay on LCD |
| `get_volume()` | `int` 0–100 | Current Modulino Knob position as a volume percentage |
| `has_gps_fix()` | `bool` | Whether a valid GPS location fix is currently available |
| `get_gps_lat()` / `get_gps_lon()` | `float` | Current coordinates (0.0 if no fix) |
| `mark_landmark_visited(id)` | `bool` | Marks a minimap landmark as visited by numeric index |
| `set_location_by_id(id)` | `bool` | Moves the "you are here" marker to a landmark's coordinates |
| `set_location_xy(x, y)` | `bool` | Moves the marker to arbitrary screen coordinates |
| `set_minimap_location(location)` | `bool` | Switches active map: 0=Park Güell, 1=Sagrada Família |
| `reset_minimap()` | `bool` | Clears all visited landmarks and the location marker |
| `set_photo_validation_state(state)` | — | Vision validation state: -1=idle, 0=checking, 1=valid, 2=invalid |
| `set_retake_message(msg)` | — | Sets the location label shown on the retake screen; call before `set_photo_validation_state(2)` |

### Camera live view — chunked transfer:

The Bridge RPC channel has a per-message size limit. Each frame is downscaled to `CAM_THUMB_W × CAM_THUMB_H` pixels in RGB565 format and sent in blocks of `CAM_CHUNK_PIXELS` pixels via `receive_camera_chunk`.

> **These three constants must match exactly between `config.py` and `sketch/src/core/config.h`.**

---

## Configuration (`python/config.py`)

All paths, device identifiers, and buffer sizes are centralised in `config.py`. If anything needs changing, it changes here and nowhere else.

### Values verified on real hardware:

```python
MIC_DEVICE             = "hw:0,0"       # Logitech Brio 105 microphone
CAMERA_DEVICE_INDEX    = 2              # /dev/video2
CAMERA_FOURCC          = "MJPG"
PLAYBACK_DEVICE        = "plughw:0,0"   # Jack 3.5mm (ALSA)
DEFAULT_VOLUME_PERCENT = 70
```

### AI model paths:

```python
STT_MODEL_PATH   = MODELS_DIR / "stt" / "faster-whisper-base.en"
SLM_MODEL_PATH   = MODELS_DIR / "slm" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"
KG_PATH          = MODELS_DIR / "knowledge" / "element_sheets.json"
KG_BASE_PATH     = MODELS_DIR / "knowledge" / "knowledge_base.json"
TTS_MODEL_DIR    = MODELS_DIR / "tts"
VISION_MODEL_DIR = MODELS_DIR / "vision"
```

---

## AI Model Installation

Model files are **not included in the repository** (too large). Download them manually.

### STT — faster-whisper

```bash
huggingface-cli download Systran/faster-whisper-base.en \
    --local-dir python/models/stt/faster-whisper-base.en
```

See [`python/models/stt/README.md`](python/models/stt/README.md) for full instructions and optimisation parameters.

### SLM — Qwen2.5 1.5B (llama-cpp-python)

```bash
# Download the GGUF from Hugging Face:
# https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF
# File: qwen2.5-1.5b-instruct-q4_k_m.gguf → python/models/slm/

# Build llama-cpp-python for aarch64 (Cortex-A53):
CMAKE_ARGS="-DGGML_NATIVE=OFF -DCMAKE_C_FLAGS='-march=armv8-a -mtune=cortex-a53' \
            -DCMAKE_CXX_FLAGS='-march=armv8-a -mtune=cortex-a53'" \
sudo pip install --break-system-packages llama-cpp-python
```

See [`python/models/README.md`](python/models/README.md) for download and build details.

### TTS — Piper

```bash
pip install piper-tts
# Download from https://huggingface.co/rhasspy/piper-voices:
#   en_US-libritts_r-medium.onnx + .onnx.json
#   en_GB-semaine-medium.onnx    + .onnx.json
# → python/models/tts/
```

See [`python/models/tts/README.md`](python/models/tts/README.md) for full instructions.

### Vision — ONNX classifiers

```
python/models/vision/
├── park_guell/
│   ├── model.onnx
│   └── labels.json    # ["3_viaductes", "casa_museu", ..., "unknown"]
└── sagrada_familia/
    ├── model.onnx
    └── labels.json    # ["cupula", "facana_naixement", ..., "unknown"]
```

---

## Knowledge Graph (`python/models/knowledge/`)

Two complementary files:

- **`element_sheets.json`** — Detailed fact sheets per Gaudí element, indexed by `id` and `aliases`. Used when the vision classifier identifies a specific element.
- **`knowledge_base.json`** — General Gaudí and monument context. Used as a fallback when the classifier returns `"unknown"`.

`ModelRegistry.get_kg_context(element, personality)` selects the relevant fields per personality automatically. To extend the knowledge base, add fields such as `year_built`, `materials`, `dimensions`, or `curiosities` (list of strings) — they are all serialised and injected into the SLM prompt as context.

---

## Project Status

### ✅ Verified on real hardware (3 Sep 2026)

- **C++ sketch**: compiled and flashed to UNO Q
  - Onboarding UI: welcome → options → tutorial ×3 → personality selection
  - Camera live view via chunked RPC
  - Photo confirmation flow: photo → preview → "Do you like the photo?" → switch confirms → buzzer → audio unlocked
  - Park Güell minimap with landmark pins and location marker
  - All peripherals: buttons A/B/C, switch D6, push button D7, Modulino Knob, buzzer

- **Python — hardware**:
  - `CameraManager`: 1080p capture + chunked live view ✅
  - `MicrophoneManager`: chunked recording ✅
  - `AudioPlayer`: `aplay` ALSA + dynamic volume via `amixer` (3.5mm jack) ✅

- **Python — AI (loads and runs)**:
  - `faster-whisper`: loaded and transcribes (STT) ✅
  - `onnxruntime`: loaded, classifies elements (Vision, 99.3% on Dragon Stairway) ✅
  - `llama-cpp-python`: loaded, generates answers (SLM, Qwen2.5 1.5B) ✅
  - `piper-tts`: voice loads — **speech output not yet confirmed on speaker** ⚠️

### ⚠️ Known issues

| # | Issue | Impact |
|---|---|---|
| 1 | **Piper TTS output unverified on speaker** | API fix applied (`synthesize()`), but actual audio output through the 3.5mm jack still needs confirmation |
| 2 | **STT returns empty string** | `faster-whisper` loads correctly but transcription is `''` — likely a microphone silence or overly aggressive VAD threshold issue |
| 3 | **Sagrada Família minimap not implemented** | If GPS resolves to Sagrada Família, vision/KG work correctly but the LCD still shows the Park Güell map |
| 4 | **GPS not physically verified** | GPS may not receive data if the physical pinout on the UNO Q differs from the sketch |

---

## Audio Playback (3.5mm Jack)

Audio plays through the **3.5mm jack** via ALSA (`PLAYBACK_DEVICE = "default"`).

Quick verification from the UNO Q MPU shell:

```bash
aplay -D default /usr/share/sounds/alsa/Front_Center.wav
amixer set Master 70%
```

---

## Dependency Troubleshooting (Arduino UNO Q)

The UNO Q's Linux MPU runs **Python 3.13.5** on **aarch64 (Qualcomm QRB2210, ARM Cortex-A53)**. All AI packages must be compiled or downloaded for `aarch64`; `x86_64` pre-built wheels will not work.

---

### Issue 1 — SSL certificate verification failure

**Symptom:**
```
SSLError: CERTIFICATE_VERIFY_FAILED - certificate verify failed:
Hostname mismatch, certificate is not valid for 'pypi.org'
```

**Cause:** The UPC network (UPCguest) performs TLS interception with a captive portal. The portal certificate (`portal-upcguest.upc.edu`) is presented instead of PyPI's.

**Fix:** Use a mobile hotspot, or pass `--trusted-host` if the environment allows:
```bash
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org <package>
```

---

### Issue 2 — System clock out of date breaks SSL

**Symptom:** TLS certificate rejected for invalid date even without a captive portal.

**Cause:** The board clock was more than a year behind (e.g. 2024 when the actual date is 2026). TLS rejects certificates when `not_before > now`.

**Temporary fix (until next reboot):**
```bash
sudo date -s "2026-09-03 14:41:00"
```

**Permanent fix:**
```bash
sudo apt install ntp
sudo systemctl enable ntp --now
```

---

### Issue 3 — `pip install` blocked by externally managed environment

**Symptom:**
```
error: externally-managed-environment
× This environment is externally managed
```

**Cause:** From Python 3.11 onward, Debian/Ubuntu mark the system Python as apt-managed. Direct `pip` installs are blocked.

**Fix:** Use `uv` (recommended) or `--break-system-packages`:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
cd ~/ArduinoApps/cultura-viva-uno-q/python
sudo ~/.local/bin/uv pip install --system --break-system-packages -r requirements.txt
```

---

### Issue 4 — `llama-cpp-python` fails to build inside Arduino App Lab

**Symptom:**
```
× Failed to build `llama-cpp-python==0.3.35`
CMake Error: CMAKE_C_COMPILER not found
```

**Cause:** Arduino App Lab runs `python/main.py` in a sandboxed container (`/app/`) with no access to `gcc`, `cmake`, or build tools. When `llama-cpp-python` is not in the `uv` cache, App Lab tries to compile it from source and fails. The cache is wiped between App Lab sessions.

**Fix — pre-install on the host system (outside App Lab):**
```bash
CMAKE_ARGS="-DGGML_NATIVE=OFF -DCMAKE_C_FLAGS='-march=armv8-a -mtune=cortex-a53' \
            -DCMAKE_CXX_FLAGS='-march=armv8-a -mtune=cortex-a53'" \
sudo pip install --break-system-packages llama-cpp-python
```

Then add the system site-packages paths to `sys.path` in `python/config.py` so App Lab can find them:
```python
# config.py — before any AI imports
import sys
from pathlib import Path

APP_DIR = Path(__file__).parent

_lib_dir = APP_DIR / "lib"
if _lib_dir.exists() and str(_lib_dir) not in sys.path:
    sys.path.insert(0, str(_lib_dir))

for _p in [
    "/usr/local/lib/python3.13/dist-packages",
    "/home/arduino/.local/lib/python3.13/site-packages",
]:
    if _p not in sys.path:
        sys.path.append(_p)
```

---

### Issue 5 — `opencv-python-headless` conflicts with system OpenCV

**Symptom:**
```
ImportError: libGL.so.1: cannot open shared object file
# or:
error: conflicting distribution 'opencv-python 4.13.0...' found in the system
```

**Cause:** The UNO Q OS ships its own optimised OpenCV build (`4.13.0+1ddb20b`). Installing `opencv-python-headless` via pip creates version conflicts or missing `.so` dependencies.

**Fix:** Remove `opencv-python-headless` from `requirements.txt` and `pyproject.toml`. The system OpenCV works correctly at 1080p.

```bash
python3 -c "import cv2; print(cv2.__version__)"
# → 4.13.0
```

---

### Issue 6 — `onnxruntime` installed to a path App Lab cannot find

**Symptom:** `[WARN] vision_module: 'onnxruntime' is not installed` in App Lab, even though `python3 -c "import onnxruntime"` works in the shell.

**Cause:** `onnxruntime` was installed to `/home/arduino/.local/lib/python3.13/site-packages/` (user install), which is not on the `sys.path` of the App Lab container.

**Fix:** Add the path to `sys.path` in `config.py` (see Issue 4 fix).

```bash
python3 -c "import onnxruntime; print(onnxruntime.__file__)"
# → /home/arduino/.local/lib/python3.13/site-packages/onnxruntime/__init__.py
```

---

### Issue 7 — Piper `synthesize_wav()` API incompatibility

**Symptom:**
```
[ERROR] AudioPlayer: synthesis failed for voice 'semaine_prudence':
PiperVoice.synthesize_wav() got an unexpected keyword argument 'speaker_id'
```

**Cause:** The `piper-tts` build for `aarch64` exposes `synthesize()` rather than `synthesize_wav()`, or does not accept `speaker_id` for single-speaker voices.

**Fix applied in `hw/audio_playback_module.py`:**
```python
try:
    if speaker_id is not None:
        voice_obj.synthesize(text, wf, speaker_id=speaker_id)
    else:
        voice_obj.synthesize(text, wf)
except (TypeError, AttributeError):
    try:
        voice_obj.synthesize(text, wf)
    except (TypeError, AttributeError):
        voice_obj.synthesize_wav(text, wf)   # fallback to older API
```

---

### Issue 8 — Vision label does not match knowledge graph key

**Symptom:**
```
[WARN] KG: element 'escalinata_drac' not found in any knowledge file.
```

**Cause:** The vision model returns the label `escalinata_drac` (from `labels.json`), but the knowledge graph entry used the key `drac_park_guell` with no matching alias.

**Fix:** Added `"escalinata_drac"` to the `aliases` list of the `drac_park_guell` entry. All vision labels are now mapped:

| Vision label | Knowledge graph key |
|---|---|
| `escalinata_drac` | `drac_park_guell` |
| `pavellons_consergeria` | `porters_lodge_park_guell` |
| `placa_natura` | `banc_serpentejant` |
| `3_viaductes` | `viaductes_park_guell` |
| `sala_hipostila` | `sala_hipostila` |

---

### Dependency verification

Run this snippet on the board to verify all AI packages are importable:

```bash
python3 -c "
mods = ['numpy', 'PIL', 'onnxruntime', 'faster_whisper', 'llama_cpp', 'piper', 'sounddevice']
for m in mods:
    try:
        __import__(m); print(f'[OK] {m}')
    except Exception as e:
        print(f'[MISSING] {m}: {e}')
"
```

Expected output on a verified board:
```
[OK] numpy
[OK] PIL
[OK] onnxruntime
[OK] faster_whisper
[OK] llama_cpp
[OK] piper
[OK] sounddevice
```

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/Hackestiu/cultura-viva-uno-q
cd cultura-viva-uno-q

# 2. Install Python dependencies:
#    Option A (recommended — uses uv):
curl -LsSf https://astral.sh/uv/install.sh | sh
cd python && uv sync
#
#    Option B (pip):
pip install -r python/requirements.txt

# 3. Download AI models (see "AI Model Installation" above)

# 4. Flash the sketch in Arduino Lab (sketch/sketch.ino — board: Arduino UNO Q)

# 5. Launch the app from Arduino Lab (Run button)
#    The UNO Q automatically runs python/main.py on the Linux MPU
```

---

## Git

```bash
git add -A
git commit -m "description"
git push

git pull --rebase

git status
git log --oneline -10
```
