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

### ✅ Verificat i funcionant (placa real, 3 set. 2026)

- **Sketch C++**: compilat i flaix a la UNO Q
  - UI d'acollida: benvinguda → opcions → tutorial ×3 → selecció de personalitat
  - Vista en directe de la càmera per chunks RPC
  - Flux de confirmació de foto: foto → previsualització → "Are you sure?" → switch confirma → buzzer → desbloqueig àudio
  - Minimapa de Park Güell amb landmarks i marcador de posició actual
  - Perifèrics: botons A/B/C, switch D6, push button D7, Modulino Knob (volum), buzzer

- **Python — maquinari**:
  - `CameraManager`: fotos 1080p + live view chunked ✅
  - `MicrophoneManager`: gravació per chunks ✅
  - `AudioPlayer`: `aplay` ALSA + volum dinàmic via `amixer` (Jack 3.5mm) ✅

- **Python — IA (verificat que carrega i executa)**:
  - `faster-whisper` carregat i transcriu (STT) ✅
  - `onnxruntime` carregat, classifica elements (Visió, 99.3% al Drac) ✅
  - `llama-cpp-python` carregat, genera respostes (SLM, Qwen2.5 1.5B) ✅
  - `piper-tts` carrega la veu — **síntesi pendent de verificar** ⚠️

### ⚠️ Pendent / Limitacions conegudes

| # | Problema | Impacte |
|---|---|---|
| 1 | **Síntesi Piper no verificada a l'altaveu** | Fix aplicat a l'API (`synthesize()`), però cal confirmar que surt so real pel jack 3.5mm |
| 2 | **STT retorna string buit** | `faster-whisper` carrega bé però la transcripció és `''` — possible problema de silenci al micròfon o de VAD massa estricte |
| 3 | **Minimapa Sagrada Família inexistent** | Si GPS detecta SF, la visió/KG funciona però el minimapa de la LCD segueix mostrant Park Güell |
| 4 | **GPS no verificat físicament** | El GPS pot no llegir si el pinout físic de la UNO Q difereix del sketch |

---

## Reproducció de l'àudio (Jack 3.5mm)

L'àudio surt per **jack 3.5mm** directament per ALSA (`PLAYBACK_DEVICE = "default"`).

Verificació ràpida des de la UNO Q (MPU Linux):

```bash
aplay -D default /usr/share/sounds/alsa/Front_Center.wav
amixer set Master 70%
```

---

## Instal·lació de dependències a l'Arduino UNO Q — Problemes i Solucions

Aquesta secció documenta tots els problemes sorgits durant la instal·lació de les
llibreries d'IA a la placa i les solucions definitives aplicades.

### Arquitectura del sistema

L'**Arduino UNO Q** executa el codi Python sobre un MPU Linux amb CPU
**Qualcomm QRB2210 (ARM Cortex-A53, `aarch64`, 64-bit)**. Totes les
dependències d'IA han de ser compilades per a `aarch64`; els paquets
precompilats per a `x86_64` no serveixen.

**Python disponible**: 3.13.5 (a `/usr/bin/python3`)

---

### Problema 1 — SSL: verificació de certificat fallida

**Símptoma:**
```
SSLError: CERTIFICATE_VERIFY_FAILED - certificate verify failed:
Hostname mismatch, certificate is not valid for 'pypi.org'
```

**Causa:** La xarxa de la UPC (UPCguest) fa intercepció TLS amb portal captiu.
El certificat del portal (`portal-upcguest.upc.edu`) es presenta en lloc del de PyPI.

**Solució:** Connectar la placa a un hotspot mòbil (sense proxy corporatiu) o
passar `--trusted-host` si l'entorn ho permet:
```bash
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org <paquet>
```

---

### Problema 2 — El rellotge del sistema desactualitzat trenca SSL

**Símptoma:** El certificat TLS és rebutjat per data invàlida fins i tot sense
portal captiu.

**Causa:** El rellotge de la placa estava desfasat > 1 any (p.ex. 2024 quan
l'any real és 2026). TLS rebutja certificats quan `not_before > now`.

**Solució temporal (fins al proper boot):**
```bash
sudo date -s "2026-09-03 14:41:00"
```

**Solució permanent:**
```bash
sudo apt install ntp
sudo systemctl enable ntp --now
```

---

### Problema 3 — `pip install` falla perquè el sistema és *externally managed*

**Símptoma:**
```
error: externally-managed-environment
× This environment is externally managed
```

**Causa:** A partir de Python 3.11, Debian/Ubuntu marquen el Python del
sistema com a gestionat per `apt`. `pip` directe queda bloquejat.

**Solució:** Usar el flag `--break-system-packages` o millor, usar `uv`:
```bash
# Instal·lar uv (gestor de paquets ultra ràpid en Rust)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Instal·lar dependències amb uv
cd ~/ArduinoApps/cultura-viva-uno-q/python
sudo ~/.local/bin/uv pip install --system --break-system-packages -r requirements.txt
```

---

### Problema 4 — `llama-cpp-python` no es pot compilar dins Arduino App Lab

**Símptoma:**
```
× Failed to build `llama-cpp-python==0.3.35`
CMake Error: CMAKE_C_COMPILER not found
```

**Causa:** Arduino App Lab executa `python/main.py` en un contenidor sandbox
(`/app/`) que **no té accés a `gcc`, `cmake` ni eines de compilació**. Quan
`llama-cpp-python` no és al cache de `uv`, App Lab intenta compilar-lo des de
zero i falla.

**Per què passa cada vegada que s'obre App Lab:** App Lab buida el cache de
`uv` entre sessions i torna a intentar compilar.

**Solució definitiva — Preinstalar al sistema host de la placa:**
```bash
# A la shell de la placa (fora d'App Lab)
CMAKE_ARGS="-DGGML_NATIVE=OFF -DCMAKE_C_FLAGS='-march=armv8-a -mtune=cortex-a53' \
            -DCMAKE_CXX_FLAGS='-march=armv8-a -mtune=cortex-a53'" \
sudo pip install --break-system-packages llama-cpp-python
```

I afegir els paths del sistema al `sys.path` d'App Lab via `python/config.py`:
```python
# config.py — al principi del fitxer, ABANS de qualsevol import de IA
import sys
from pathlib import Path

APP_DIR = Path(__file__).parent

# Libs vendoritzades dins l'app (si existeixen)
_lib_dir = APP_DIR / "lib"
if _lib_dir.exists() and str(_lib_dir) not in sys.path:
    sys.path.insert(0, str(_lib_dir))

# Paquets instal·lats al sistema host de la placa
for _p in [
    "/usr/local/lib/python3.13/dist-packages",
    "/home/arduino/.local/lib/python3.13/site-packages",
]:
    if _p not in sys.path:
        sys.path.append(_p)
```

---

### Problema 5 — `opencv-python-headless` conflicte amb el sistema

**Símptoma:**
```
ImportError: libGL.so.1: cannot open shared object file
# o bé:
error: conflicting distribution 'opencv-python 4.13.0...' found in the system
```

**Causa:** El SO de l'Arduino UNO Q porta un build propi i optimitzat de
`opencv` (`4.13.0+1ddb20b`) preinstal·lat. Instal·lar `opencv-python-headless`
via pip genera conflictes de versió o dependències de biblioteques `.so` absents.

**Solució:** Eliminar `opencv-python-headless` del `requirements.txt` i del
`pyproject.toml`. El OpenCV del sistema funciona perfectament a 1080p.

```bash
# Verificació:
python3 -c "import cv2; print(cv2.__version__)"
# → 4.13.0
```

---

### Problema 6 — `onnxruntime` s'instal·la a un path diferent

**Símptoma:** `[WARN] vision_module: 'onnxruntime' is not installed` a App Lab
tot i que `python3 -c "import onnxruntime"` funciona a la shell.

**Causa:** `onnxruntime` s'havia instal·lat a
`/home/arduino/.local/lib/python3.13/site-packages/` (instal·lació d'usuari)
mentre que App Lab usa Python de `/usr`. El path d'usuari no era al `sys.path`
del contenidor.

**Solució:** Afegit al `sys.path` de `config.py` (vegeu Problema 4).
Verificació:
```bash
python3 -c "import onnxruntime; print(onnxruntime.__file__)"
# → /home/arduino/.local/lib/python3.13/site-packages/onnxruntime/__init__.py
```

---

### Problema 7 — API de Piper `synthesize_wav()` incompatible

**Símptoma:**
```
[ERROR] AudioPlayer: synthesis failed for voice 'semaine_prudence':
PiperVoice.synthesize_wav() got an unexpected keyword argument 'speaker_id'
```

**Causa:** La versió de `piper-tts` instal·lada a `aarch64` exposa `synthesize()`
en lloc de `synthesize_wav()`, o bé no accepta el kwarg `speaker_id` en veus
mono-parlant.

**Solució aplicada a `hw/audio_playback_module.py`:**
```python
try:
    if speaker_id is not None:
        voice_obj.synthesize(text, wf, speaker_id=speaker_id)
    else:
        voice_obj.synthesize(text, wf)
except (TypeError, AttributeError):
    try:
        voice_obj.synthesize(text, wf)       # sense speaker_id
    except (TypeError, AttributeError):
        voice_obj.synthesize_wav(text, wf)   # fallback a API antiga
```

---

### Problema 8 — `element_sheets.json` no troba `escalinata_drac`

**Símptoma:**
```
[WARN] KG: element 'escalinata_drac' not found in any knowledge file.
```

**Causa:** El model de visió retorna l'etiqueta `escalinata_drac` (de
`labels.json`), però `element_sheets.json` tenia l'element amb `"id":
"drac_park_guell"` i sense cap àlies que coincidís amb `escalinata_drac`.

**Solució:** Afegida `"escalinata_drac"` a la llista `aliases` de l'element
`drac_park_guell`. Igualment s'han mapejat totes les etiquetes dels models de
visió als seus elements:

| Etiqueta del model | Element al KG |
|---|---|
| `escalinata_drac` | `drac_park_guell` |
| `pavellons_consergeria` | `porters_lodge_park_guell` |
| `placa_natura` | `banc_serpentejant` |
| `3_viaductes` | `viaductes_park_guell` |
| `sala_hipostila` | `sala_hipostila` |

---

### Resum de l'estat de les dependències (verificat 3 set. 2026)

```bash
python3 -c "
mods = ['numpy', 'PIL', 'onnxruntime', 'faster_whisper', 'llama_cpp', 'piper', 'sounddevice']
for m in mods:
    try:
        __import__(m); print(f'[OK] {m}')
    except Exception as e:
        print(f'[FALTA] {m}: {e}')
"
```

Resultat esperat (placa verificada):
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
