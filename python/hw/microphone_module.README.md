# `microphone_module.py` — mètode `transcribe()` pendent

**Estat**: ⏳ PENDENT D'IMPLEMENTAR — `MicrophoneManager.transcribe()` **no
existeix** encara al fitxer. El que sí existeix i funciona:
- `record_while_held(is_still_held)` ✅
- `save(button_id, model_name, audio)` ✅

**NO tocar cap d'aquests dos** quan implementis `transcribe()`.

---

## Mètode a afegir

```python
def transcribe(self, audio_path) -> str:
    """Transcriu un .wav ja gravat (el path que retorna save()) amb Whisper.
    Retorna el text transcrit com a string (buit "" si no s'ha pogut).

    NO toca record_while_held() ni save(), que ja funcionen.
    """
```

### On afegir-lo dins del fitxer

Al final de la classe `MicrophoneManager`, **després** del mètode `save()`.
`save()` és un `@staticmethod`, `transcribe()` ha de ser un mètode
d'instància normal (necessita `self` perquè pot voler accedir al model
carregat a `__init__` per eficiència — no carregar-lo cada vegada).

---

## Implementació amb `pywhispercpp`

Recomanat per ARM/Linux (UNO Q). No depèn de CUDA.

```python
from pywhispercpp.model import Model as WhisperModel

class MicrophoneManager:
    def __init__(self):
        # ... codi existent intacte ...
        self._whisper = None  # carregat lazy a la primera crida

    def transcribe(self, audio_path) -> str:
        if self._whisper is None:
            from config import STT_MODEL_PATH
            self._whisper = WhisperModel(str(STT_MODEL_PATH))
        segments = self._whisper.transcribe(str(audio_path))
        return " ".join(s.text for s in segments).strip()
```

**Llibreria** (afegir a `requirements.txt`):
```
pywhispercpp>=1.0.0
```

---

## Model Whisper necessari — `STT_MODEL_PATH` a `config.py`

El model Whisper en format GGML (el que fa servir `pywhispercpp`). El
model petit (`base` o `small`) va bé per a transcripció en català/castellà
en temps quasi-real a la UNO Q.

**On posar-lo:**
```
python/
└── models/
    └── stt/
        └── ggml-small.bin    ← fitxer aquí
```

**Com descarregar-lo (des de la UNO Q):**
```bash
# opció 1: des de huggingface
pip install huggingface-hub
huggingface-cli download ggerganov/whisper.cpp ggml-small.bin \
    --local-dir python/models/stt/

# opció 2: script oficial de whisper.cpp
bash models/download-ggml-model.sh small
```

**Afegir a `config.py` quan el tinguis:**
```python
STT_MODEL_PATH = MODELS_DIR / "stt" / "ggml-small.bin"
```

> ⚠️ **Si canvies de model Whisper o de nom de fitxer**: actualitza
> `STT_MODEL_PATH` a `config.py`. `microphone_module.py` l'importarà
> des d'allà (el té en lazy load a `transcribe()`).
>
> Si canvies de `pywhispercpp` a una altra llibreria (p.ex. `faster-whisper`),
> l'única cosa que canvia és el bloc `transcribe()` — **no toca** res de
> `record_while_held()` ni `save()`.

---

## Com provar-ho de forma aïllada (PAS 2 del pla de migració)

**Abans** de connectar-ho a `main.py`, prova'l amb un `.wav` ja existent
de `recordings/`:

```python
# test_stt.py (executa-ho des de la carpeta python/)
from microphone_module import MicrophoneManager
from pathlib import Path

mic = MicrophoneManager()
# agafa la primera gravació que trobi
wav = list(Path("recordings").glob("*.wav"))[0]
text = mic.transcribe(wav)
print(f"Transcripció: '{text}'")
```

```bash
cd python/
python test_stt.py
```

Si retorna text sense llençar excepcions, el mètode és llest.

---

## Com es crida des de `main.py` (quan estigui llest)

```python
# dins del loop, bloc is_recording_active, DESPRÉS de microphone.save():
wav_path = microphone.save(button_id, model_name, audio)

# NOU: pipeline Cultura Viva
question_text = microphone.transcribe(wav_path)
```

**`wav_path`** és el `Path` que ja retorna `save()` — no cal cap canvi a
`save()` per fer-ho servir.
