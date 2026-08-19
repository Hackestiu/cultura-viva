# Local STT models

Place downloaded model weights and extracted model directories here when running the standalone `app/` bundle locally. Model files are ignored by Git.

Expected paths from `app.yaml`:

```text
models/
├── vosk-model-small-en-us-0.15/
└── sherpa-onnx-en/
	├── tiny.en-encoder.onnx
	├── tiny.en-decoder.onnx
	└── tiny.en-tokens.txt
```

The faster-whisper `tiny.en` and `base.en` models normally use the Hugging Face cache managed by the library. The sherpa-onnx path is explicit and local. The adapter supports sherpa Whisper files with `*-encoder.onnx`, `*-decoder.onnx`, and `*-tokens.txt`, as well as transducer files with `encoder.onnx`, `decoder.onnx`, `joiner.onnx`, and `tokens.txt`. Vosk's official small English ZIP is available at `https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip`.
