# `audio_playback_module.py` — mètode `synthesize_and_play()` pendent

**Estat**: ⏳ PENDENT D'IMPLEMENTAR — `AudioPlayer.synthesize_and_play()` **no
existeix** encara al fitxer. El que sí existeix i funciona (verificat):
- `play(audio_path)` ✅
- `save_response(audio_bytes)` ✅
- `_resolve_device()` ✅ (fix Bluetooth d'aquesta sessió)
- `reset_bluetooth_cache()` ✅

**NO tocar cap d'aquests** quan implementis `synthesize_and_play()`.

---

## Mètode a afegir

```python
def synthesize_and_play(self, text: str) -> bool:
    """Sintetitza text a veu amb Piper TTS, desa el .wav a RESPONSES_DIR
    i el reprodueix pels auriculars Bluetooth. Retorna True si ha anat bé.

    Reutilitza save_response() i play() ja existents i verificats.
    """
```

### On afegir-lo dins del fitxer

Al final de la classe `AudioPlayer`, **després** de `save_response()`.

---

## Implementació amb Piper TTS

```python
import subprocess
from config import TTS_MODEL_PATH, TTS_CONFIG_PATH

def synthesize_and_play(self, text: str) -> bool:
    try:
        result = subprocess.run(
            [
                "piper",
                "--model", str(TTS_MODEL_PATH),
                "--config", str(TTS_CONFIG_PATH),
                "--output_raw",
            ],
            input=text.encode("utf-8"),
            capture_output=True,
            check=True,
            timeout=30,
        )
        # result.stdout és l'àudio PCM raw -- l'emboliquem en WAV
        audio_bytes = _pcm_to_wav(result.stdout, sample_rate=22050)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        print(f"[ERROR] Piper TTS ha fallat: {exc}")
        return False

    out_file = self.save_response(audio_bytes)   # ja existent
    return self.play(out_file)                    # ja existent, ja verificat
```

On `_pcm_to_wav` és una funció auxiliar que cal afegir a l'arxiu
(fora de la classe) per afegir la capçalera WAV al PCM raw de Piper:

```python
import struct

def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 22050,
                channels: int = 1, sampwidth: int = 2) -> bytes:
    """Embolcalla bytes PCM raw (int16 little-endian) en un fitxer WAV vàlid."""
    import io, wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()
```

---

## Model Piper TTS necessari — `TTS_MODEL_PATH` a `config.py`

Piper necessita dos fitxers per veu: el model `.onnx` i el seu
`.onnx.json` de configuració.

**Recomanat per català:** `ca_ES-upc_pau-medium` (veu masculina) o
`ca_ES-upc_ona-x_low` (veu femenina lleugera).

**On posar-los:**
```
python/
└── models/
    └── tts/
        ├── ca_ES-upc_pau-medium.onnx
        └── ca_ES-upc_pau-medium.onnx.json
```

**Com descarregar-los:**
```bash
# Directament des de piper-tts releases
cd python/models/tts/
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/ca/ca_ES/upc_pau/medium/ca_ES-upc_pau-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/ca/ca_ES/upc_pau/medium/ca_ES-upc_pau-medium.onnx.json
```

**Instal·lar `piper` (binari del sistema):**
```bash
# Paquet wheel per ARM64 Linux
pip install piper-tts
# O des del repositori oficial: https://github.com/rhasspy/piper
```

**Afegir a `config.py` quan el tinguis:**
```python
TTS_MODEL_PATH   = MODELS_DIR / "tts" / "ca_ES-upc_pau-medium.onnx"
TTS_CONFIG_PATH  = MODELS_DIR / "tts" / "ca_ES-upc_pau-medium.onnx.json"
```

> ⚠️ **Si canvies de veu o de model TTS**: actualitza `TTS_MODEL_PATH` i
> `TTS_CONFIG_PATH` a `config.py`. El mètode `synthesize_and_play()` els
> importa des d'allà.
>
> Si canvies de Piper a una altra eina TTS, l'única cosa que canvia és
> el bloc `synthesize_and_play()` — **no toca** `play()` ni `save_response()`
> ni cap de la lògica Bluetooth.

---

## Com provar-ho de forma aïllada (PAS 5 del pla de migració)

**Antes** de connectar-ho a `main.py`, prova-ho sol amb un text curt —
hauria de sonar pels RZ-B100W:

```python
# test_tts.py (executa-ho des de la carpeta python/)
from audio_playback_module import AudioPlayer

player = AudioPlayer()
ok = player.synthesize_and_play("Hola, soc la guia de Park Güell.")
print("OK" if ok else "ERROR")
```

```bash
cd python/
python test_tts.py
```

Si sona als auriculars Bluetooth sense errors, el mètode és llest.

---

## Com es crida des de `main.py` (quan estigui llest)

```python
from audio_playback_module import AudioPlayer
player = AudioPlayer()

# dins del loop, bloc is_recording_active, al FINAL de la pipeline:
answer = models.generate_response(
    question=question_text,
    element=element,
    personality=model_name,
    kg_context=kg_context,
)
player.synthesize_and_play(answer)
```
