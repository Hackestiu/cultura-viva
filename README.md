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
│   ├── setup_whisper_cpp.sh # Lean compilation script for Arduino UNO Q
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── data_audio/      # synthetic manifest + WAVs; data_audio/recorded/ for human speech
│   ├── models/          # Compiled whisper-cli binary & downloaded model weights
│   ├── results_computer/ # JSON reports + plots from local runs
│   └── results_arduino/  # written by App Lab runs on the UNO Q, per app.yaml
├── sketch/               # MCU (Zephyr) side — placeholder, this app is Python-only
│   ├── sketch.ino
│   └── sketch.yaml
```

---

## Benchmark Models

The benchmark evaluates edge-capable English STT models optimized for the **Arduino UNO Q** (4x ARM Cortex-A53 @ 2.0 GHz):

- **Primary Target Model (Default):** `whisper.cpp:base.en-q5_0` (Whisper Base 5-bit quantized GGML model running natively in C++ with ARM NEON SIMD vector optimization).
- **Other Available Models (Preserved in Codebase):**
  - `whisper.cpp:base.en-q4_0` (Whisper Base 4-bit quantized GGML model).
  - `faster-whisper:base.en` (Whisper Base in CTranslate2 INT8).
  - `faster-whisper:tiny.en` (Whisper Tiny in CTranslate2 INT8).
  - `vosk` (Kaldi acoustic model for English).
  - `sherpa-onnx` (Zipformer Transducer ONNX model).

---

## Target Optimizations (Arduino UNO Q)

To run `Whisper Base` smoothly on the Arduino UNO Q's 4x ARM Cortex-A53 processor with minimal latency and low RAM footprint, the following optimizations are applied:

1. **ARM NEON SIMD & Native C++ (`whisper.cpp`):** Direct 128-bit vector processing on ARMv8 CPU cores without Python runtime overhead.
2. **Quantization (`q5_0` / `q4_0` / `int8`):** Reduces model memory footprint to ~60 MB (`q5_0`) or ~45 MB (`q4_0`), cutting memory bandwidth pressure while preserving high transcription accuracy.
3. **4 CPU Threads (`--cpu-threads 4`):** Spreads the tensor computation parallelly across all 4 physical CPU cores.
4. **Greedy Search (`--whisper-beam-size 1`):** Fast single-pass decoding without exploring candidate branches.
5. **Minimal Disk Footprint with `uv`:** The compiled `whisper-cli` binary is stripped to ~2.5 MB, and intermediate build files are cleaned up, avoiding heavy disk usage on the board.

---

## Domain-Vocabulary Bias 

Domain vocabulary bias is always enabled by default. It injects Cultura Viva domain keywords (*Antoni Gaudí, Sagrada Família, basilica, facade, modernisme, Catalan, Casa Batlló, Casa Milà, Park Güell, trencadís, salamander, dragon, Barcelona, Passeig de Gràcia*) as contextual prompts and hotwords, and applies phonetic entity canonicalization to ensure top accuracy on cultural terms.

Every exported prediction record indicates `domain_bias_applied: true` for compatible engines.

---

## Dataset & Domain Keywords

`python/data_audio/manifest.json` contains synthetic benchmark ground truth; real human speech recordings should be placed under `python/data_audio/recorded/`.

Audio files **must** be 16 kHz, mono, 16-bit PCM WAV (the benchmark automatically normalizes other formats if needed).

---

## Arduino UNO Q Execution Guide

Follow these steps to setup, compile, and execute the benchmark on the Arduino UNO Q Debian Linux environment.

### Step 1: System Performance Configuration
Open a terminal on the Arduino UNO Q and lock all 4 CPU cores to maximum clock frequency (2.0 GHz) and set OpenMP / OpenBLAS thread limits:

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

### Step 3: Setup & Compile whisper.cpp with ARM NEON
Navigate to the `python` directory and execute the lean setup script to compile `whisper-cli` with ARM NEON optimizations and download the quantized model (~60 MB):

```bash
cd ~/ArduinoApps/stt-benchmark/python

# Compiles whisper.cpp with ARM NEON and downloads ggml-base.en-q5_0.bin:
bash setup_whisper_cpp.sh base.en-q5_0
```

### Step 4: Sync Python Dependencies with `uv`
```bash
uv sync
```

### Step 5: Run Benchmark
By default, the benchmark runs the optimized **`whisper.cpp:base.en-q5_0`** model:

```bash
# Optimized execution:
uv run python main.py --output-dir results_arduino
```

#### Running Other Available Models:
To run 4-bit quantization or compare against other preserved engines, pass the `--engines` argument:

```bash
# Run 4-bit quantized Whisper Base:
# (First download the model with: bash setup_whisper_cpp.sh base.en-q4_0)
uv run python main.py --engines whisper.cpp:base.en-q4_0 --output-dir results_arduino

# Compare against faster-whisper Base INT8:
uv run python main.py --engines faster-whisper:base.en --output-dir results_arduino

# Run Vosk or Sherpa-ONNX:
uv run python main.py --engines vosk sherpa-onnx --output-dir results_arduino
```

---

## Local Execution (Host Computer)

For baseline testing or computer-side comparisons:

```bash
cd python
uv sync
uv run python main.py --output-dir results_computer
```

Results will be written to `python/results_computer/`.

---

## Results & Visualizations (`visualize.py`)

After the benchmark finishes executing on the Arduino UNO Q, run `visualize.py` to generate visual performance reports and an interactive HTML dashboard across all benchmarked models:

```bash
cd python
uv run visualize.py --input-dir results_arduino
```

This generates in `results_arduino/plots/`:
- **Performance Summary Dashboard** (`plots/dashboard_summary.png`): Combined WER/CER, Latency, RTF, and Peak RAM footprint.
- **Real-Time Factor (RTF) Analysis** (`plots/rtf_realtime_factor.png`): Evaluates execution speed relative to real-time audio playback (`RTF < 1.0`).
- **Interactive Evaluation Report** (`plots/evaluation_report.html`): Self-contained HTML report.

### Comparing Host Computer vs. Arduino UNO Q:
If you have run the benchmark on both a PC and the Arduino board:

```bash
uv run visualize.py --input-dir results_arduino --compare-with results_computer
```