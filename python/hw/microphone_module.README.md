# `microphone_module.py` — Speech-to-Text (`transcribe()`)

**Estat**: ✅ IMPLEMENTAT — `MicrophoneManager.transcribe()` utilitza `faster-whisper` amb totes les optimitzacions del benchmark STT.

Elements integrats i actius:
- `record_while_held(is_still_held)` ✅
- `save(button_id, model_name, audio)` ✅
- `transcribe(audio_path)` ✅

---

## Mètode `transcribe(audio_path)`

```python
def transcribe(self, audio_path) -> str:
    """Transcriu un .wav ja gravat (el path que retorna save()) amb faster-whisper.
    Retorna el text transcrit com a string (buit "" si no s'ha pogut).
    """
```

---

## Implementació amb `faster-whisper`

Optimitzat per a ARM/Linux (UNO Q), configurat exclusivament per a anglès (`language="en"`):

```python
from faster_whisper import WhisperModel
```

### Optimitzacions aplicades:
- **`compute_type="int8"`** i **`cpu_threads=4`** (ajustat per a Cortex-A53)
- **`beam_size=1`**, **`temperature=0.0`** (cerca llaminera més ràpida)
- **`vad_filter=True`** (filtra silencis i evita al·lucinacions)
- **`initial_prompt=DOMAIN_PROMPT`** (context de la Sagrada Família / Park Güell)
- **`hotwords=build_hotwords()`** (vocabulari de domini Gaudí)
- **`canonicalize_domain_entities()`** (post-correcció de noms propis com Gaudí, Casa Batlló, Park Güell)

---

## Model Whisper necessari — `STT_MODEL_PATH` a `config.py`

El model per defecte és `Systran/faster-whisper-base.en`.

**On posar-lo:**
```
python/
└── models/
    └── stt/
        └── faster-whisper-base.en/
            ├── model.bin
            ├── config.json
            └── vocabulary.txt
```

Veure instruccions de descàrrega a [`python/models/stt/README.md`](../models/stt/README.md).
