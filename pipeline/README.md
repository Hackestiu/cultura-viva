# Pipeline STT adapters

This folder contains the two benchmark winners prepared for the Cultura Viva
pipeline. It is intentionally separate from the benchmark runner so the App Lab
application can import a small `transcribe(audio_path)` adapter.

## What To Copy Into The App Lab Project

Copy these directories/files into the App Lab project's Python side:

```text
models/
pipeline/
```

The shared `models/` directory belongs at the application root and is also where
the future SLM and TTS files should live. Do not put model weights in Git.

Install the Python dependencies from this benchmark's `pyproject.toml` (or add
the equivalent packages to the App Lab dependency configuration):

```text
pywhispercpp
faster-whisper
huggingface-hub
soundfile
```

The production application needs only one STT model at runtime. Before the final
choice, both adapters can be kept in the source tree, but do not load both models
at the same time on the UNO Q.

Expected shared model layout:

```text
stt-benchmark/
├── models/
│   ├── ggml-base.en-q5_1.bin
│   └── faster-whisper-base.en/
└── pipeline/
    ├── common.py
    ├── faster_whisper_base/
    └── whisper_cpp_base_q5_1/
```

Both model directories belong to the shared top-level `models/` directory used
by the whole application. Keep the actual weights out of Git. The benchmark's
model provisioning command can populate them before deployment; the adapters
intentionally fail clearly when their configured model file is missing.

Provision the candidate weights on a connected computer, then copy the resulting
`models/` directory to the board. The benchmark command is:

```bash
uv run main.py --engines faster-whisper:base.en whisper.cpp:base.en-q5_1
```

For a memory-constrained UNO Q, provision and copy only the model eventually
selected. The faster-whisper model is a directory; whisper.cpp is the single
file `ggml-base.en-q5_1.bin`.

Example usage from the repository root:

```python
from pipeline import FasterWhisperBaseSTT, WhisperCppBaseQ5_1STT

stt = WhisperCppBaseQ5_1STT()
question = stt.transcribe(wav_path)
```

For the production application, select one backend in configuration and create
it once, not once per recording:

```python
from pathlib import Path

from pipeline import FasterWhisperBaseSTT

stt = FasterWhisperBaseSTT(
    model_path=Path("models/faster-whisper-base.en"),
    cpu_threads=4,
)

def transcribe(audio_path: str) -> str:
    return stt.transcribe(audio_path)
```

The alternative is:

```python
from pipeline import WhisperCppBaseQ5_1STT

stt = WhisperCppBaseQ5_1STT(
    model_path="models/ggml-base.en-q5_1.bin",
    cpu_threads=2,
)
```

This function is the piece to add to `MicrophoneManager`; it does not replace
`record_while_held()` or `save()`. The orchestration should call it only after
`save()` returns the WAV path.

## Changes After The Benchmark Choice

Keep both adapters while comparing them. Once the winner is chosen:

1. Set one `STT_MODEL_PATH` and one `STT_BACKEND` in the application config.
2. Create only that adapter once in `MicrophoneManager.__init__`.
3. Implement `transcribe(audio_path)` by delegating to that persistent instance.
4. Remove the unused backend dependency and model from the board image.
5. Leave `record_while_held()` and `save()` unchanged.

For `whisper.cpp:base.en-q5_1`:

```python
from pipeline import WhisperCppBaseQ5_1STT

self._stt = WhisperCppBaseQ5_1STT(
        model_path=STT_MODEL_PATH,
        cpu_threads=2,
)
```

For `faster-whisper:base.en`:

```python
from pipeline import FasterWhisperBaseSTT

self._stt = FasterWhisperBaseSTT(
        model_path=STT_MODEL_PATH,
        device="cpu",
        compute_type="int8",
        cpu_threads=2,
)
```

The call from the existing orchestration remains:

```python
wav_path = microphone.save(button_id, model_name, audio)
question_text = microphone.transcribe(wav_path)
```

Do not call `Model(...)` or `WhisperModel(...)` inside `transcribe`; model loading
must happen once and inference must happen after the WAV has been saved.

## UNO Q Stability Checklist

- Use `cpu_threads=2` initially. Increase to 3 or 4 only after measuring RAM and
    confirming the process does not reset the board.
- Run one model per process and never benchmark `--engines all` inside the live
    App Lab application.
- Keep the recorded WAV short and normalize it to 16 kHz mono PCM16 before STT.
- Avoid running SLM, TTS, vision, and STT model loads concurrently; release any
    temporary image/audio buffers before calling STT.
- Keep `device="cpu"` and `compute_type="int8"` for faster-whisper on the UNO Q.
- Watch `free -h` and `dmesg -T | tail -100` while reproducing a reset. An OOM
    kill appears in `dmesg`; a watchdog or thermal reset usually leaves a different
    kernel/service message.
- If the process is killed while a single long utterance is decoding, split or
    limit recordings before inference rather than changing WER post-processing.

The production project should copy one adapter into its `microphone_module.py`
or hold one instance on `MicrophoneManager`; do not construct the model for
every utterance. Both adapters apply the same Cultura Viva prompt and final
domain-entity canonicalization. Faster-whisper additionally receives hotwords.