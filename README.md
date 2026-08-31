# Cultura Viva STT Benchmark

Offline English speech-to-text benchmark for Cultura Viva. Compares candidate STT
engines on recognition quality and resource usage, for local development and for
deployment on an Arduino UNO Q via Arduino App Lab.

This repository is itself a runnable Arduino App Lab app: the whole
`stt-benchmark/` folder — `app.yaml`, `python/`, and `sketch/` — can be copied
onto a UNO Q as-is and started with App Lab once models and
recordings are in place.

## Repository layout

```text
stt-benchmark/
├── app.yaml            # App Lab manifest (Python entry point + MCU linkage)
├── python/              # the runnable benchmark (MPU / Debian Linux side)
│   ├── main.py
│   ├── benchmark.py
│   ├── dataset_generator.py
│   ├── utils.py
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── data_audio/      # synthetic manifest + WAVs; data_audio/recorded/ for human speech
│   ├── models/          # Git-tracked placeholder — downloaded model files stay local
│   ├── results_computer/ # JSON reports + plots from local runs
│   └── results_arduino/  # written by App Lab runs on the UNO Q, per app.yaml
├── sketch/               # MCU (Zephyr) side — placeholder, this app is Python-only
│   ├── sketch.ino
│   └── sketch.yaml
```

- `app.yaml` is the App Lab manifest for this app. It points to the Python
  entry point (`python/main.py`), declares output/model paths for the device,
  and links the MCU sketch under `sketch/` so App Lab can
  build and run both halves together. On the device it sets `OUTPUT_DIR:
  results_arduino` and points `VOSK_MODEL_DIR`/`SHERPA_ONNX_MODEL_DIR` at the
  on-device model paths automatically.
- `sketch/sketch.ino` and `sketch/sketch.yaml` exist only so this is a valid
  App Lab app structure. The MCU side is not used by this benchmark — see the
  comments in `sketch.ino`.

## Tested models

- faster-whisper `tiny.en` and `base.en`
- Vosk small English
- sherpa-onnx `zipformer-small-en`

See `python/models/README.md` for install sources and paths.

## Domain-vocabulary bias

Off by default; enabled with `--enable-domain-bias`. When enabled:

```text
faster-whisper (tiny.en, base.en)  — yes
sherpa-onnx (zipformer-small-en)   — yes
vosk                                — no
```

Every prediction row records `domain_bias_applied` for the engine that produced it.

## Dataset & domain keywords

`python/data_audio/manifest.json` is the synthetic benchmark ground truth; a
separate recorded human-speech set is distributed outside the repo. See
`python/data_audio/recorded/README.md` for the recorded set.

Audio must be 16 kHz, mono, 16-bit PCM WAV, matching the manifest schema. If you
change a query, regenerate the WAV files and manifest together.

## Evaluation metrics

Per utterance and aggregate reports include:

- **WER**, **CER** — word/character error rate against the manifest's ground truth.
- **Domain keyword spotting accuracy** — recovery rate of the canonical heritage
  entities (Gaudí, Sagrada Família, trencadís, etc.) listed in a clip's `keywords`.
- **RTF** (real-time factor) and **inference latency** (ms) — measured after model
  loading; load time is excluded.
- **Peak RAM** (MB) — host-side process measurement; treat as a comparison signal,
  not an Arduino deployment measurement.
- **Model size on disk** (MB), where the model path is local.
- **`domain_bias_applied`** — whether the domain-vocabulary hint was actually applied
  for that engine on that run (see "Domain-vocabulary bias" above).

Each engine writes a schema-versioned JSON file under `predictions/`; aggregate
metrics go in `summary.json`. Comparison plots are derived from the JSON reports
and are optional.

## Local execution (computer)

```powershell
cd python
uv sync
uv run python main.py --engines faster-whisper:tiny.en
```

The application prefers the recorded dataset when its manifest and WAV files are
present; otherwise it uses the synthetic set, generating it first if needed
(requires internet access for Edge TTS — intended for a computer, not the Arduino).

Results are written to `python/results_computer/`: per-engine predictions under
`results_computer/predictions/<engine>.json`, aggregate metrics in
`results_computer/summary.json`, and plots under `results_computer/plots/`.

To compare all configured engines:

```powershell
python main.py
```

To apply the domain-vocabulary hint to every engine that supports it (see
"Domain-vocabulary bias" above for which engines that is):

```powershell
python main.py --enable-domain-bias
```

Engines with missing Python dependencies or model files are skipped with a
message — at least one installed engine and model is required for a useful run.

### Engine model paths

The runner looks for bundled model files under `python/models/` by default. If
your models live elsewhere, set their paths before running (see
`python/models/README.md` for what each path must contain):

```powershell
$env:VOSK_MODEL_DIR = 'D:\models\vosk-model-small-en-us-0.15'
$env:SHERPA_ONNX_MODEL_DIR = 'D:\models\sherpa-onnx-en'
python main.py --engines vosk sherpa-onnx
```

### Recorded audio set

To test the recorded package on a computer, extract it under
`python/data_audio/recorded/` (see `python/data_audio/recorded/README.md`) and run:

```powershell
python main.py --audio-dir data_audio\recorded --manifest data_audio\recorded\manifest.json
```

### Experiment tracking (optional)

```powershell
uv add wandb
wandb login
uv run python main.py --wandb --enable-domain-bias
```

Logs, per run: full CLI config, `dataset_source` (recorded/synthetic) and
`domain-bias-on`/`domain-bias-off` as tags, a per-utterance predictions table
(including `raw_transcription` vs. the canonicalized `transcription`, so cosmetic
name-fixing can be distinguished from real recognition errors), per-engine
aggregate metrics, and the `predictions/` JSON files plus the domain-bias hotwords
file (when used) as a versioned artifact. Off by default — nothing changes if
you don't pass `--wandb`.

## Arduino App Lab deployment

This repo's root is laid out as an App Lab app (`app.yaml` + `python/` + `sketch/`),
so the whole `stt-benchmark/` folder is what you deploy — no separate packaging
step is required. Models, the recorded audio set, and previous local results are
kept out of git and are copied to the device separately, alongside the code.

1. **Install App Lab** and run it at least once against your UNO Q to configure
   the board and update its packages/firmware.
2. **Get the app onto the device.** 
3. **Copy models and the recorded audio set onto the device separately**, laid
   out as:
   ```text
   ~/ArduinoApps/stt-benchmark/python/data_audio/recorded/*.wav
   ~/ArduinoApps/stt-benchmark/python/data_audio/recorded/manifest.json
   ```
   and the models as documented in `python/models/README.md`, matching the
   device paths referenced in `app.yaml`.
4. **Run the app.** 

`sketch/` is only present because App Lab apps require an MCU half; it's an
intentional no-op here (see `sketch/sketch.ino`) since this benchmark doesn't
use the board's MCU or the Python↔MCU Bridge.


## Results / findings & Visualizations

Local CPU runs write to `python/results_computer/`; App Lab runs on the device
write to `python/results_arduino/`. Re-run on the target UNO Q before making
deployment decisions — host timings and RAM are not edge measurements.

### Visual performance evaluation (`visualize.py`)

After running the benchmark (on the Arduino UNO Q or computer), run `visualize.py` to generate visual representations and an interactive HTML report:

```powershell
cd python
uv run visualize.py
```

`visualize.py` automatically detects benchmark outputs (prioritizing `results_arduino/`, then `results_computer/`), and generates:

- **Performance Summary Dashboard** (`plots/dashboard_summary.png`): All-in-one scorecard comparing WER/CER accuracy, latency, Real-Time Factor (RTF), and memory footprint.
- **Accuracy vs. Latency Pareto Frontier** (`plots/accuracy_vs_latency_pareto.png`): Trade-off scatter plot highlighting Pareto-optimal models.
- **Real-Time Factor (RTF) Analysis** (`plots/rtf_realtime_factor.png`): Evaluates edge streaming feasibility against the `RTF = 1.0` real-time boundary.
- **Per-Utterance Distributions** (`plots/error_distribution_boxplots.png`): Robustness boxplots showing error variance across test clips.
- **Interactive Evaluation Report** (`plots/evaluation_report.html`): Self-contained HTML report with model rankings and recommendations.

#### Advanced visualization options:

```powershell
# Explicitly evaluate Arduino results:
uv run visualize.py --input-dir results_arduino

# Compare Arduino UNO Q vs. Host Computer directly:
uv run visualize.py --input-dir results_arduino --compare-with results_computer

# Display interactive matplotlib window:
uv run visualize.py --show
```

