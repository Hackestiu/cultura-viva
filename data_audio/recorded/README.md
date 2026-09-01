# Curated Recorded Test Set

**This is the preferred dataset.** It's real human speech, not synthetic TTS, so
it's the more representative test of real-world recognition quality. When this
folder contains a valid `manifest.json` and its WAV files, `uv run main.py` (with
no `--audio-dir`/`--manifest` flags) uses it automatically and does not fall
back to the synthetic set — see `resolve_dataset` in `main.py`.

## Installation

The package is distributed separately via the project Drive link (see the root
[README](../../README.md)) because it contains real human voices and isn't
committed to Git. To use it:

1. Download the package from Drive (https://drive.google.com/drive/folders/1Mh7SzZXO3wE7YzRpU9vlUwrwgAqhhxot?usp=sharing). 
2. Extract its `recorded` folder so its contents land directly under
  `data_audio/recorded/` in this repo — i.e. this file's directory should end
   up containing the package's WAV files and `manifest.json` alongside it.
3. Run `uv run main.py` from the repository root with no dataset flags — the recorded set is
   picked up automatically. No extra flags or environment variables are needed for
   local runs.

If this folder is empty or has no `manifest.json`, the benchmark falls back to the
synthetic set in `data_audio/` and generates it if missing.

## Audio Requirements & Conversion

> **Strict Format Requirement:** All audio files added to this dataset **must be 16 kHz, mono, 16-bit PCM WAV**. 

If your recordings were captured at higher sample rates (e.g., 44.1 kHz or 48 kHz), you must convert/downsample them to 16 kHz before running the benchmark or adding them to `manifest.json`.

### How to Convert Audio to 16 kHz

**Windows (PowerShell)**
Batch-resample and replace all `.wav` files in your directory using FFmpeg:
```powershell
Get-ChildItem *.wav | ForEach-Object { ffmpeg -i $_.FullName -ar 16000 "temp_$($_.Name)" -y; Move-Item "temp_$($_.Name)" $_.FullName -Force }
```


**Linux (Terminal)**
Using FFmpeg or SoX:
```bash
# FFmpeg
for f in *.wav; do ffmpeg -i "$f" -ar 16000 "16k_$f"; done

# SoX
for f in *.wav; do sox "$f" -r 16000 "16k_$f"; done
```

---

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
place), using explicit dataset paths:

```powershell
uv run main.py --audio-dir data_audio\recorded --manifest data_audio\recorded\manifest.json
```
