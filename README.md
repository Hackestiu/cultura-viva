# Cultura Viva STT Benchmark

Offline English speech-to-text benchmark for Cultura Viva. Compares STT engines on
recognition quality, keyword accuracy, latency, RAM, and model size.

The primary target is `whisper.cpp:base.en-q5_1`, using the native `pywhispercpp`
binding. `q5_1` is a quantization variant, not a Whisper model version.

---

## Repository layout

```text
stt-benchmark/
├── main.py              # Benchmark entry point
├── benchmark.py         # Engines, measurements, and report export
├── utils.py             # Models, scoring, keywords, and audio helpers
├── dataset_generator.py # Synthetic dataset generator
├── visualize.py         # Result visualizations
├── pyproject.toml       # UV project definition
├── uv.lock              # Locked Python dependencies
├── data_audio/          # Synthetic and recorded datasets
├── models/              # Downloaded model weights
└── results_computer/    # JSON reports and plots
```

## Benchmark Models

The benchmark evaluates local English STT engines:

**Primary Target Model (Default):** `whisper.cpp:base.en-q5_1` (Whisper Base 5-bit quantized GGML model running natively via pywhispercpp Python bindings with ARM NEON SIMD vector optimization). `q5_1` is a quantization variant, not a Whisper model version; it is the current official Base English Q5_1 file available from the whisper.cpp model repository.

**Other Available Models (Preserved in Codebase):**

- `whisper.cpp:base.en-q5_0` (legacy Q5 comparison model, when available in the selected whisper.cpp mirror).
- `faster-whisper:base.en` (Whisper Base in CTranslate2 INT8).
- `faster-whisper:tiny.en` (Whisper Tiny in CTranslate2 INT8).
- `vosk` (Kaldi acoustic model for English).
- `sherpa-onnx` (Zipformer Transducer ONNX model).

## Target Optimizations

To run Whisper Base smoothly on the Arduino UNO Q's 4x ARM Cortex-A53 processor with minimal latency and low RAM footprint, the following optimizations are applied:

- **ARM NEON SIMD & Native Bindings (pywhispercpp):** Direct 128-bit vector processing on ARMv8 CPU cores integrated smoothly through Python bindings.
- **Quantization (q5_1 / int8):** Reduces model memory footprint while cutting memory bandwidth pressure. The benchmark keeps q5_1 as the accuracy-first whisper.cpp target.
- **4 CPU Threads (`--cpu-threads 4`):** Spreads the tensor computation parallelly across all 4 physical CPU cores.
- **Greedy Search (`--whisper-beam-size 1`):** Fast single-pass decoding without exploring candidate branches.
- **Environment Management with uv:** Python dependencies are locked by UV. Large model files are downloaded into `models/`; they are intentionally not embedded in `uv.lock` or Git.

## Domain-Vocabulary Bias

Domain vocabulary bias is always enabled by default. It injects Cultura Viva domain keywords (Antoni Gaudí, Sagrada Família, basilica, facade, modernisme, Catalan, Casa Batlló, Casa Milà, Park Güell, trencadís, salamander, dragon, Barcelona, Passeig de Gràcia) as contextual prompts and hotwords, and applies phonetic entity canonicalization to ensure top accuracy on cultural terms.

Every exported prediction record indicates `domain_bias_applied: true` for compatible engines.

## Dataset & Domain Keywords

`data_audio/manifest.json` contains synthetic benchmark ground truth; real human speech recordings should be placed under `data_audio/recorded/`.

Audio files must be 16 kHz, mono, 16-bit PCM WAV (the benchmark automatically normalizes other formats if needed).

## Setup and Execution

From the repository root, install the locked environment and run the benchmark:

```bash
uv sync
uv run main.py
```

`main.py` downloads missing model weights for the selected engines into
`models/`. UV manages packages; model weights are runtime data and cannot
be declared in TOML.

### Running Other Available Models

To compare engines, pass the `--engines` argument:

```bash
# Run every configured engine sequentially:
uv run main.py --engines all --output-dir results_arduino

# Run both supported whisper.cpp Base variants in one benchmark:
uv run main.py --engines whisper.cpp:base.en-q5_1 whisper.cpp:base.en-q5_0 --output-dir results_arduino

# Compare against faster-whisper Base INT8:
uv run main.py --engines faster-whisper:base.en --output-dir results_arduino

# Run Vosk or Sherpa-ONNX:
uv run main.py --engines vosk sherpa-onnx --output-dir results_arduino
```

## Local Execution (Host Computer)

For baseline testing or computer-side comparisons:

```bash
uv sync
uv run python main.py --output-dir results_computer
```

Results will be written to `results_computer/`.

## Results & Visualizations (visualize.py)

After the benchmark finishes, run `visualize.py` to generate visual performance reports and an interactive HTML dashboard across all benchmarked models:

```bash
uv run visualize.py --input-dir results_arduino
```

This generates in `results_arduino/plots/`:

- **Performance Summary Dashboard** (`plots/dashboard_summary.png`): Combined WER/CER, Latency, RTF, and Peak RAM footprint.
- **Real-Time Factor (RTF) Analysis** (`plots/rtf_realtime_factor.png`): Evaluates execution speed relative to real-time audio playback (RTF < 1.0).
- **Interactive Evaluation Report** (`plots/evaluation_report.html`): Self-contained HTML report.

### Comparing Host Computer vs. Arduino UNO Q:

If you have run the benchmark on both a PC and the Arduino board:

```bash
uv run visualize.py --input-dir results_arduino --compare-with results_computer
```