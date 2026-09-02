# Pla de migració: pipeline Cultura Viva → Arduino App Lab

Aquest document és la guia de referència per integrar la pipeline de
Cultura Viva (STT → Visió → Graf de coneixement → SLM → TTS) dins
del projecte Arduino App Lab ja existent i verificat.

> ⚠️ **Regla d'or**: NO es toca cap nom de funció RPC existent
> (`is_recording_active`, `get_personality_index`, `has_gps_fix`,
> `get_gps_lat`, `get_gps_lon`, `photo_trigger`, `view_switch_state`,
> `mark_landmark_visited`, etc.) ni l'estructura del bucle de `main.py`
> que ja hem depurat. Tot el que segueix és **afegir** mètodes nous dins
> dels mòduls existents, no substituir-los.

---

## Mapa de fitxers: on va cada cosa

| Codi de Cultura Viva | Va a... | Estat |
|---|---|---|
| `src/speech/stt.py` | `hw/microphone_module.py` (mètode nou `transcribe()`) | ✅ Fet |
| `src/speech/slm.py` + `src/knowledge/knowledge_graph.py` | `model_module.py` (mètodes nous) | ✅ Fet |
| `src/vision/classifiers.py` | `vision_module.py` (fitxer NOU) | ✅ Fet |
| `src/speech/tts.py` | `hw/audio_playback_module.py` (mètode nou `synthesize_and_play()`) | ✅ Fet |
| `src/capture/camera.py` | `hw/camera_module.py` (`last_photo_path`) | ✅ Fet |
| `src/hw/.../bluetooth_manager.py` | Substituït per sortida Jack 3.5mm a `hw/audio_playback_module.py` | ✅ Fet |
| `src/main.py` | `main.py` (imports des de `hw.*`) | ✅ Fet |

---

## On trobar les instruccions de cada pas

Cada mòdul té el seu propi README amb les instruccions completes
(codi d'implementació, models necessaris, com provar-ho):

| Fitxer | README d'implementació |
|---|---|
| `hw/camera_module.py` | [`hw/camera_module.README.md`](hw/camera_module.README.md) |
| `hw/microphone_module.py` | [`hw/microphone_module.README.md`](hw/microphone_module.README.md) |
| `vision_module.py` | [`vision_module.README.md`](vision_module.README.md) |
| `model_module.py` | [`model_module.README.md`](model_module.README.md) |
| `hw/audio_playback_module.py` | [`hw/audio_playback_module.README.md`](hw/audio_playback_module.README.md) |
| `models/` (SLM + KG + Vision) | [`models/README.md`](models/README.md) |

---

## Ordre d'implementació recomanat

### Pas 1 — `camera_module.py`: afegir `last_photo_path`
Canvi mínim (dues línies), sense risc, sense dependències noves.
Veure `camera_module.README.md`.

### Pas 2 — `microphone_module.py`: afegir `transcribe()`
Necessita model Whisper GGML a `models/stt/`.
Constants noves a `config.py`: `STT_MODEL_PATH`.
**Provar sol** amb un `.wav` de `recordings/` existent.
Veure `microphone_module.README.md`.

### Pas 3 — `vision_module.py`: nou fitxer
Portar `src/vision/classifiers.py` de Cultura Viva.
Si necessita pesos, posar-los a `models/vision/`.
Constants noves a `config.py`: `VISION_MODELS_DIR` (si escau).
**Provar sol** amb una foto de `photos/` existent.
Veure `vision_module.README.md`.

### Pas 4 — `model_module.py`: afegir `get_kg_context()` i `generate_response()`
Necessita model Qwen2.5 GGUF a `models/slm/` i KG a `models/knowledge/`.
Constants noves a `config.py`: `SLM_MODEL_PATH`, `KG_PATH`.
**NO toca `name_for()`** — segueix igual.
**Provar sols** els dos mètodes amb text d'exemple.
Veure `model_module.README.md`.

### Pas 5 — `audio_playback_module.py`: afegir `synthesize_and_play()`
Necessita model Piper TTS a `models/tts/` i binari `piper` instal·lat.
Constants noves a `config.py`: `TTS_MODEL_PATH`, `TTS_CONFIG_PATH`.
**NO toca `play()` ni `_resolve_device()`** — segueixen igual.
**Provar sol** amb un text curt — ha de sonar pels RZ-B100W.
Veure `audio_playback_module.README.md`.

### Pas 6 — `config.py` i `requirements.txt`
Afegir totes les constants de model que surten als READMEs anteriors.
Afegir a `requirements.txt`: `pywhispercpp`, `llama-cpp-python`,
`piper-tts`, `opencv-python` (si no hi és ja).

### Pas 7 — `main.py`: connectar la pipeline
**NOMÉS quan cada peça funcioni sola**. Afegir dins del bloc
`is_recording_active`, just després de `microphone.save(...)`:

```python
from vision_module import VisionClassifier
from location_module import LocationRegistry
from audio_playback_module import AudioPlayer

vision   = VisionClassifier()
location = LocationRegistry()
player   = AudioPlayer()

# dins del loop():
if Bridge.call("is_recording_active"):
    personality_index = Bridge.call("get_personality_index")
    button_id  = "ABC"[personality_index]
    model_name = models.name_for(button_id)

    audio = microphone.record_while_held(
        is_still_held=lambda: Bridge.call("is_recording_active")
    )
    if audio is not None:
        wav_path = microphone.save(button_id, model_name, audio)

        # --- NOU: pipeline Cultura Viva ---
        question_text = microphone.transcribe(wav_path)
        site          = location.current()
        photo_path    = camera.last_photo_path
        element       = vision.classify(site, photo_path) if photo_path else None
        kg_context    = models.get_kg_context(element) if element else ""
        answer        = models.generate_response(
                            question=question_text,
                            element=element,
                            personality=model_name,
                            kg_context=kg_context,
                        )
        player.synthesize_and_play(answer)
```

### Pas 8 — Prova end-to-end a l'App Lab
Foto → pregunta enregistrada → resposta sentida pels auriculars RZ-B100W.

---

## Constants noves a afegir a `config.py` (resum global)

| Constant | Mòdul que la fa servir | Pas |
|---|---|---|
| `STT_MODEL_PATH` | `microphone_module.transcribe()` | 2 |
| `VISION_MODELS_DIR` | `vision_module.VisionClassifier` (si escau) | 3 |
| `SLM_MODEL_PATH` | `model_module.generate_response()` | 4 |
| `KG_PATH` | `model_module.get_kg_context()` | 4 |
| `TTS_MODEL_PATH` | `audio_playback_module.synthesize_and_play()` | 5 |
| `TTS_CONFIG_PATH` | `audio_playback_module.synthesize_and_play()` | 5 |

Cap d'aquestes constants existeix encara a `config.py` — afegir-les
quan es tinguin els fitxers de model reals.

> ⚠️ **Si en algun moment canvies de model** (Whisper, Qwen2.5, Piper,
> classificador de visió) **o de nom de fitxer**: l'únic lloc on cal
> canviar-ho és `config.py`. Cap mòdul té paths hardcodejats.
