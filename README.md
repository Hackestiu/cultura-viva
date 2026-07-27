# stt-benchmark

Benchmark of Whisper models (`tiny.en`, `base.en`, `small.en`, via `faster-whisper`) on a set of short English audio recordings about Antoni Gaudí's work (Sagrada Família, Park Güell, Casa Batlló, etc.). It measures inference time and Word Error Rate (WER) to compare the speed/accuracy trade-off across model variants.

## Repository structure

```
stt-benchmark/
├── colab/
│   └── stt_benchmark_whisper_test1.ipynb   # Full notebook: setup, benchmarking, plots, export
├── data_audio/
│   └── README.md                           # Link to the audio files (hosted on Google Drive, not versioned here)
├── results/
│   ├── plots/
│   │   ├── avg_inference_time.png          # Average inference time per model
│   │   └── avg_wer.png                     # Average WER per model
│   └── predictions.json                    # Detailed results: file, model, ground truth, transcription, time, WER
└── README.md
```

## Dataset

18 audio recordings in two formats:

| Format | Files | Content |
|---|---|---|
| `.ogg` | `G_cb`, `G_pg`, `G_sf`, `g_completito` | Long-form narrations, one descriptive paragraph per monument (`g_completito` is the combined narration of all three) |
| `.m4a` | `G1`–`G14` | Short Q&A-style questions about facts, techniques, and architectural elements of Gaudí's work |

The ground truth (reference text used to compute WER) is defined directly in the notebook, in the `GROUND_TRUTH` variable.

**Audio files are not committed to this repository.** They are hosted on Google Drive:

**Audio dataset (Google Drive):** `<https://drive.google.com/drive/folders/12tf5xiSog3TiN3sY_WmBBGB-nJSMYQTC?usp=sharing>`

To reproduce the benchmark, download the folder (or mount it directly in Colab) and place its contents under `data_audio/`, matching the filenames used in `GROUND_TRUTH`.

## How to reproduce the benchmark

1. Open `colab/stt_benchmark_whisper_test1.ipynb` in Google Colab.
2. Mount Google Drive and make sure `data_audio/` (from the link above) is accessible — adjust `AUDIO_DIR` in the notebook accordingly.
3. Run all cells in order. The notebook will:
   - Install `faster-whisper`, `jiwer`, `pandas`, `seaborn`.
   - Transcribe each audio file with `tiny.en`, `base.en`, and `small.en`, passing domain keywords via `initial_prompt`.
   - Measure inference time and compute WER for each audio/model combination.
   - Export results to `results/predictions.json`.
   - Generate `results/plots/avg_inference_time.png` and `results/plots/avg_wer.png`.
4. Push the new results to the repo (directly from Colab with `git`, or manually via the GitHub web interface).

## Results

Aggregated results (average time and average WER per model) are available at:
- `results/plots/avg_inference_time.png`
- `results/plots/avg_wer.png`
- `results/predictions.json` (per-file, per-model detail)
