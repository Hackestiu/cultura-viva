# Carpeta de models d'IA
 
Aquí hi van els fitxers de models per a la pipeline de Cultura Viva (STT, SLM, TTS i Visió).
 
---
 
## Estructura de la carpeta
 
```
python/models/
├── kg.json              ← Graf de coneixement de Gaudí (12 elements)
├── stt/                 ← Model faster-whisper (faster-whisper-base.en/)
├── slm/                 ← Model GGUF (qwen2.5-1.5b-instruct-q4_k_m.gguf)
├── tts/                 ← Veus Piper (.onnx + .onnx.json)
└── vision/              ← Classificadors ONNX (park_guell/ i sagrada_familia/)
```
 
---
 
## 1. Model SLM — `models/slm/<fitxer>.gguf`
 
El mètode `ModelRegistry.generate_response(...)` a `core/model_module.py` necessita un fitxer GGUF. Model recomanat: **Qwen2.5-1.5B-Instruct** quantitzat (`q4_k_m`) — és lleuger i cap bé a la memòria de la UNO Q.
 
**Com descarregar-lo:**
```bash
pip install huggingface-hub
huggingface-cli download Qwen/Qwen2.5-1.5B-Instruct-GGUF \
    qwen2.5-1.5b-instruct-q4_k_m.gguf \
    --local-dir python/models/slm/
```
 
---
 
## 2. Graf de coneixement (KG) — `models/kg.json`
 
Conté la informació factual per a cada element de Gaudí que pot reconèixer el mòdul de visió. El fitxer `models/kg.json` ja està creat amb 12 elements base i es pot enriquir lliurement afegint camps (`curiosities`, `materials`, `year_built`, etc.).
 
---
 
## 3. Speech-to-Text (STT) — `models/stt/`
 
Veure la guia a [`stt/README.md`](stt/README.md).
 
---
 
## 4. Text-to-Speech (TTS) — `models/tts/`
 
Veure la guia a [`tts/README.md`](tts/README.md).

