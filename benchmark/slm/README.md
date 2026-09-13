# CulturaViva: SLM Benchmark & Embedded Deployment Suite

An end-to-end evaluation, benchmarking, and embedded deployment pipeline for **CulturaViva** — an intelligent interactive audio guide system for Antoni Gaudí monuments (Sagrada Família, Park Güell, Casa Milà, Casa Batlló).

---

## System Architecture & Constraints

- **Target Device**: Arduino UNO Q (Qualcomm QRB2210 quad-core ARM Cortex-A53 @ 2.0 GHz, 4GB LPDDR4, 32GB eMMC, Debian Linux).
- **Embedded Footprint**: < 1.5GB RAM allocated for model weights and 2k context window; target response latency < 3s.
- **Inference Runtime**: On-device `llama.cpp` (compiled with ARM NEON SIMD) / `llama-cpp-python`.
- **Knowledge Grounding**: Upstream Computer Vision / RFID element ID direct lookup + fallback keyword search over `knowledge_base.json` and `element_sheets.json`.
- **Evaluation Engine**: [Ragas](https://docs.ragas.io/) scoring (*Faithfulness*, *AnswerRelevancy*, *ContextPrecision*, *ContextRecall*) with a local Ollama judge (`qwen2.5:7b`).

---

## Candidate Models Under Test

| Model | Ollama Tag | Quantization | RAM Footprint | Target Architecture |
| :--- | :--- | :--- | :--- | :--- |
| **Qwen 2.5 1.5B Instruct** | `qwen2.5:1.5b` | `Q4_K_M` (~1.1 GB) | ~1.45 GB | ARM Cortex-A53 / PC |
| **Llama 3.2 1B Instruct** | `llama3.2:1b` | `Q4_K_M` (~0.8 GB) | ~1.10 GB | ARM Cortex-A53 / PC |
| **Gemma 3 1B IT** | `gemma3:1b` | `Q4_K_M` (~0.85 GB) | ~1.15 GB | ARM Cortex-A53 / PC |
| **SmolLM2 1.7B Instruct** | `smollm2:1.7b` | `Q4_K_M` (~1.15 GB) | ~1.50 GB | ARM Cortex-A53 / PC |
| **Qwen 2.5 0.5B Instruct** | `qwen2.5:0.5b` | `Q4_K_M` (~0.39 GB) | ~0.65 GB | ARM Cortex-A53 / PC |

---

## Repository Layout

```text
├── main.py                   # Unified CLI entrypoint (prepare / benchmark / eval)
├── config.yaml               # Single source of truth (models, paths, inference, Arduino)
├── pyproject.toml            # Project dependencies (managed via uv)
├── README.md
│
├── core/
│   ├── config.py             # config.yaml loader (env > yaml > default)
│   └── device_prompt.py      # Imports the device's real prompt builders
│
├── data/                     # Gaudí knowledge files (copies of the device's)
│   ├── knowledge_base.json   # High-level biographies, works, and timelines
│   └── element_sheets.json   # Granular architectural facts, materials, and element IDs
│
├── scripts/                  # Runnable Python scripts
│   ├── prepare.py            # Model downloader & Arduino deployment packager
│   └── benchmark.py          # SLM prediction runner & Ragas evaluation trigger
│
└── eval/                     # Ragas evaluation suite
    ├── testset.json          # Curated Gaudí question/reference-answer benchmark set
    ├── evaluate.py           # Self-contained Ragas scoring runner
    ├── predictions.example.json
    └── legacy_pre_device_parity/   # Superseded runs, kept for comparison only
```

---

## The prompt comes from the device

The benchmark does **not** define its own prompt. `core/device_prompt.py` imports
`build_messages` and `PERSONALITY_PROMPTS` straight out of
`arduino/python/core/model_module.py`, the module the board actually runs, so a
change to the guide's wording lands in the next benchmark run automatically.

That matters because the two had already drifted: this suite used to score a
single flat completion prompt under a generic persona, long after the device had
moved to a chat prompt that puts retrieved facts **first** and the personality
instructions second — an ordering llama.cpp's prefix KV cache depends on.

Generation parameters in `config.yaml` (`max_tokens: 60`, `repeat_penalty: 1.1`,
`stop: ["\n\n", "<|im_end|>"]`, `temperature: 0.1`) mirror the device's
`create_chat_completion` call. Keep them in step by hand.

### The one deliberate difference: retrieval

On the board, vision names the element and the knowledge sheet is fetched by id.
The testset has no element ids, and includes architect-level and cross-monument
questions that no single element sheet can answer, so passages are retrieved
semantically here (`retrieval.top_k`, default 3). Everything downstream of
retrieval — prompt, personality, sampling — matches the device.

---

## Quickstart (PC Setup & Benchmarking)

### 1. Install Dependencies
Ensure you have Python 3.12+ and [`uv`](https://docs.astral.sh/uv/) installed:
```bash
uv sync
```

### 2. Start Local Ollama
In a separate terminal, launch the Ollama service:
```bash
ollama serve
```

### 3. Prepare Models (PC & Arduino)
Fetch all candidate models into Ollama and download their quantized GGUF equivalents from Hugging Face:
```bash
# Pull all Ollama models, download GGUFs, and assemble Arduino export
uv run python main.py prepare --all

# Or download only without exporting:
uv run python main.py prepare --download-only
```

### 4. Run the Benchmark
Generate predictions across `eval/testset.json` and score them with Ragas. Every
candidate is run once **per guide personality** (artistic, technical, child), so
the default sweep is 5 models x 3 personalities x 38 questions:
```bash
# Every candidate model, every personality
uv run python main.py benchmark

# One model, every personality
uv run python main.py benchmark --model qwen2.5:1.5b

# One model, one personality
uv run python main.py benchmark --model qwen2.5:1.5b --personality technical

# Generate predictions without running the Ragas judge
uv run python main.py benchmark --model gemma3:1b --skip-eval
```

Predictions land in `eval/predictions_<model>_<personality>.json`; scores and
per-question breakdowns in `eval/results/`.

The artistic and child voices are expected to score lower on
`answer_correctness` than the technical one: the testset references are written
as plain factual statements, and those two personalities are instructed to
speak in metaphor and simple analogy. Compare a personality against itself
across models, not against a different personality.

---

## Deploying to Arduino UNO Q (Debian ARM64)

### 1. Assemble the Deployment Bundle
Export the chosen model (e.g. `qwen2.5:1.5b` or `gemma3:1b`) and runtime files:
```bash
uv run python main.py prepare --export-arduino --model qwen2.5:1.5b
```

### 2. Transfer to the Arduino
Copy the `arduino_export/` directory over SSH:
```bash
scp -r arduino_export/ debian@<ARDUINO_IP>:~/culturaviva/
```

### 3. Build & Run on Device
SSH into the Arduino UNO Q and run the setup script:
```bash
ssh debian@<ARDUINO_IP>
cd ~/culturaviva

# Run setup (installs dependencies & compiles llama-cpp-python with ARM NEON flags)
chmod +x setup_arduino.sh
./setup_arduino.sh

# Run the interactive audio guide
./venv/bin/python run_guide.py
```

### 4. Run the Full Benchmark on Arduino Hardware
To evaluate real-world inference speed, tokens/sec, and accuracy directly on the Cortex-A53 CPU:
```bash
# Run benchmark for Qwen 2.5 1.5B (or any other GGUF in models/)
./venv/bin/python benchmark_arduino.py --model models/qwen2.5-1.5b-instruct-q4_k_m.gguf
```
This runs the 38 test questions and saves `predictions_arduino_<model>.json`.

### 5. Evaluate Arduino Predictions on PC with Ragas
Copy the on-device predictions back to your PC and score them:
```bash
# On your PC terminal:
scp debian@<ARDUINO_IP>:~/culturaviva/predictions_arduino_*.json eval/

# Score with local Ragas judge:
uv run python main.py eval --predictions eval/predictions_arduino_qwen2.5-1.5b-instruct-q4_k_m.json
```

---

## Customization (`config.yaml`)

All parameters (temperatures, token limits, model repositories, GGUF URLs, file paths, and compiler flags) can be modified in [`config.yaml`](config.yaml). No code edits required.
