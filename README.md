# Cultura Viva — Arduino UNO Q

Interactive, bilingual multimodal AI audio guide for Park Güell and the Sagrada Família. Visitors capture a photo of a Gaudí architectural element, review the shot, ask a question aloud, and receive an instant spoken answer tailored to their chosen guide personality (Artistic, Technical, or Child).

The system runs on the **Arduino UNO Q** dual-processor architecture:
- **STM32 Microcontroller (MCU)**: Runs the real-time C++ Arduino sketch controlling the ST7735S LCD display, physical inputs (buttons, switches, rotary encoder), buzzer feedback, GPS ingestion, and minimap rendering.
- **Qualcomm QRB2210 Linux Processor (MPU)**: Runs the Python AI pipeline orchestrating computer vision (ONNX), speech-to-text (faster-whisper), knowledge graph retrieval, small language model reasoning (Qwen2.5 via llama-cpp-python), and speech synthesis (Piper TTS).

Communication between the MCU and MPU occurs over high-speed **Arduino Bridge RPC**.

---

## Hardware Architecture

| Component | Interface / Pinout | Role |
|---|---|---|
| **Arduino UNO Q** | Dual-core SoC | Real-time hardware control (MCU) + Linux AI pipeline (MPU) |
| **ST7735S LCD Display** | SPI: CS=10, DC=8, RST=9, BL=5 | 1.8" 128×160 color display (live view thumbnail, minimap, UI overlays) |
| **Logitech Brio 105** | USB 2.0 (`/dev/video2`, ALSA `hw:0,0`) | 1080p camera captures and microphone audio recording |
| **Modulino Buttons** | I2C (Wire1 / Qwiic) | Buttons A, B, C for guide personality selection and LED indicators |
| **Modulino Knob** | I2C (Wire1 / Qwiic) | Rotary encoder for real-time headphone volume control (0–100%) |
| **Modulino Buzzer** | I2C (Wire1 / Qwiic) | Acoustic feedback for shutter clicks, confirmations, and alerts |
| **Mode Switch** | Digital Pin D6 (internal pull-up) | Mode selector: HIGH = Camera Live View, LOW = Minimap Navigation |
| **Action Button** | Digital Pin D7 (internal pull-up) | Shutter button in Camera mode, Record/Stop toggle in Map mode, Cancel during generation |
| **NEO-6M GPS** | Serial1 (9600 baud) | Automatic proximity detection between Park Güell and Sagrada Família |
| **Headphones / Speaker** | 3.5mm Jack (ALSA `plughw:0,0`) | Piper TTS spoken audio output |

---

## Repository Structure

```
cultura-viva-uno-q/
├── README.md                    ← Project documentation
├── app.yaml                     ← Arduino App manifest
│
├── sketch/                      ← C++ Arduino Sketch (STM32 MCU)
│   ├── sketch.ino               ← Hardware setup, peripheral init, and main loop
│   ├── sketch.yaml              ← Pinned Arduino library dependencies
│   └── src/
│       ├── core/
│       │   ├── app_state.h/.cpp ← Global state flags and Bridge getters/setters
│       │   ├── config.h         ← Pin assignments, baud rates, and timing limits
│       │   └── rpc_manager.h/.cpp ← Bridge RPC method registrations
│       ├── display/
│       │   ├── camera_view.h/.cpp ← Chunked frame renderer, review overlay & validation
│       │   ├── minimap.h/.cpp   ← 40×28 tilemap rendering, landmark pins & location marker
│       │   ├── ui_manager.h/.cpp ← UI state machine, status overlay pills & volume bar
│       │   ├── ui_screens.h     ← UI layout primitives, navigation headers and cards
│       │   ├── ui_assets.h      ← Onboarding and tutorial RGB565 bitmaps
│       │   ├── landmarks_guell.h   ← Park Güell landmark coordinates and display names
│       │   ├── landmarks_sagrada.h ← Sagrada Família landmark coordinates and display names
│       │   ├── tilemap_guell.h     ← Park Güell tilemap grid and color palette
│       │   └── tilemap_sagrada.h   ← Sagrada Família tilemap grid and color palette
│       ├── input/
│       │   └── controls.h/.cpp  ← Debounced inputs for D6, D7, Modulino buttons/knob/buzzer
│       └── location/
│           └── gps_module.h/.cpp← TinyGPSPlus serial reader
│
└── python/                      ← Python AI Pipeline (Qualcomm Linux MPU)
    ├── main.py                  ← Central orchestration loop (App.run)
    ├── config.py                ← Central paths, devices, thresholds, and audio parameters
    ├── requirements.txt         ← Core Python dependencies
    ├── core/
    │   ├── model_module.py      ← Prompt construction, Knowledge Graph loader & local SLM
    │   ├── vision_module.py     ← ONNX classifier for Gaudí architectural elements
    │   └── minimap_module.py    ← Landmark visit and marker updates via Bridge RPC
    ├── hw/
    │   ├── camera_module.py     ← 1080p capture and base64 live-view thumbnail streaming
    │   ├── microphone_module.py ← Chunked audio recording and faster-whisper STT
    │   ├── audio_playback_module.py ← Piper TTS synthesis and ALSA playback with live volume
    │   └── location_module.py   ← GPS coordinate ingestion and Haversine site resolution
    ├── minimapa/                ← JSON coordinate datasets for minimap landmarks
    └── models/                  ← AI model weights and knowledge graph (downloaded separately)
        ├── knowledge/           ← Gaudí fact sheets (element_sheets.json, knowledge_base.json)
        ├── slm/                 ← Quantized GGUF language model (Qwen2.5 1.5B Instruct)
        ├── stt/                 ← faster-whisper speech recognition model
        ├── tts/                 ← Piper voice ONNX models and configs
        └── vision/              ← ONNX classification models for Park Güell & Sagrada Família
```

---

## Interaction Flow

```
+-----------------------------------------------------------------------------------+
| 1. CAMERA MODE (Switch D6 ON)                                                     |
|    - Live-view stream rendered on ST7735S LCD.                                    |
|    - Press Button D7 -> Captures 1080p photo.                                     |
|    - Vision AI validates photo:                                                   |
|        - If non-monument -> Retake screen displayed.                             |
|        - If valid monument -> Photo review prompt ("Do you like the photo?").     |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| 2. PHOTO CONFIRMATION                                                             |
|    - Flip Switch D6 OFF (Map Mode) -> Photo CONFIRMED, buzzer chirps, mic unblocked|
|    - (OR press Button D7 while ON -> Discard and retake photo).                   |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| 3. PERSONALITY SELECTION (Modulino Buttons)                                       |
|    - [A] Artistic  : Evocative, metaphorical style (LibriTTS-R voice)             |
|    - [B] Technical : Architectural, precise facts (Semaine Spike voice)           |
|    - [C] Child     : Simple, fun, engaging stories (Semaine Prudence voice)       |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| 4. QUESTION & SPEECH REASONING (Switch D6 OFF - Map Mode)                         |
|    - Press Button D7 -> Starts audio recording (Red overlay pill).                |
|    - Press Button D7 again -> Stops recording. AI pipeline executes:              |
|        1. Speech-to-Text (faster-whisper) transcribes spoken question.            |
|        2. Vision Classifier (ONNX) identifies specific architectural element.     |
|        3. Knowledge Graph retrieves grounded facts for site + element.            |
|        4. Small Language Model (Qwen2.5 1.5B via llama-cpp) generates response.   |
|        5. Text-to-Speech (Piper) synthesizes spoken audio.                        |
|        6. Audio Player plays output through headphones; volume adjustable via Knob.|
|    - Landmark visited is marked on the interactive LCD minimap.                   |
|    - Pressing Button D7 during processing immediately cancels generation.         |
+-----------------------------------------------------------------------------------+
```

> **Note**: Audio recording is guarded; attempting to record before confirming a valid photo triggers a warning dialog on the display.

---

## Bridge RPC Interface

The STM32 MCU registers RPC endpoints via `Bridge.provide(...)`, called by Python via `Bridge.call(...)`:

| Endpoint | Return Type | Description |
|---|---|---|
| `photo_trigger()` | `bool` | Returns `true` once when button D7 is pressed in camera mode; resets flag. |
| `confirm_photo_saved()` | `void` | Notifies the MCU that a photo is saved, scheduling confirmation UI & buzzer. |
| `view_switch_state()` | `bool` | Current debounced state of switch D6 (`true` = Camera mode, `false` = Map mode). |
| `camera_live_view_active()`| `bool` | `true` when the MCU is ready to accept and render live-view thumbnail frames. |
| `receive_camera_chunk(idx, total, b64)` | `void` | Receives a Base64 RGB565 thumbnail chunk from Python and draws to LCD. |
| `get_personality_index()` | `int` | Selected guide personality (0 = Artistic, 1 = Technical, 2 = Child). |
| `is_recording_active()` | `bool` | `true` while user audio recording is in progress. |
| `set_recording_active(bool)` | `void` | Enables or disables recording state from Python. |
| `is_processing_active()` | `bool` | `true` while AI pipeline (STT, SLM, TTS) is executing. |
| `set_processing_active(bool)` | `void` | Controls the "Generating answer..." status pill and cancellation listener. |
| `is_playback_active()` | `bool` | `true` while Piper TTS audio is playing through ALSA. |
| `set_playback_active(bool)` | `void` | Updates the "Speaking answer..." status pill on the display. |
| `get_volume()` | `int` | Current output volume percentage (0–100) from the Modulino rotary knob. |
| `has_gps_fix()` | `bool` | `true` if NEO-6M GPS has a valid geographical position fix. |
| `get_gps_lat()` / `get_gps_lon()` | `float` | Current latitude and longitude coordinates. |
| `mark_landmark_visited(id)`| `bool` | Marks a landmark as visited on the minimap. |
| `set_location_by_id(id)` | `bool` | Moves the "you are here" marker to a landmark's coordinates. |
| `set_location_xy(x, y)` | `bool` | Moves the "you are here" marker to arbitrary screen coordinates. |
| `set_minimap_location(id)` | `bool` | Switches active map: 0 = Park Güell, 1 = Sagrada Família. |
| `reset_minimap()` | `bool` | Clears all visited landmarks and resets user position marker. |
| `set_photo_validation_state(s)` | `void` | Sets vision state: 0 = scanning, 1 = valid, 2 = invalid, -1 = idle. |
| `set_retake_message(msg)` | `void` | Sets the location name string displayed on the retake screen. |

---

## Setup and Quick Start

### 1. Hardware Assembly
- Mount the Arduino UNO Q onto your carrier board.
- Connect the ST7735S display to the designated SPI pins (CS: 10, DC: 8, RST: 9, Backlight: 5).
- Connect the Modulino modules (Buttons, Knob, Buzzer) to the I2C Wire1 Qwiic port.
- Wire Switch D6 and Push Button D7 to ground (using internal pull-ups).
- Connect the NEO-6M GPS to `Serial1` (TX/RX).
- Connect the Logitech Brio 105 USB webcam to the USB-A port and plug headphones into the 3.5mm jack.

### 2. Flash the Microcontroller Sketch
1. Open Arduino Lab for MicroPython or the Arduino IDE.
2. Select target board **Arduino UNO Q** (profile: `arduino:zephyr:unoq`).
3. Open `sketch/sketch.ino` and flash it to the board.

### 3. Install Python Dependencies
On the Arduino UNO Q Linux MPU:
```bash
cd cultura-viva-uno-q/python
pip install -r requirements.txt
```

*Required external packages on aarch64*: `onnxruntime`, `faster-whisper`, `llama-cpp-python`, `piper-tts`, `sounddevice`, `numpy`, `pillow`.

### 4. Download Model Weights
Place the required model files into their respective folders under `python/models/`:
- **Speech-to-Text**: `python/models/stt/faster-whisper-base.en`
- **Language Model**: `python/models/slm/qwen2.5-1.5b-instruct-q4_k_m.gguf`
- **Text-to-Speech**: Piper `.onnx` and `.onnx.json` files in `python/models/tts/`
  - `en_US-libritts_r-medium.onnx`
  - `en_GB-semaine-medium.onnx`
- **Vision Models**: ONNX models and labels in `python/models/vision/park_guell/` and `python/models/vision/sagrada_familia/`
- **Knowledge Base**: `element_sheets.json` and `knowledge_base.json` in `python/models/knowledge/`

### 5. Run the Application
Launch the main Python loop on the MPU:
```bash
python3 python/main.py
```
Or launch it directly from Arduino App Lab by pressing **Run**.
