# faster-whisper base model

This directory is the designated location for the Speech-to-Text model weights.

## Download Instructions

Download the original `Systran/faster-whisper-base.en` files directly from Hugging Face:
[https://huggingface.co/Systran/faster-whisper-base.en/tree/main](https://huggingface.co/Systran/faster-whisper-base.en/tree/main)

Ensure the following files are downloaded and placed into this directory:
- `model.bin`
- `config.json`
- `vocabulary.txt`

The resulting path should look like this:
```
pipeline/models/model.bin
```

These files will be loaded automatically by `microphone_module.py` via `config.STT_MODEL_PATH`.

