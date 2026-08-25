# Local STT models

Place downloaded model weights and extracted model directories here when running
the standalone `app/` bundle locally. Model files are ignored by Git.

```text
models/
├── vosk-model-small-en-us-0.15/
└── sherpa-onnx-en/
    ├── encoder.onnx
    ├── decoder.onnx
    ├── joiner.onnx
    ├── tokens.txt
    └── bpe.model
```

`bpe.model` is required for `--enable-domain-bias` to apply to sherpa-onnx — it's
what the benchmark uses to build the hotwords file at runtime. Without it, that
engine still runs, just without the domain-vocabulary hint.

The sherpa-onnx adapter also accepts an older Whisper-style export
(`*-encoder.onnx`, `*-decoder.onnx`, `*-tokens.txt`) for backward compatibility, but
Whisper-based sherpa-onnx models never support hotwords regardless of `bpe.model` —
use the transducer layout above to get domain-bias parity with faster-whisper.

## Model sources

| Engine | Source | Local destination |
| --- | --- | --- |
| faster-whisper `tiny.en` | [Systran/faster-whisper-tiny.en on Hugging Face](https://huggingface.co/Systran/faster-whisper-tiny.en) | Hugging Face cache; downloaded automatically by faster-whisper |
| faster-whisper `base.en` | [Systran/faster-whisper-base.en on Hugging Face](https://huggingface.co/Systran/faster-whisper-base.en) | Hugging Face cache; downloaded automatically by faster-whisper |
| sherpa-onnx `zipformer-small-en` | [k2-fsa/sherpa-onnx releases](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-transducer/index.html) (`asr-models` release assets) | `models/sherpa-onnx-en/` |
| Vosk small English | [Official Alpha Cephei model page](https://alphacephei.com/vosk/models) | `models/vosk-model-small-en-us-0.15/` |

Verify the exact sherpa-onnx release filename against the link above before
downloading — release asset names occasionally change.

## Install commands (with venv active)

```powershell
python -m pip install "huggingface_hub[cli]" sentencepiece
hf download Systran/faster-whisper-tiny.en
hf download Systran/faster-whisper-base.en
```

```powershell
cd models
Invoke-WebRequest -Uri https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-zipformer-small-en-2023-06-26.tar.bz2 -OutFile sherpa-onnx-en.tar.bz2
tar xvf sherpa-onnx-en.tar.bz2
Rename-Item sherpa-onnx-zipformer-small-en-2023-06-26 sherpa-onnx-en
cd models/sherpa-onnx-en
Rename-Item encoder-epoch-*.onnx encoder.onnx
Rename-Item decoder-epoch-*.onnx decoder.onnx
Rename-Item joiner-epoch-*.onnx joiner.onnx
```

Vosk is distributed as a ZIP rather than a Hugging Face repository. Download
`vosk-model-small-en-us-0.15.zip` from the Alpha Cephei page above, extract it, and
place the complete extracted directory at `models/vosk-model-small-en-us-0.15/`.
It must contain `am/`, `conf/`, `graph/`, and `ivector/` subdirectories.

`sentencepiece` is required only for building the sherpa-onnx domain-bias hotwords
file (`--enable-domain-bias`); every other feature works without it.

## Arduino deployment

Model binaries are not included in the packaged app archive (see
[../README.md](../README.md)) because of their size. Copy the same directories
above to the device under `/app/models/`, matching the paths in `app.yaml`; App Lab
points `VOSK_MODEL_DIR` and `SHERPA_ONNX_MODEL_DIR` at those locations
automatically. faster-whisper models may download on first use, depending on the
device's network access — download them on a computer and copy the Hugging Face
cache over if the Arduino has no internet access at runtime.