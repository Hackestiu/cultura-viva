# Cultura Viva STT Benchmark

Offline English speech-to-text benchmark for Cultura Viva. Compares candidate STT
engines on recognition quality and resource usage, for local development and for
deployment on an Arduino UNO Q via Arduino App Lab.

## Repository layout

- `app/` — the runnable benchmark. See [app/README.md](app/README.md) for setup,
  local execution, and Arduino deployment.
- `colab/` — historical, see "Historical Colab Execution" below.

## Tested Models

- faster-whisper `tiny.en` and `base.en`
- Vosk small English
- sherpa-onnx `zipformer-small-en`

See [app/models/README.md](app/models/README.md) for install sources and paths.

## Domain-vocabulary bias

Off by default; enabled with `--enable-domain-bias`. When enabled:

```text
faster-whisper (tiny.en, base.en)  — yes
sherpa-onnx (zipformer-small-en)   — yes
vosk                                — no
```

Every prediction row records `domain_bias_applied` for the engine that produced it.

## Dataset & Domain Keywords

`app/data_audio/manifest.json` is the synthetic benchmark ground truth; a separate
recorded human-speech set is distributed outside the repo. See
[app/data_audio/README.md](app/data_audio/README.md) for the manifest schema and
generation, and [app/data_audio/recorded/README.md](app/data_audio/recorded/README.md)
for the recorded set.

## Evaluation Metrics

Per utterance and aggregate reports include:

- **WER**, **CER** — word/character error rate against the manifest's ground truth.
- **Domain keyword spotting accuracy** — recovery rate of the canonical heritage
  entities (Gaudí, Sagrada Família, trencadís, etc.) listed in a clip's `keywords`.
- **RTF** (real-time factor) and **inference latency** (ms) — measured after model
  loading; load time is excluded.
- **Peak RAM** (MB) — host-side process measurement; treat as a comparison signal,
  not an Arduino deployment measurement.
- **Model size on disk** (MB), where the model path is local.
- **`domain_bias_applied`** — whether the domain-vocabulary hint was actually applied
  for that engine on that run (see "Domain-vocabulary bias" above).

Each engine writes a schema-versioned JSON file under `predictions/`; aggregate
metrics go in `summary.json`. Comparison plots are
derived from the JSON reports and are optional.

## How to Run

See [app/README.md](app/README.md) for the full setup and run instructions
(local computer and Arduino UNO Q). For run-to-run comparison and auditing of
predictions, see the optional [Weights & Biases section](app/README.md#experiment-tracking-optional)
there.

## Results / Findings

Local CPU runs write to `app/results_computer/`; Arduino App Lab runs write to
`app/results_arduino/`. Re-run on the target UNO Q before making deployment
decisions — host timings and RAM are not edge measurements.

## Historical Colab Execution

`colab/` documents the offline model-selection phase that preceded edge-device
integration. It is not production runtime code and should not be mixed with
current computer or Arduino reports.