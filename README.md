# Cultura Viva STT Benchmark

Offline English speech-to-text benchmark for Cultura Viva. Compares and evaluates 
STT engines on recognition quality and resource usage, optimized for deployment on 
an **Arduino UNO Q** (Qualcomm Dragonwing QRB2210 - 4x ARM Cortex-A53 @ 2.0 GHz) 
via Arduino App Lab.

This repository is a runnable Arduino App Lab app: the whole `stt-benchmark/` folder 
— `app.yaml`, `python/`, and `sketch/` — can be copied onto a UNO Q as-is and started 
with App Lab once models and recordings are in place.

---

## Repository layout

```text
stt-benchmark/
├── app.yaml            # App Lab manifest (Python entry point + MCU linkage)
├── python/             # Runnable benchmark (MPU / Debian Linux side)
│   ├── main.py
│   ├── benchmark.py
│   ├── dataset_generator.py
│   ├── utils.py
│   ├── visualize.py
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

---

## Target Model & Optimizations (Arduino UNO Q)

The primary target model for deployment is **Whisper Base** (`faster-whisper:base.en`).

To run `Whisper Base` smoothly on the Arduino UNO Q's 4x ARM Cortex-A53 processor without thermal throttling or high latency, the following optimizations are applied:

1. **INT8 Quantization (`--compute-type int8`):** Reduces RAM usage to ~200 MB and leverages ARM NEON vector processing.
2. **4 CPU Threads (`--cpu-threads 4`):** Spreads the tensor math parallelly across all 4 CPU cores.
3. **Greedy Search (`--whisper-beam-size 1`):** Fast single-pass decoding without exploring candidate branches.
4. **Voice Activity Detection (`vad_filter=True`):** Pre-filters audio silences to skip non-speech segments before hitting the Whisper decoder.

---

## Domain-vocabulary bias

Off by default; enabled with `--enable-domain-bias`. 
When enabled, domain-specific keywords (Gaudí, Sagrada Família, trencadís, etc.) are injected as initial prompts/hotwords.

Every prediction row records `domain_bias_applied` for the engine that produced it.

---

## Dataset & Domain Keywords

`python/data_audio/manifest.json` contains synthetic benchmark ground truth; real human speech recordings should be placed under `python/data_audio/recorded/`.

Audio files **must** be 16 kHz, mono, 16-bit PCM WAV.

---

## Arduino UNO Q Execution Guide

Follow these steps to execute the **Whisper Base** benchmark on the Arduino UNO Q Linux environment.

### Step 1: System Performance Configuration
Before running the benchmark, open a terminal on the Arduino UNO Q (Debian Linux side) and lock all 4 CPU cores to maximum clock frequency (2.0 GHz) and set OpenMP threads:

```bash
# Set CPU governor to maximum performance
sudo echo "performance" | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Set OpenMP and OpenBLAS thread limits to match physical cores
export OMP_NUM_THREADS=4
export OPENBLAS_NUM_THREADS=4
```

### Step 2: Prepare Recorded Audio Dataset
Copy the recorded WAV audio files and manifest to the board:
```text
~/ArduinoApps/stt-benchmark/python/data_audio/recorded/*.wav
~/ArduinoApps/stt-benchmark/python/data_audio/recorded/manifest.json
```

### Step 3: Run Benchmark (Whisper Base)
Navigate to the `python` directory and execute the runner specifying **Whisper Base** with INT8 precision:

```bash
cd python

# Execution:
uv run python main.py \
  --engines faster-whisper:base.en \
  --compute-type int8 \
  --cpu-threads 4 \
  --whisper-beam-size 1 \
  --enable-domain-bias \
  --output-dir results_arduino

---

## Local Execution (Host Computer)

For baseline testing or computer-side comparisons:

```bash
cd python
uv sync
uv run python main.py --engines faster-whisper:base.en --compute-type int8
```

Results will be written to `python/results_computer/`.

---

## Results & Visualizations (`visualize.py`)

After the benchmark finishes executing on the Arduino UNO Q, run `visualize.py` to generate visual performance reports and an interactive HTML dashboard.

```bash
cd python
uv run visualize.py --input-dir results_arduino
```

This generates:
- **Performance Summary Dashboard** (`plots/dashboard_summary.png`): Combined WER/CER, Latency, RTF, and Peak RAM footprint.
- **Real-Time Factor (RTF) Analysis** (`plots/rtf_realtime_factor.png`): Evaluates execution speed relative to real-time audio playback (`RTF < 1.0`).
- **Interactive Evaluation Report** (`plots/evaluation_report.html`): Self-contained HTML report.

### Comparing Host Computer vs. Arduino UNO Q:
If you have run the benchmark on both a PC and the Arduino board:

```bash
uv run visualize.py --input-dir results_arduino --compare-with results_computer
```