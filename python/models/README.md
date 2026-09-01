# Local STT Models

Place downloaded model weights and extracted model directories here when running the benchmark locally. Model weight files are ignored by Git due to their size.

```text
models/
├── ggml-base.en-q5_0.bin       # Whisper Base 5-bit quantized model for whisper.cpp (~60 MB)
├── ggml-base.en-q4_0.bin       # Whisper Base 4-bit quantized model for whisper.cpp (~45 MB) [optional]
├── whisper.cpp/                # Repository and compiled whisper-cli binary
│   └── build/bin/whisper-cli
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
| **whisper.cpp** *(Target)* | `base.en-q5_0` | [ggerganov/whisper.cpp (Hugging Face)](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en-q5_0.bin) | GGML 5-bit (~60 MB) |
| **whisper.cpp** | `base.en-q4_0` | [ggerganov/whisper.cpp (Hugging Face)](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en-q4_0.bin) | GGML 4-bit (~45 MB) |
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

## Quick Setup & Download Commands

### For whisper.cpp on Arduino UNO Q:
The automated script compiles `whisper-cli` with ARM NEON and downloads the model:
```bash
# Downloads and prepares base.en-q5_0:
bash setup_whisper_cpp.sh base.en-q5_0

# Or to download the 4-bit version:
bash setup_whisper_cpp.sh base.en-q4_0
```

### Manual Download of GGML Models:
```bash
# Direct download of Whisper Base Q5_0:
curl -L -o models/ggml-base.en-q5_0.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en-q5_0.bin

# Direct download of Whisper Base Q4_0:
curl -L -o models/ggml-base.en-q4_0.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en-q4_0.bin
```

### Host PC / Local Setup Commands (with venv active)

#### faster-whisper models:
```powershell
python -m pip install "huggingface_hub[cli]" sentencepiece
hf download Systran/faster-whisper-tiny.en
hf download Systran/faster-whisper-base.en
```

#### sherpa-onnx model:
```powershell
cd models
Invoke-WebRequest -Uri https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-zipformer-small-en-2023-06-26.tar.bz2 -OutFile sherpa-onnx-en.tar.bz2
tar xvf sherpa-onnx-en.tar.bz2
Rename-Item sherpa-onnx-zipformer-small-en-2023-06-26 sherpa-onnx-en
cd sherpa-onnx-en
Rename-Item encoder-epoch-*.onnx encoder.onnx
Rename-Item decoder-epoch-*.onnx decoder.onnx
Rename-Item joiner-epoch-*.onnx joiner.onnx
```

#### Vosk model:
Vosk is distributed as a ZIP archive. Download `vosk-model-small-en-us-0.15.zip` from the Alpha Cephei page above, extract it, and place the complete extracted directory at `models/vosk-model-small-en-us-0.15/`. It must contain `am/`, `conf/`, `graph/`, and `ivector/` subdirectories.

---

## Arduino Deployment

Model binaries are not included in the packaged app archive because of their size. Place the model files under `models/` on the board (matching the paths in `app.yaml`). App Lab sets `VOSK_MODEL_DIR` and `SHERPA_ONNX_MODEL_DIR` automatically. For `whisper.cpp`, `main.py` detects the compiled `whisper-cli` binary and `ggml-base.en-q5_0.bin` directly in `models/`.