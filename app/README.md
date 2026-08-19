# Cultura Viva STT Benchmark

This directory contains the offline English speech-to-text benchmark for Cultura Viva. The benchmark can be used for local development and model comparison, and can also be deployed through Arduino App Lab on an Arduino UNO Q.

The benchmark evaluates recognition quality and resource usage across several candidate engines. It reports WER, CER, domain-keyword accuracy, real-time factor, inference latency, peak memory, and model size where available.

## Directory contents

- `data_audio/` contains the benchmark WAV files and `manifest.json`.
- `models/` is a Git-tracked directory placeholder; downloaded model contents remain local and are not committed.
- `results_computer/` contains JSON reports and plots from local computer runs.
- `results_arduino/` is used by Arduino App Lab, as configured in `app.yaml`.

The WAV files and model files are inputs to the benchmark. They must be prepared before running the application; the Arduino does not generate or download them automatically at startup.

## General workflow

1. Generate the audio on a computer with internet access.
2. Run a quick benchmark on the computer.
3. Package the application together with the generated WAV files.
4. Copy the model files to the Arduino separately.
5. Run the packaged application on the Arduino.

The recommended process is to generate and validate the dataset on a computer, package the application with the generated audio, transfer the model files separately, and then run the benchmark on the Arduino. This keeps dataset creation independent from the edge runtime.

## Dataset generation

Run the following commands from the `app` directory. Edge TTS is the supported generation engine and requires internet access:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python dataset_generator.py
```

This creates 24 WAV files and updates `data_audio/manifest.json`. The corpus includes adult masculine, adult feminine, and child-like voices, as well as selected stutters, pauses, and background-noise examples.

If Edge TTS returns an error, the command stops. It never replaces the requested voices with a local voice.

**Disclaimer:** Recorded audio is preferable for final realism; the generated TTS corpus is retained as a reproducible baseline while recorded samples are pending.

## Local execution

After generating the dataset, a single model can be used for a quick validation run:

```powershell
python main.py --engines faster-whisper:tiny.en
```

Results are written to `results_computer/`. Each engine writes its predictions to `results_computer/predictions/<engine>.json`, aggregate metrics are written to `results_computer/summary.json`, and comparison plots are written to `results_computer/plots/`. No CSV or duplicate aggregate predictions file is generated. The first faster-whisper run may download its model automatically. Local timings and memory measurements are useful for development and comparison, but they should not be interpreted as Arduino performance measurements.

To compare all configured engines, run:

```powershell
python main.py
```

The benchmark writes JSON reports and plots which summarize recognition quality, inference latency, and resource usage. The plots include the original average inference-time and average WER charts, along with the newer recognition-quality, latency, and resource-usage comparisons. They are derived from the JSON reports and are not required for benchmark execution. Latency and RTF are measured after model loading; peak RAM is a host-side process measurement and should be verified separately on the Arduino.

The local runner automatically looks for bundled model files under `models/`. Engines whose Python dependency or model files are missing are skipped with a message. Vosk and sherpa-onnx should therefore work locally without setting environment variables when their directories are present in `models/`.

To verify the two bundled engines directly:

```powershell
python main.py --engines vosk sherpa-onnx
```

If the models are stored somewhere else, set their paths before running. Replace these example paths with directories that actually contain the complete extracted models:

```powershell
$env:VOSK_MODEL_DIR = 'D:\models\vosk-model-small-en-us-0.15'
$env:SHERPA_ONNX_MODEL_DIR = 'D:\models\sherpa-onnx-en'
python main.py --engines vosk sherpa-onnx
```

If the models are in this repository's `models/` directory, do not set these variables; the benchmark finds the bundled paths automatically. A valid Vosk directory must contain subdirectories such as `am/`, `conf/`, `graph/`, and `ivector/`. A valid sherpa-onnx directory must contain the matching encoder, decoder, and tokens files.

## Arduino deployment

The dataset must be generated before packaging. The WAV files are included in the application archive, so `dataset_generator.py` does not need to run on the Arduino. This also avoids requiring Edge TTS internet access on the device.

Create the archive from a clean staging directory. The following PowerShell commands include the generated WAV files while excluding the virtual environment, model binaries, and previous results:

```powershell
$stage = Join-Path $env:TEMP "cultura-viva-app"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item $stage -ItemType Directory | Out-Null
Get-ChildItem app -Force | Where-Object { $_.Name -notin @('.venv', '__pycache__', 'models', 'results_computer', 'results_arduino') } | Copy-Item -Destination $stage -Recurse -Force
Compress-Archive -Path "$stage\*" -DestinationPath cultura-viva-app.zip -Force
```

If using Git Bash or WSL, the equivalent command is:

```bash
cd app
zip -r ../cultura-viva-app.zip . -x '.venv/*' '__pycache__/*' '*.bin' '*.gguf' '*.onnx' 'results_computer/*' 'results_arduino/*'
```

`app.yaml` starts the benchmark with `OUTPUT_DIR: results_arduino`.

## Model installation

The repository already contains the expected Vosk and sherpa-onnx directory layouts. For a fresh local installation, download or extract the following models into `app/models/`:

```text
models/
├── vosk-model-small-en-us-0.15/
└── sherpa-onnx-en/
```

### Model sources

| Engine | Model source | Local destination |
| --- | --- | --- |
| faster-whisper tiny.en | [Systran/faster-whisper-tiny.en on Hugging Face](https://huggingface.co/Systran/faster-whisper-tiny.en) | Hugging Face cache; downloaded automatically by faster-whisper |
| faster-whisper base.en | [Systran/faster-whisper-base.en on Hugging Face](https://huggingface.co/Systran/faster-whisper-base.en) | Hugging Face cache; downloaded automatically by faster-whisper |
| sherpa-onnx Whisper English | [csukuangfj/sherpa-onnx-whisper-tiny.en on Hugging Face](https://huggingface.co/csukuangfj/sherpa-onnx-whisper-tiny.en) | `models/sherpa-onnx-en/` |
| Vosk small English | [Official Alpha Cephei model page](https://alphacephei.com/vosk/models) | `models/vosk-model-small-en-us-0.15/` |

Install the Hugging Face command-line tool once:

```powershell
python -m pip install "huggingface_hub[cli]"
```

From the `app` directory, download the Hugging Face models with:

```powershell
hf download Systran/faster-whisper-tiny.en
hf download Systran/faster-whisper-base.en
hf download csukuangfj/sherpa-onnx-whisper-tiny.en --local-dir .\models\sherpa-onnx-en
```
Vosk is distributed as a ZIP from Alpha Cephei rather than as a Hugging Face repository. Download `vosk-model-small-en-us-0.15`, extract it, and place the complete extracted directory at `models/vosk-model-small-en-us-0.15/`.

For Arduino deployment, model binaries are not included in the standard application archive because of their size. Copy the same required model directories and files to the Arduino under `/app/models/`, matching the paths in `app.yaml`. The App Lab environment variables point Vosk and sherpa-onnx to those locations automatically. The faster-whisper models may be downloaded by the library on first use, depending on the device environment. Engines with missing optional dependencies or model files are skipped; at least one installed engine and model is required for a useful benchmark.

## Audio and manifest requirements

Audio must be 16 kHz, mono, 16-bit PCM WAV. The manifest contains the exact ground-truth transcript, domain keywords, pronunciation hints, and audio-effect metadata for every file. If you change a query, regenerate the WAV files and manifest together.

