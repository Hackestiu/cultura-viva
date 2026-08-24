# Curated Recorded Test Set

**This is the preferred dataset.** It's real human speech, not synthetic TTS, so
it's the more representative test of real-world recognition quality. When this
folder contains a valid `manifest.json` and its WAV files, `python main.py` (with
no `--audio-dir`/`--manifest` flags) uses it automatically and does not fall
back to the synthetic set — see `resolve_dataset` in `main.py`.

## Installation

The package is distributed separately via the project Drive link (see the root
[README](../../../README.md)) because it contains real human voices and isn't
committed to Git. To use it:

1. Download the package from Drive (https://drive.google.com/drive/folders/1Mh7SzZXO3wE7YzRpU9vlUwrwgAqhhxot?usp=sharing). 
2. Extract its `recorded` folder so its contents land directly under
   `app/data_audio/recorded/` in this repo — i.e. this file's directory should end
   up containing the package's WAV files and `manifest.json` alongside it.
3. Run `python main.py` from `app/` with no dataset flags — the recorded set is
   picked up automatically. No extra flags or environment variables are needed for
   local runs.

If this folder is empty or has no `manifest.json`, the benchmark falls back to the
synthetic set in `data_audio/` and generates it if missing.

Format: 16 kHz, mono, 16-bit PCM WAV, one row per file in this directory's own
`manifest.json`.

## Manifest schema

```json
[
  {
    "filename": "query_01_spk01_take01.wav",
    "language": "en",
    "text": "Tell me about Gaudí.",
    "keywords": ["Gaudí"]
  }
]
```

`filename` is relative to this directory. Keep the reference transcript exact, but
use canonical keyword spellings — the benchmark accepts accented and unaccented
aliases when scoring, and restores canonical accents (e.g. `Gaudí`, `Casa Batlló`,
`trencadís`) in its final transcription regardless of how the source audio was
pronounced.

Recordings should use the same sentences as `data_audio/manifest.json`'s `text`
field, plus the short keyword-focused sentences described in `recording_script.md`.

## Running this set explicitly

Auto-detection covers the default case; use explicit flags only if you need to
point at a *different* recorded copy (e.g. testing a package before moving it into
place), or on the Arduino, where `app.yaml` sets `AUDIO_DIR`/`MANIFEST` to these
paths explicitly:

```powershell
cd app
python main.py --audio-dir data_audio\recorded --manifest data_audio\recorded\manifest.json
```

On the Arduino, the same layout is expected at `/app/data_audio/recorded/`.