# Cultura Viva

Interactive multimodal AI audio guide for Antoni Gaudí's monuments in Barcelona
(Sagrada Família, Park Güell, Casa Milà, Casa Batlló), running fully on-device on
an **Arduino UNO Q**. A visitor photographs an architectural element, asks a
question aloud, and hears a spoken answer in the guide personality they picked.

This monorepo gathers the shipped device app together with the research that
picked each model in its pipeline.

## Layout

| Folder | What it is |
| --- | --- |
| [`arduino/`](arduino) | The device application. C++ sketch for the STM32 MCU (LCD, buttons, GPS minimap, buzzer) plus the Python pipeline for the QRB2210 Linux side (vision → STT → knowledge retrieval → SLM → TTS), talking over Arduino Bridge RPC. |
| [`vision/`](vision) | Training, threshold calibration, and ONNX export for the per-monument element classifiers that the device uses to recognise what the camera is pointed at. |
| [`benchmark/slm/`](benchmark/slm) | Evaluation of small language models (Qwen2.5, Llama 3.2, Gemma 3, SmolLM2) on a Gaudí Q&A test set, under the board's memory and latency budget. |
| [`benchmark/stt/`](benchmark/stt) | Speech-to-text comparison — whisper.cpp, faster-whisper, Vosk, sherpa-onnx — measuring WER, latency, and real-time factor on the board. |
| [`benchmark/tts/`](benchmark/tts) | Text-to-speech comparison across 18 ONNX voices (Piper and VITS), measuring inference time and model footprint. |
| [`prototype/`](prototype) | The early end-to-end pipeline sketch that preceded the device app. Kept for reference. |

Each folder is self-contained, with its own `README.md`, `pyproject.toml`, and
lockfile — run `uv sync` inside the one you're working on.

## History

`arduino/`, `vision/`, and the three `benchmark/` folders were merged in with
`git subtree`, so every commit from the original repositories is preserved here.
To pull later changes from an upstream repo:

```sh
git subtree pull --prefix=vision https://github.com/Hackestiu/gaudi-vision.git main
```

The originals: [cultura-viva-uno-q](https://github.com/Hackestiu/cultura-viva-uno-q),
[gaudi-vision](https://github.com/Hackestiu/gaudi-vision),
[slm-benchmark](https://github.com/Hackestiu/slm-benchmark),
[stt-benchmark](https://github.com/Hackestiu/stt-benchmark),
[tts-benchmark](https://github.com/Hackestiu/tts-benchmark).
