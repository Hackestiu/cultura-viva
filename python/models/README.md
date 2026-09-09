# AI Models — `python/models/`
 
Model files for the Cultura Viva pipeline (STT, SLM, TTS, and Vision). None of these files are included in the repository — download them separately using the instructions below.
 
---
 
## Directory layout
 
```
python/models/
├── knowledge/
│   ├── element_sheets.json  ← Detailed fact sheets per Gaudí element (indexed by id and aliases)
│   └── knowledge_base.json  ← General Gaudí and monument context (fallback when vision returns unknown)
├── stt/                     ← faster-whisper model (faster-whisper-base.en/)
├── slm/                     ← GGUF model (qwen2.5-1.5b-instruct-q4_k_m.gguf)
├── tts/                     ← Piper voice pairs (.onnx + .onnx.json)
└── vision/                  ← ONNX classifiers (park_guell/ and sagrada_familia/)
```
 
All downloads below use `huggingface-cli`, which works directly on the board and is the single recommended path for every model in this project.
 
```bash
pip install huggingface-hub   # skip if already installed
```
 
---
 
## 1. SLM — `models/slm/qwen2.5-1.5b-instruct-q4_k_m.gguf`
 
Recommended model: **Qwen2.5-1.5B-Instruct** quantised to `q4_k_m`. Inference parameters are configured in `core/model_module.py`:
 
| Parameter | Value | Reason |
|---|---|---|
| `n_ctx` | 2048 | Context window |
| `n_threads` | 4 | Cortex-A53 core count |
| `n_batch` | 256 | Prompt processing batch size |
| `temperature` | 0.1 | Factual, low-hallucination outputs |
| `max_tokens` | 128 | Short answers suitable for TTS |
 
### Download
 
```bash
huggingface-cli download Qwen/Qwen2.5-1.5B-Instruct-GGUF \
    qwen2.5-1.5b-instruct-q4_k_m.gguf \
    --local-dir python/models/slm/
```
 
### Build llama-cpp-python for Arduino UNO Q (Cortex-A53 / aarch64)
 
```bash
CMAKE_ARGS="-DGGML_NATIVE=OFF -march=armv8-a -mtune=cortex-a53" \
    pip install llama-cpp-python
```
 
> **Note:** `-DGGML_NATIVE=OFF` prevents cmake from misdetecting the host architecture during cross-compilation on the board.
 
---
 
## 2. Knowledge graph — `models/knowledge/`
 
Factual data for each Gaudí element the vision module can recognise. Two complementary files:
 
- **`element_sheets.json`** — Detailed fact sheets per element (Park Güell, individual elements such as the Dragon Stairway, the Serpentine Bench, etc.). Indexed by `id` and `aliases`.
- **`knowledge_base.json`** — General Gaudí, monument, and artistic context. Used as a fallback when the vision classifier does not identify a specific element.
`ModelRegistry.get_kg_context(element, personality)` selects relevant fields per personality automatically (A=Artistic, B=Technical, C=Child).
 
---
 
## 3. Speech-to-Text (STT) — `models/stt/`
 
**Engine**: [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper) — a CTranslate2-based reimplementation of Whisper, optimized for CPU inference (int8 quantization, ~4× faster than vanilla Whisper on ARM).
 
### Expected layout
 
```
models/stt/
└── faster-whisper-base.en/
    ├── model.bin
    ├── config.json
    └── vocabulary.txt
```
 
The directory name `faster-whisper-base.en` is what `config.py` points to via `STT_MODEL_PATH`. If you rename it, update `STT_MODEL_PATH` in `config.py`.
 
### Download
 
```bash
huggingface-cli download Systran/faster-whisper-base.en \
    --local-dir python/models/stt/faster-whisper-base.en
```
 
`faster-whisper` uses the CTranslate2 model format. The tokenizer vocabulary is stored in `vocabulary.txt`, so a separate Hugging Face `tokenizer.json` file is not required by `WhisperModel`.
 
### Optimizations applied in `hw/microphone_module.py`
 
| Parameter | Value | Reason |
|---|---|---|
| `compute_type` | `"int8"` | ~4× faster on Cortex-A53, fits in 2 GB RAM |
| `cpu_threads` | `4` | UNO Q has 4 physical cores |
| `beam_size` | `1` | Greedy decoding — faster, deterministic |
| `temperature` | `0.0` | No sampling randomness |
| `vad_filter` | `True` | Removes silence chunks, reduces hallucinations |
| `min_silence_duration_ms` | `500` | VAD sensitivity threshold |
| `language` | `"en"` | English only |
| `initial_prompt` | Gaudí domain text | Biases ASR towards Gaudí/Barcelona vocabulary |
| `hotwords` | Domain keyword list | Boosts recognition of proper nouns |
 
Post-transcription, `canonicalize_domain_entities()` further corrects common ASR misspellings (e.g. "gaudy" → "Gaudí", "trencadis" → "trencadís").
 
---
 
## 4. Text-to-Speech (TTS) — `models/tts/`
 
### Expected layout
 
```
python/models/tts/
├── en_US-libritts_r-medium.onnx
├── en_US-libritts_r-medium.onnx.json
├── en_GB-semaine-medium.onnx
└── en_GB-semaine-medium.onnx.json
```
 
### Voice index
 
| Voice key (`hw/audio_playback_module.py`) | Personality | Language | Description | ONNX stem |
|---|---|---|---|---|
| `libriTTS_r_medium` | `artistic` | en-US | LibriTTS-R medium — clean, neutral American English | `en_US-libritts_r-medium` |
| `semaine_spike` | `technical` | en-GB | Semaine medium — Spike (male British English) | `en_GB-semaine-medium` |
| `semaine_prudence` | `child` | en-GB | Semaine medium — Prudence (female British English) | `en_GB-semaine-medium` |
 
> **Semaine note**: Spike and Prudence share the **same ONNX pair**. The module uses `speaker_id` 0 for Prudence and 1 for Spike, matching the downloaded `en_GB-semaine-medium.onnx.json` configuration.
 
All voices are hosted in [`rhasspy/piper-voices`](https://huggingface.co/rhasspy/piper-voices) on Hugging Face.
 
### Download
 
```python
from huggingface_hub import hf_hub_download
from pathlib import Path
import shutil
 
DEST = Path("python/models/tts")
DEST.mkdir(parents=True, exist_ok=True)
REPO = "rhasspy/piper-voices"
 
files = [
    # en-US LibriTTS-R medium
    "en/en_US/libritts_r/medium/en_US-libritts_r-medium.onnx",
    "en/en_US/libritts_r/medium/en_US-libritts_r-medium.onnx.json",
    # en-GB Semaine medium (covers both Spike and Prudence)
    "en/en_GB/semaine/medium/en_GB-semaine-medium.onnx",
    "en/en_GB/semaine/medium/en_GB-semaine-medium.onnx.json",
]
 
for remote_path in files:
    local = hf_hub_download(repo_id=REPO, filename=remote_path)
    target = DEST / Path(remote_path).name
    shutil.copy2(local, target)
    print(f"  OK  {target.name}")
```
 
---
 
## 5. Vision classifiers (ONNX) — `models/vision/`
 
ONNX-based classifiers for identifying architectural elements at each site:
- `models/vision/sagrada_familia/model.onnx` + `labels.json`
- `models/vision/park_guell/model.onnx` + `labels.json`
### Unknown / background class
 
Each model includes a dedicated `unknown` class to avoid false positives when the user photographs a person, an unrelated object, or the ground.
 
- **Park Güell** (8 classes, indices 0–7):
  - `0`: `3_viaductes`
  - `1`: `casa_museu`
  - `2`: `escalinata_drac`
  - `3`: `pavellons_consergeria`
  - `4`: `placa_natura`
  - `5`: `sala_hipostila`
  - `6`: `turo_3_creus`
  - `7`: `unknown`
- **Sagrada Família** (7 classes, indices 0–6):
  - `0`: `cupula`
  - `1`: `facana_naixement`
  - `2`: `facana_passio`
  - `3`: `laterals`
  - `4`: `posterior`
  - `5`: `torres`
  - `6`: `unknown`
When the classifier predicts `unknown`, or when confidence falls below `CONFIDENCE_THRESHOLD`, the system returns `"unknown"`. The SLM then invites the user to photograph a recognisable architectural element.
 

 