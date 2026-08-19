# English benchmark audio

Place one English visitor query per PCM WAV file here. Use 16 kHz, mono, 16-bit audio and keep each clip approximately 3 to 20 seconds. The generated benchmark has 24 varied clips covering eight recurring intents. Some clips have a context sentence before the question, while others begin directly with the question. Registers and speaker types also vary by clip. A few clips deliberately include a repeated word, an inserted pause, or low-level deterministic background noise to test robustness. `keywords` lists the canonical heritage entities expected in the reference and is used for keyword spotting accuracy:

```json
[
  {
    "filename": "query_01_casual_materials.wav",
    "language": "en",
    "register": "casual",
    "intent": "materials",
    "lead_in": "We have just arrived at this part of the tour.",
    "question": "What is this amazing wall made of?",
    "keywords": ["Gaudí", "trencadís"],
    "audio_effects": {"pause_ms": 0, "background_noise_level": 0},
    "speaker": "child_like",
    "voice": "en-US-AnaNeural",
    "text": "We have just arrived at this part of the tour. What is this amazing wall made of?"
  }
]
```

Generate the supplied synthetic set from the `app` directory. Audio and manifest must be regenerated together whenever query text or keyword annotations change:

```bash
python app/dataset_generator.py
```

The generated set mixes adult masculine, adult feminine, and child-like Edge TTS voice profiles. The manifest also records pronunciation hints. For example, the spoken synthesis text uses `uh-PREE-shee-ate` while the canonical ground truth remains `appreciate`, so WER is scored against normal English spelling. Manually recorded or externally generated WAV files are supported when they match the same format and manifest schema. The old `.ogg`/`.m4a` files are historical notebook data and are not part of the production benchmark.
