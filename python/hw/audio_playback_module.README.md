# `audio_playback_module.py` — Text-to-Speech (`synthesize_and_play()`)

**Estat**: ✅ IMPLEMENTAT — `AudioPlayer.synthesize_and_play()` utilitza Piper TTS (`piper-tts` via API Python `PiperVoice`) amb routing per personalitat.

Funcionalitats actives:
- `play(audio_path)` ✅
- `save_response(audio_bytes)` ✅
- `set_volume(volume_percent)` ✅
- `synthesize_and_play(text, personality=None)` ✅

---

## Mètode `synthesize_and_play(text, personality=None)`

```python
def synthesize_and_play(self, text: str, personality: str | None = None) -> bool:
    """Sintetitza text a veu amb el model Piper corresponent a la personalitat,
    desa el .wav a RESPONSES_DIR i el reprodueix amb aplay.
    Retorna True si ha anat bé.
    """
```

### Mapping de personalitats i veus (Anglès):
| Personalitat | Mètric / Veu | Model ONNX stem | Speaker ID |
|---|---|---|---|
| `artistic` | `libriTTS_r_medium` (en-US, neutral) | `en_US-libritts_r-medium` | None |
| `technical` | `semaine_spike` (en-GB, masculí) | `en_GB-semaine-medium` | 1 |
| `child` | `semaine_prudence` (en-GB, femení) | `en_GB-semaine-medium` | 0 |

---

## Models Piper necessaris — `python/models/tts/`

Els fitxers ONNX i JSON han d'estar situats a `python/models/tts/`.
Veure instruccions detallades de descàrrega a [`python/models/tts/README.md`](../models/tts/README.md).

---

