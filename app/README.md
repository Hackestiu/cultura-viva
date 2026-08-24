# Cultura Viva STT Benchmark — App

This directory contains the runnable offline English STT benchmark. It runs locally
for development and model comparison, and can be deployed through Arduino App Lab
on an Arduino UNO Q.

## Directory contents

- `data_audio/` — synthetic benchmark manifest and WAV inputs. See
  [data_audio/README.md](data_audio/README.md).
- `data_audio/recorded/` — human-speech test set, downloaded separately. See
  [data_audio/recorded/README.md](data_audio/recorded/README.md).
- `models/` — Git-tracked placeholder; downloaded model contents stay local. See
  [models/README.md](models/README.md) for what to install and where.
- `cache/` — generated at runtime (currently: the sherpa-onnx hotwords file built
  from `utils.DOMAIN_KEYWORD_ALIASES` when `--enable-domain-bias` is on). Not
  committed to Git.
- `results_computer/` — JSON reports and plots from local runs.
- `results_arduino/` — used by Arduino App Lab, as configured in `app.yaml`.

## General workflow

1. Install dependencies and models (see [models/README.md](models/README.md)).
2. Prepare audio: generate the synthetic set, or fetch the recorded package (see
   [data_audio/README.md](data_audio/README.md) and
   [data_audio/recorded/README.md](data_audio/recorded/README.md)).
3. Run the benchmark on a computer.
4. Package the app and copy model files to the Arduino separately.
5. Run the benchmark on the Arduino with the selected audio set.

## Local execution

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py --engines faster-whisper:tiny.en
```

The application prefers the recorded dataset when its manifest and WAV files are
present; otherwise it uses the synthetic set, generating it first if needed
(requires internet access for Edge TTS — intended for a computer, not the Arduino).

Results are written to `results_computer/`: per-engine predictions under
`results_computer/predictions/<engine>.json`, aggregate metrics in
`results_computer/summary.json`, and plots under `results_computer/plots/`.

To compare all configured engines:

```powershell
python main.py
```

To apply the domain-vocabulary hint to every engine that supports it (see the root
[README](../README.md#domain-vocabulary-bias) for which engines that is):

```powershell
python main.py --enable-domain-bias
```

Engines with missing Python dependencies or model files are skipped with a message
— at least one installed engine and model is required for a useful run.

### Engine model paths

The runner looks for bundled model files under `models/` by default. If your models
live elsewhere, set their paths before running (see
[models/README.md](models/README.md) for what each path must contain):

```powershell
$env:VOSK_MODEL_DIR = 'D:\models\vosk-model-small-en-us-0.15'
$env:SHERPA_ONNX_MODEL_DIR = 'D:\models\sherpa-onnx-en'
python main.py --engines vosk sherpa-onnx
```

## Recorded audio set

To test the recorded package on a computer, extract it under `data_audio/recorded/`
(see [data_audio/recorded/README.md](data_audio/recorded/README.md)) and run:

```powershell
python main.py --audio-dir data_audio\recorded --manifest data_audio\recorded\manifest.json
```

## Arduino deployment

Package the application from a clean staging directory, excluding local
environments, model binaries, recordings, and previous results (models and the
recorded set are copied to the device separately):

```powershell
$stage = Join-Path $env:TEMP "cultura-viva-app"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item $stage -ItemType Directory | Out-Null
Get-ChildItem . -Force | Where-Object { $_.Name -notin @('.venv', '__pycache__', 'cache', 'models', 'results_computer', 'results_arduino', 'data_audio') } | Copy-Item -Destination $stage -Recurse -Force
New-Item (Join-Path $stage 'data_audio') -ItemType Directory | Out-Null
Copy-Item data_audio\manifest.json (Join-Path $stage 'data_audio') -Force
Copy-Item data_audio\*.wav (Join-Path $stage 'data_audio') -Force
Compress-Archive -Path "$stage\*" -DestinationPath ..\cultura-viva-app.zip -Force
```

Git Bash / WSL equivalent:

```bash
zip -r ../cultura-viva-app.zip . -x '.venv/*' '__pycache__/*' 'cache/*' 'data_audio/recorded/*' '*.bin' '*.gguf' '*.onnx' 'results_computer/*' 'results_arduino/*'
```

On the device, lay out the recorded set as:

```text
/app/data_audio/recorded/*.wav
/app/data_audio/recorded/manifest.json
```

and the models as documented in [models/README.md](models/README.md), matching the
paths in `app.yaml`. `app.yaml` starts the benchmark with `OUTPUT_DIR:
results_arduino` and points `VOSK_MODEL_DIR`/`SHERPA_ONNX_MODEL_DIR` at the device
paths automatically.

## Experiment tracking (optional)

```powershell
python -m pip install wandb
wandb login
python main.py --wandb --enable-domain-bias
```

Logs, per run: full CLI config, `dataset_source` (recorded/synthetic) and
`domain-bias-on`/`domain-bias-off` as tags, a per-utterance predictions table
(including `raw_transcription` vs. the canonicalized `transcription`, so cosmetic
name-fixing can be distinguished from real recognition errors), per-engine
aggregate metrics, and the `predictions/` JSON files plus the domain-bias hotwords
file (when used) as a versioned artifact. Off by default — nothing changes if
you don't pass `--wandb`.

## Audio format

Audio must be 16 kHz, mono, 16-bit PCM WAV, matching the manifest schema described
in [data_audio/README.md](data_audio/README.md). If you change a query, regenerate
the WAV files and manifest together.