# Cultura Viva STT Benchmark (Arduino UNO Q Edition)

A highly-optimized, zero-bloat repository for running and evaluating Speech-to-Text (STT) inference on the Arduino UNO Q (Qualcomm Dragonwing QRB2210).

This repository evaluates two primary engines using the Whisper Base model:
1. `whisper.cpp` (native C++ execution via GGML, ARM NEON SIMD)
2. `faster-whisper` (CTranslate2, INT8 quantization)
3. `vosk` (Optional)
4. `sherpa-onnx` (Optional)

## 1. System Prerequisites & Environment Setup

This project uses `uv` for lightning-fast Python dependency management.

### Install `uv`
If you don't have `uv` installed, install it via:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Setup Virtual Environment
Run the following from the root of this repository:
```bash
uv venv
uv pip install -r pyproject.toml
```

---

## 2. Compiling `whisper.cpp` for Arduino UNO Q (Cortex-A53)

The Arduino UNO Q features a Quad-core ARM Cortex-A53 processor. To achieve the absolute minimum inference latency with `whisper.cpp`, you must compile the backend natively with hardware-specific flags.

When `pywhispercpp` builds its bundled `whisper.cpp`, you can pass environment variables to force the compiler to target the Cortex-A53 and enable ARM NEON SIMD instructions.

```bash
# Force CMAKE to use Cortex-A53 optimizations (NEON is always enabled on aarch64)
export CFLAGS="-O3 -mcpu=cortex-a53"
export CXXFLAGS="-O3 -mcpu=cortex-a53"

# Force pywhispercpp to rebuild the C++ backend
uv pip install --force-reinstall pywhispercpp>=1.2.0
```

> **Note**: For 64-bit OS (aarch64), NEON is enabled by default, but `-mcpu=cortex-a53` ensures instruction scheduling is optimal for this specific core.

---

## 3. Running the Benchmark

You must provide a dataset directory containing `.wav` audio files (16kHz, mono) and a `manifest.json`.

```bash
uv run main.py \
    --audio-dir /path/to/dataset \
    --manifest /path/to/dataset/manifest.json \
    --engines whisper.cpp:base.en-q5_1 faster-whisper:base.en \
    --cpu-threads 4 \
    --compute-type int8
```

### Technical Deep Dive: Optimizations Applied

1. **Threading Strategy (`--cpu-threads 4`)**: The QRB2210 SoC has exactly 4 Cortex-A53 cores. Setting threads to 4 avoids context-switching overhead while fully saturating the CPU.
2. **Quantization (`--compute-type int8`)**: For `faster-whisper`, CTranslate2 is configured to use `int8` (or `int8_float16`) to fit the model comfortably in the LPDDR4 RAM and maximize memory bandwidth.
3. **NEON SIMD**: Native C++ compilation ensures vector math operations (like dot products) process multiple data points in a single clock cycle.
4. **Low-Latency Decoding**: We enforce `temperature=0.0` (greedy search) and `beam_size=1` (by default) to minimize RTF (Real-Time Factor).

---

## 4. Keyword Preservation via `initial_prompt`

Preserving domain-specific vocabulary (e.g., "Gaudí", "Sagrada Família", "trencadís") is critical. The decoder can be heavily biased toward these keywords by injecting them as prior context.

By default, `benchmark.py` injects a rich domain prompt:
> *"Cultura Viva audio guide in Barcelona about Antoni Gaudí, Sagrada Família basilica, Nativity, Passion, and Glory facades, Catalan modernisme architecture, Casa Batlló, Casa Milà, Park Güell, dragon and salamander sculptures, and trencadís mosaics."*

You can override this and inject a custom keyword list using the `--whisper-initial-prompt` flag:
```bash
uv run main.py \
    --audio-dir /path/to/dataset \
    --manifest /path/to/dataset/manifest.json \
    --whisper-initial-prompt "Antoni Gaudí, Barcelona, Passeig de Gràcia, trencadís"
```
*For `faster-whisper`, these keywords are also passed as explicit `hotwords`.*

---

## 5. Benchmarking Metrics and Telemetry

The benchmark automatically measures:
- **RTF (Real-Time Factor)**: Inference latency divided by audio duration.
- **WER / CER (Word/Character Error Rate)**.
- **Keyword Spotting Accuracy**: Percentage of target keywords successfully transcribed.
- **Peak RAM Usage**: Sampled memory footprint (MB).

Results are exported to the `results_computer/` folder (or your specified `--output-dir`). A `summary.json` is generated, and a suite of `matplotlib` comparison charts will be saved in `results_computer/plots/`.