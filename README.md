# Cultura Viva — Arduino UNO Q

Audioguia interactiva de Park Güell i la Sagrada Família que combina visió
per computador, transcripció de veu (STT), model de llenguatge petit (SLM) i
síntesi de veu (TTS) sobre un Arduino UNO Q.

L'usuari fa una foto d'un element de Gaudí, confirma la foto amb el switch,
fa una pregunta en veu alta i rep una resposta parlada adaptada a la
personalitat seleccionada (Artístic / Tècnic / Infantil).

---

## Maquinari

| Component | Detalls |
|---|---|
| **Arduino UNO Q** | MCU STM32 (sketch `.ino`, temps real) + MPU Linux Qualcomm QRB2210 (Python). Es comuniquen per **Bridge RPC**. |
| **LCD TFT ST7735S** | 128×160, 1.8", SPI: CS=10, DC=8, RST=9, backlight=5 |
| **Webcam Logitech Brio 105** | USB — fotos 1080p i vista en directe. Micròfon integrat (ALSA `hw:0,0`) |
| **Mòduls Qwiic (I2C via `Wire1`)** | Modulino Buttons (A/B/C — selecció de personalitat), Modulino Knob (volum), Modulino Buzzer (feedback foto) |
| **Switch** | Switch físic a D6 — commuta entre mode càmera i mode minimapa |
| **Push button** | Botó físic a D7 — fa foto (mode càmera) / activa gravació (mode minimapa) |
| **GPS NEO-6M** | `Serial1`, 9600 baud — detecta la ubicació automàticament per proximitat |
| **Auriculars** | Jack 3.5mm cablejat (sortida ALSA `default`) — volum dinàmic via Modulino Knob |

---

## Estructura de fitxers

```
cultura-viva-uno-q/
│
├── README.md                    ← Ets aquí
├── app.yaml                     ← Manifest de l'app (nom, icona)
├── convert_logo.py              ← Eina per convertir el logo a bitmap C++
│
├── sketch/                      ← Codi C++ del MCU (sketch Arduino)
│   ├── sketch.ino               ← Entry point — inicialitza perifèrics i Bridge RPC
│   ├── sketch.yaml              ← Dependències de llibreries (versions explícites)
│   └── src/
│       ├── core/
│       │   ├── app_state.h/cpp  ← Variables globals d'estat (mode, personalitat, flags foto)
│       │   ├── config.h         ← Pins i constants de maquinari
│       │   └── rpc_manager.h/cpp← Registre de totes les funcions Bridge.provide(...)
│       ├── display/
│       │   ├── ui_screens.h     ← Pantalles d'acollida (benvinguda, tutorial, selecció)
│       │   ├── ui_manager.h/cpp ← Màquina d'estats de la UI: transicions entre pantalles
│       │   ├── camera_view.h/cpp← Vista en directe + overlay confirmació de foto
│       │   ├── minimap.h/cpp    ← Renderitzat del minimapa de Park Güell
│       │   ├── landmarks.h      ← Dades dels landmarks del minimapa
│       │   ├── tilemap.h        ← Paleta i terreny del minimapa
│       │   └── logo_bitmap.h    ← Bitmap del logo per la pantalla d'inici
│       ├── input/
│       │   └── controls.h/cpp   ← Lectura de botons, switch, knob; lògica de confirmació foto
│       └── location/
│           └── (GPS reading helpers)
│
└── python/                      ← Codi Python del MPU Linux
    ├── main.py                  ← Bucle principal de l'app (App.run)
    ├── config.py                ← Tota la configuració centralitzada (paths, devices, mides)
    ├── requirements.txt         ← Dependències Python
    │
    ├── core/                    ← Serveis d'IA i lògica de domini
    │   ├── model_module.py      ← ModelRegistry: personalitats, prompts, KG, SLM (llama-cpp)
    │   ├── vision_module.py     ← VisionClassifier: ONNX — detecta element Gaudí de la foto
    │   └── minimap_module.py    ← MinimapManager: traducció landmark → RPC del minimapa
    │
    ├── hw/                      ← Gestors de perifèrics hardware
    │   ├── camera_module.py     ← CameraManager: foto 1080p + vista en directe per chunks
    │   ├── microphone_module.py ← MicrophoneManager: gravació per chunks + STT (faster-whisper)
    │   ├── audio_playback_module.py ← AudioPlayer: TTS Piper + reproducció ALSA (Jack 3.5mm)
    │   └── location_module.py   ← LocationRegistry: GPS + Haversine → ubicació actual
    │
    ├── models/                  ← Fitxers de models d'IA (no inclosos al repositori)
    │   ├── kg.json              ← Graf de coneixement de Gaudí (12 elements, extensible)
    │   ├── stt/                 ← faster-whisper model (faster-whisper-base.en)
    │   ├── slm/                 ← Model SLM en GGUF (qwen2.5-1.5b-instruct-q4_k_m.gguf)
    │   ├── tts/                 ← Models de veu Piper (.onnx + .onnx.json)
    │   └── vision/              ← Models ONNX de classificació (park_guell/, sagrada_familia/)
    │
    ├── assets/                  ← Recursos estàtics (imatges, sons)
    ├── data/                    ← Dades en temps d'execució (es creen soles a l'inici)
    │   ├── photos/              ← Fotos preses (1080p .jpg)
    │   ├── recordings/          ← Preguntes gravades (.wav)
    │   └── responses/           ← Respostes TTS generades (.wav)
    ├── minimapa/                ← Dades del minimapa (landmarks.json, minimap_module.py)
    └── locations/               ← Override opcional de coordenades GPS (locations.json)
```

---

## Flux d'interacció (com funciona de cara a l'usuari)

### El switch commuta entre dos modes:

| Switch (D6) | Pantalla | Push button (D7) fa... |
|---|---|---|
| **ON — Mode càmera** | Vista en directe de la webcam | Fa una **foto** |
| **OFF — Mode minimapa** | Minimapa de Park Güell | 1r click **comença** a gravar / 2n click **para** i processa |

### Flux complet d'una interacció:

```
1. Switch ON  → Pantalla en directe de la càmera
2. Push button → Fa la foto → previsualització a la LCD
               → "Are you sure?" apareix a la pantalla
3. Switch OFF  → Confirma la foto → buzzer → desbloqueig de l'àudio
4. [Opcional] Botons A/B/C → Selecciona personalitat (Artístic/Tècnic/Infantil)
5. Push button (hold) → Grava la pregunta → para quan es deixa anar
6. Pipeline automàtica:
     STT     → Transcriu la pregunta (faster-whisper)
     Visió   → Classifica l'element Gaudí de la foto (ONNX)
     KG      → Recupera context factual de kg.json
     SLM     → Genera la resposta (Qwen2.5 via llama-cpp)
     TTS     → Sintetitza la veu (Piper) → reprodueix per auriculars Jack 3.5mm
```

> ⚠️ **Sense foto confirmada no es pot gravar àudio.** Si s'intenta gravar
> sense foto, la LCD mostra un avís i es descarta la gravació.

### Botons A/B/C — Personalitats:

Els LEDs dels botons reflecteixen la personalitat activa. Durant la gravació,
els tres parpellegen junts com a feedback visual.

| Botó | Personalitat | Veu Piper | Estil de resposta |
|---|---|---|---|
| **A** | Artístic | libriTTS r-medium (en-US) | Evocador, metàfores, passió |
| **B** | Tècnic | Semaine Spike (en-GB) | Precís, dimensions, materials |
| **C** | Infantil | Semaine Prudence (en-GB) | Simple, curiós, anecdòtic |

### GPS i ubicació:

La ubicació (Park Güell / Sagrada Família) es determina automàticament per
proximitat GPS (Haversine). El sketch exposa el fix cru via RPC;
`location_module.py` calcula el lloc més proper. Si no hi ha fix GPS
(interiors, test), el sistema usa `park_guell` com a fallback.

> ⚠️ El minimapa de la LCD només té dades de **Park Güell**. El GPS
> serveix exclusivament per triar el classificador de visió i el KG correcte,
> no per canviar la pantalla del minimapa.

---

## Interfície RPC (Bridge) — sketch ↔ Python

Totes les funcions que el **sketch exposa** (`Bridge.provide`) i el **Python crida** (`Bridge.call`):

| Funció RPC | Retorna | Descripció |
|---|---|---|
| `photo_trigger()` | `bool` | `True` una sola vegada quan es prem el push button en mode càmera (auto-consumida) |
| `confirm_photo_saved()` | — | Python la crida quan la foto s'ha desat → fa sonar el buzzer i mostra confirmació |
| `view_switch_state()` | `bool` | Estat debounced del switch (`True`=càmera, `False`=minimapa) |
| `receive_camera_chunk(idx, total, data_b64)` | — | Rep un chunk de la miniatura de la vista en directe |
| `get_personality_index()` | `int` 0/1/2 | Personalitat activa seleccionada amb A/B/C |
| `is_recording_active()` | `bool` | `True` mentre s'està gravant (toggle push button en mode minimapa) |
| `get_volume()` | `int` 0–100 | Posició actual del Modulino Knob com a % de volum |
| `has_gps_fix()` | `bool` | El GPS té fix vàlid en aquest moment |
| `get_gps_lat()` / `get_gps_lon()` | `float` | Coordenades actuals (0.0 si no hi ha fix) |
| `mark_landmark_visited(id)` | `bool` | Marca un landmark del minimapa com a visitat |
| `set_location_by_id(id)` | `bool` | Mou el marcador "estàs aquí" a un landmark |
| `set_location_xy(x, y)` | `bool` | Mou el marcador a coordenades de pantalla arbitràries |
| `reset_minimap()` | `bool` | Neteja landmarks visitats i marcador de posició |

### Vista de càmera per chunks:

El canal RPC té un límit de mida per missatge. Per això, cada fotograma es
redueix a `CAM_THUMB_W × CAM_THUMB_H` en RGB565 i s'envia en blocs de
`CAM_CHUNK_PIXELS` píxels via `receive_camera_chunk`. **Aquestes tres
constants han de coincidir EXACTAMENT entre `config.py` i `sketch.ino`.**

---

## Configuració (`python/config.py`)

Centralitza **tot** — paths, dispositius, mides de buffer. Si necessites canviar
alguna cosa, és aquí i **només aquí**.

### Valors verificats contra el maquinari real:

```python
MIC_DEVICE             = "hw:0,0"   # Logitech Brio 105
CAMERA_DEVICE_INDEX    = 2          # /dev/video2
CAMERA_FOURCC          = "MJPG"
PLAYBACK_DEVICE        = "default"  # Jack 3.5mm (ALSA)
DEFAULT_VOLUME_PERCENT = 70
```

### Paths dels models d'IA:

```python
STT_MODEL_PATH   = MODELS_DIR / "stt" / "faster-whisper-base.en"
SLM_MODEL_PATH   = MODELS_DIR / "slm" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"
KG_PATH          = MODELS_DIR / "kg.json"
TTS_MODEL_DIR    = MODELS_DIR / "tts"
VISION_MODEL_DIR = MODELS_DIR / "vision"
```

---

## Instal·lació dels models d'IA

Els fitxers de model **no estan al repositori** (massa grans). Cal baixar-los manualment:

### STT — faster-whisper

```bash
pip install faster-whisper
python -c "from faster_whisper import WhisperModel; WhisperModel('base.en', device='cpu')"
# Mou el model resultant a python/models/stt/faster-whisper-base.en/
```

### SLM — Qwen2.5 1.5B (llama-cpp-python)

```bash
pip install llama-cpp-python
# Baixa el GGUF de Hugging Face:
# https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF
# Fitxer: qwen2.5-1.5b-instruct-q4_k_m.gguf → python/models/slm/
```

### TTS — Piper

```bash
pip install piper-tts
# Baixa els models de veu de https://huggingface.co/rhasspy/piper-voices:
#   en_US-libritts_r-medium.onnx + .onnx.json
#   en_GB-semaine-medium.onnx    + .onnx.json
# → python/models/tts/
```

### Visió — ONNX

Els models de classificació han de tenir l'estructura:

```
python/models/vision/
├── park_guell/
│   ├── model.onnx
│   └── meta.json   # {"labels": ["escalinata_drac", "placa_natura", ...], "input_size": 224, ...}
└── sagrada_familia/
    ├── model.onnx
    └── meta.json
```

---

## Graf de coneixement (`python/models/kg.json`)

Conté 12 elements Gaudí (7 de Park Güell, 5 de Sagrada Família). Cada entrada:

```json
"escalinata_drac": {
  "full_name": "Dragon Stairway (Trencadís Salamander)",
  "location": "park_guell",
  "description": "Monumental entrance staircase featuring the famous multicolored mosaic salamander/dragon."
}
```

Per enriquir-lo afegeix camps com `year_built`, `materials`, `dimensions`,
`curiosities` (llista de strings) — `ModelRegistry.get_kg_context()` els
serialitza tots automàticament i els passa al SLM com a context.

---

## Estat actual del projecte

### ✅ Completament funcional

- **Sketch C++**: compilat i verificat a la UNO Q (Zephyr core)
  - UI d'acollida: benvinguda → opcions → tutorial ×3 → selecció de personalitat
  - Vista en directe de la càmera per chunks RPC
  - **Flux de confirmació de foto**: foto → previsualització → "Are you sure?" → switch confirma → buzzer → desbloqueig àudio
  - Minimapa de Park Güell amb landmarks i marcador de posició actual
  - Tots els perifèrics físics (A/B/C, switch, push button, knob, buzzer, GPS)

- **Python**: tots els mòduls verificats
  - `CameraManager`: fotos 1080p + live view chunked + `last_photo_path`
  - `MicrophoneManager`: gravació per chunks + STT (faster-whisper, domain-biased, VAD)
  - `AudioPlayer`: TTS Piper 3 veus + `aplay` ALSA + volum dinàmic via `amixer` (Jack 3.5mm)
  - `LocationRegistry`: GPS + Haversine, fallback `park_guell`
  - `VisionClassifier`: ONNX + ImageNet preprocessing + confidence threshold
  - `ModelRegistry`: personalitats, prompts per role, KG lookup, SLM via llama-cpp
  - `main.py`: pipeline STT→Visió→KG→SLM→TTS, guarda d'àudio si no hi ha foto confirmada

### ⚠️ Pendent / Limitacions conegudes

| # | Problema | Impacte |
|---|---|---|
| 1 | **SLM no descarregat** (`models/slm/` buit) | Retorna `"(model not available)"` com a resposta. La pipeline no peta, però no hi ha resposta real. |
| 2 | **KG bàsic** (només `description` per element) | El SLM rep poc context. Enriquir amb `curiosities`, `materials`, `year_built` milloraria les respostes. |
| 3 | **Models de visió no entrenats** (`models/vision/` buit) | `classify()` retorna `None` i la pipeline continua sense context visual. |
| 4 | **Models TTS no descarregats** (`models/tts/` buit) | `AudioPlayer` no produeix so fins que es baixin els `.onnx` de Piper. |
| 5 | **Minimapa Sagrada Família inexistent** | Si GPS detecta SF, la visió/KG és correcte però el minimapa de la LCD segueix mostrant Park Güell. |
| 6 | **Pins de `Serial1` (GPS) no verificats físicament** | El GPS pot no llegir si el pinout físic de la UNO Q difereix del sketch. |

---

## Reproducció de l'àudio (Jack 3.5mm)

L'àudio surt per **jack 3.5mm** directament per ALSA (`PLAYBACK_DEVICE = "default"`).

Verificació ràpida des de la UNO Q (MPU Linux):

```bash
aplay -D default /usr/share/sounds/alsa/Front_Center.wav
amixer set Master 70%
```

---

## Primers passos (setup des de zero)

```bash
# 1. Clona el repositori
git clone https://github.com/Hackestiu/cultura-viva-uno-q
cd cultura-viva-uno-q

# 2. Instal·la les dependències Python:
# Opció A: Amb uv (Recomanat — ultra ràpid):
#   curl -LsSf https://astral.sh/uv/install.sh | sh
#   cd python && uv sync
#
# Opció B: Amb pip tradicional:
pip install -r python/requirements.txt

# 3. Descarrega els models d'IA (veure secció "Instal·lació dels models")

# 4. Obre el sketch a Arduino Lab i fes el flash a la UNO Q
#    (sketch/sketch.ino — placa: Arduino UNO Q)

# 5. Llança l'app des d'Arduino Lab (botó "Run")
#    La UNO Q executa automàticament python/main.py al MPU Linux
```

---

## Git — Commits i sincronització

```bash
# Commit i push
git add -A
git commit -m "descripció del canvi"
git push

# Actualitzar des del remot
git pull --rebase

# Estat i historial
git status
git log --oneline -10
```
