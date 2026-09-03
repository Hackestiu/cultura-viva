# Carpeta de models d'IA

Aquí hi van els fitxers de models per a la pipeline de Cultura Viva (STT, SLM, TTS i Visió).

---

## Estructura de la carpeta

```
python/models/
├── knowledge/
│   ├── element_sheets.json  ← Fitxes detallades per element (Park Güell, La Pedrera…)
│   └── knowledge_base.json  ← Coneixement general de Gaudí i monuments
├── stt/                     ← Model faster-whisper (faster-whisper-base.en/)
├── slm/                     ← Model GGUF (qwen2.5-1.5b-instruct-q4_k_m.gguf)
├── tts/                     ← Veus Piper (.onnx + .onnx.json)
└── vision/                  ← Classificadors ONNX (park_guell/ i sagrada_familia/)
```

---

## 1. Model SLM — `models/slm/qwen2.5-1.5b-instruct-q4_k_m.gguf`

Model recomanat: **Qwen2.5-1.5B-Instruct** quantitzat (`q4_k_m`).  
Paràmetres d'inferència configurats a `core/model_module.py`:

| Paràmetre        | Valor | Raó                                |
|------------------|-------|------------------------------------|
| `n_ctx`          | 2048  | Finestra de context                |
| `n_threads`      | 4     | Nuclis del Cortex-A53              |
| `n_batch`        | 256   | Batch de processament de prompt    |
| `temperature`    | 0.1   | Respostes factuals, menys al·lucinació |
| `max_tokens`     | 128   | Respostes curtes per a TTS         |

### Descarregar (opció recomanada)
```bash
# Directament amb wget (a la Raspberry Pi):
wget -P python/models/slm/ \
  https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf
```

### Alternativa amb huggingface-cli
```bash
pip install huggingface-hub
huggingface-cli download Qwen/Qwen2.5-1.5B-Instruct-GGUF \
    qwen2.5-1.5b-instruct-q4_k_m.gguf \
    --local-dir python/models/slm/
```

### Compilar llama-cpp-python per a Raspberry Pi (Cortex-A53)
```bash
# Flags optimitzats per a armv8-a / Cortex-A53 (RPi 3 i 4):
CMAKE_ARGS="-DGGML_NATIVE=OFF -march=armv8-a -mtune=cortex-a53" \
    pip install llama-cpp-python
```

> **Nota:** `-DGGML_NATIVE=OFF` és important per evitar que cmake detecti
> l'arquitectura de la màquina de compilació creuada en lloc de la Pi.

---

## 2. Graf de coneixement — `models/knowledge/`

Conté la informació factual per a cada element de Gaudí que pot reconèixer
el mòdul de visió. Ara hi ha dos fitxers complementaris:

- **`element_sheets.json`** — Fitxes detallades per element (Park Güell, La Pedrera,
  elements individuals com el Drac, el banc serpentejant…). Indexat per `id` i per àlies.
- **`knowledge_base.json`** — Coneixement general de Gaudí, monuments i context
  artístic. S'usa com a fallback si la visió no identifica cap element concret.

El mètode `ModelRegistry.get_kg_context(element, personality)` selecciona
automàticament els camps rellevants per a cada personalitat (A=artística,
B=tècnica, C=nen).

---

## 3. Speech-to-Text (STT) — `models/stt/`

Veure la guia a [`stt/README.md`](stt/README.md).

---

## 4. Text-to-Speech (TTS) — `models/tts/`

Veure la guia a [`tts/README.md`](tts/README.md).
