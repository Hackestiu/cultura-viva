# Cultura Viva STT Benchmark


## Dataset & Domain Keywords

`app/data_audio/` contains 16 kHz mono WAV visitor queries and `manifest.json` ground truth. The generated corpus varies intent, register, speaker, and duration. Domain entities are annotated per item and include `Gaudí`, `Sagrada Família`, `salamander`, `dragon`, `trencadís`, `Park Güell`, `Casa Batlló`, `Casa Milà`, and `modernisme`.

Regenerate audio and the manifest together after changing query text:

```bash
cd app
python dataset_generator.py
```

## Tested Models

- faster-whisper `tiny.en` and `base.en`
- Vosk small English
- sherpa-onnx Whisper English

Engines with missing Python dependencies or model files are skipped. All available candidate models are loaded once and then evaluated over the same manifest.

## Evaluation Metrics

Per utterance and aggregate reports include WER, CER, Gaudí keyword spotting accuracy, real-time factor (RTF), inference latency in milliseconds, peak RAM in MB, and model size on disk in MB when the model path is local. Each engine writes a schema-versioned JSON file under `predictions/`, while aggregate metrics are stored in `summary.json`. The benchmark also generates comparison plots and does not generate CSV files.

Latency and RTF measure transcription after the model has been loaded; model startup time is not included. Peak RAM is the process memory observed during transcription and should be treated as a host-side comparison, not as a complete Arduino deployment measurement.

## How to Run

See [app/README.md](app/README.md) for Linux, Windows, model installation, and App Lab packaging. The shortest local run is:

```bash
cd app
python -m pip install -r requirements.txt
python main.py --engines faster-whisper:tiny.en
```

## Results / Findings

Local CPU runs write to `app/results_computer/`; Arduino App Lab runs write to `app/results_arduino/`. Re-run on the target UNO Q before making deployment decisions; host timings and RAM are not edge measurements.

## Historical Colab Execution

`colab/` is a historical artifact from the offline model-selection phase. It documents the evaluation used to choose models before edge-device integration. It is not production runtime code and should not be mixed with current computer or Arduino reports.
