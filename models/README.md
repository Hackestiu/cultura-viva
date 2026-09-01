# Local STT Models

Place downloaded model weights and extracted model directories here when running the benchmark locally. Model weight files are ignored by Git due to their size.

```text
models/
├── ggml-base.en-q5_1.bin       # Primary Whisper Base English Q5_1 model (~60 MB)
├── ggml-base.en-q5_0.bin       # Legacy Q5_0 comparison model [optional]
├── vosk-model-small-en-us-0.15/ # Extracted Vosk model directory
└── sherpa-onnx-en/             # Extracted Transducer model directory for sherpa-onnx
    ├── encoder.onnx
    ├── decoder.onnx
    ├── joiner.onnx
    ├── tokens.txt
    └── bpe.model
```

`bpe.model` is required for domain bias to apply to sherpa-onnx — it is what the benchmark uses to build the hotwords file at runtime. Without it, sherpa-onnx still runs, just without the domain-vocabulary hint.

---

## Model Sources & Origins

| Engine | Model | Source / Repository | Format / Size |
| --- | --- | --- | --- |
| **whisper.cpp** *(Target)* | `base.en-q5_1` | [ggerganov/whisper.cpp (Hugging Face)](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en-q5_1.bin) | GGML 5-bit (~60 MB) |
| **faster-whisper** | `base.en` | [Systran/faster-whisper-base.en (Hugging Face)](https://huggingface.co/Systran/faster-whisper-base.en) | CTranslate2 INT8 (~145 MB) |
| **faster-whisper** | `tiny.en` | [Systran/faster-whisper-tiny.en (Hugging Face)](https://huggingface.co/Systran/faster-whisper-tiny.en) | CTranslate2 INT8 (~75 MB) |
| **sherpa-onnx** | `zipformer-small-en` | [k2-fsa/sherpa-onnx (GitHub Releases)](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-transducer/index.html) | ONNX Transducer (~110 MB) |
| **Vosk** | `small-en-us-0.15` | [Alpha Cephei Vosk Models](https://alphacephei.com/vosk/models) | Kaldi (~50 MB) |

---

## Where does Whisper come from?

1. **Original Whisper Architecture:** Developed by OpenAI as a state-of-the-art encoder-decoder acoustic and language model trained on 680,000 hours of multilingual supervision.
2. **`whisper.cpp` (GGML):** High-performance C/C++ port created by Georgi Gerganov. It converts the original OpenAI weights into GGML binary format and introduces 4-bit and 5-bit quantization (`q4_0`, `q5_0`) optimized for ARM NEON vector instructions on edge devices.
3. **`faster-whisper` (CTranslate2):** Implementation by Systran based on CTranslate2, a custom inference engine for Transformer models supporting INT8 quantization.

---

## Provisioning Model Files

UV manages the Python environment; model weights are large runtime artifacts and are
downloaded into `models/` by the benchmark. From the repository root, run:

```bash
uv sync
uv run main.py --engines all
```

Use `--engines whisper.cpp:base.en-q5_1` (or a space-separated list) to provision and
test only the models you intend to use. Missing models are downloaded on first use.
