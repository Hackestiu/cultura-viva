# models/stt — faster-whisper model files

This directory is the designated location for the Speech-to-Text model weights used
by `hw/microphone_module.py` (`MicrophoneManager.transcribe()`).

**Engine**: [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper) — a
CTranslate2-based reimplementation of Whisper, optimized for CPU inference
(int8 quantization, ~4× faster than vanilla Whisper on ARM).

---

## Expected layout

```
models/stt/
└── faster-whisper-base.en/
    ├── model.bin
    ├── config.json
    └── vocabulary.txt
```

The directory name `faster-whisper-base.en` is what `config.py` points to via
`STT_MODEL_PATH`. If you rename it, update `STT_MODEL_PATH` in `config.py`.

---

## Download instructions

### Option A — `huggingface_hub` CLI (recommended, works on the board)

```bash
pip install huggingface-hub   # skip if already installed

huggingface-cli download Systran/faster-whisper-base.en \
    --local-dir python/models/stt/faster-whisper-base.en
```


### Option B — Direct Hugging Face browser download

Go to: <https://huggingface.co/Systran/faster-whisper-base.en/tree/main>

Download and place these three files into `python/models/stt/faster-whisper-base.en/`:
- `model.bin`
- `config.json`
- `vocabulary.txt`

`faster-whisper` uses the CTranslate2 model format. The tokenizer vocabulary is
stored in `vocabulary.txt`, so a separate Hugging Face `tokenizer.json` file is
not required by `WhisperModel`.


---

## Optimizations applied in `hw/microphone_module.py`

| Parameter | Value | Reason |
|---|---|---|
| `compute_type` | `"int8"` | ~4× faster on Cortex-A53, fits in 2 GB RAM |
| `cpu_threads` | `4` | UNO Q has 4 physical cores |
| `beam_size` | `1` | Greedy decoding — faster, deterministic |
| `temperature` | `0.0` | No sampling randomness |
| `vad_filter` | `True` | Removes silence chunks, reduces hallucinations |
| `min_silence_duration_ms` | `500` | VAD sensitivity threshold |
| `language` | `"en"` | English only |
| `initial_prompt` | Gaudí domain text | Biases ASR towards Gaudí/Barcelona vocabulary |
| `hotwords` | Domain keyword list | Boosts recognition of proper nouns |

Post-transcription `canonicalize_domain_entities()` further corrects common ASR
misspellings (e.g. "gaudy" → "Gaudí", "trencadis" → "trencadís").

---

## .gitignore reminder

Large binary model files should not be committed. Add to `.gitignore`:

```
# models/stt/.gitignore
faster-whisper-base.en/model.bin
```
