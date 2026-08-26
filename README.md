# tts-benchmark

Compares **inference time** (and on-disk / RAM footprint, as a secondary
axis) across a handful of small, open-source Hugging Face TTS models,
synthesizing Gaudí-related sentences. The target device is an **Arduino UNO
Q** (Qualcomm QRB2210, quad-core ARM Cortex-A53, Linux) — so the benchmark is
meant to be *run on the board itself*, not on a laptop or a cloud GPU, since
the whole point is on-device inference time. Audio quality is intentionally
out of scope.

Uses [`uv`](https://docs.astral.sh/uv/) for everything — no manual venv, no
`pip install`.

## Quickstart

**Generate the report right now** (chart + table), no models/PyTorch needed —
uses the checked-in sample data:

```
uv run visualize.py
```

**Regenerate that sample data yourself** first (fast, synthetic, no GPU/board
needed), then view it:

```
uv run simulate.py && uv run visualize.py
```

**Run it for real**, with the actual models, on the Arduino UNO Q itself (see
[below](#running-the-real-benchmark-on-the-arduino-uno-q)):

```
uv sync --extra real
uv run benchmark.py && uv run visualize.py
```

That's the whole interface: `uv run <script>.py` for anything in this repo —
`uv` creates the venv and installs whatever that script needs on first use.

## Models compared

Configured in [`models_config.json`](models_config.json) — small/edge-friendly
models, plus one larger autoregressive model (Bark-small) kept as a contrast
point to show the size/speed tradeoff:

| model | architecture | params |
|---|---|---|
| `facebook/mms-tts-eng` | VITS (non-autoregressive) | ~36M |
| `kakao-enterprise/vits-ljs` | VITS (non-autoregressive) | ~83M |
| `microsoft/speecht5_tts` | SpeechT5 + HiFi-GAN vocoder | ~174M |
| `suno/bark-small` | Bark (autoregressive) | ~300M |

Arduino UNO Q ships in **2GB and 4GB RAM** variants. Both `benchmark.py` and
`simulate.py` flag any model whose checkpoint likely won't fit in RAM on
either variant (`fits_2GB_ram` / `fits_4GB_ram` in the results JSON) —
Bark-small's ~1.7GB checkpoint is already flagged as unlikely to fit the 2GB
board.

## Layout

```
pyproject.toml / uv.lock         # dependencies -- base (report) + "real" extra (actual models)
models_config.json              # which models to benchmark -- the only file you edit to add one
common.py                        # shared helpers: RAM-fit flags, length-bucket logic, balanced sampling
benchmark.py                     # REAL: run this ON the Arduino UNO Q -- loads each model, times it, saves audio + JSON
simulate.py                       # SYNTHETIC: no board/weights needed, same output shape as benchmark.py
visualize.py                      # reads the JSON, plots time-by-length-bucket vs. size
data/gaudi_sentences.json         # the Gaudí-related sentences used as TTS input (short/medium/long)
data/inference_results.json       # timing results only (sample data checked in),
                                    # each run references a sentence by id
audios/<model-slug>/              # generated audio samples, one folder per model
results/comparison.png            # chart produced by visualize.py
```

Sentences and timing results are kept in separate files on purpose: the
sentence list doesn't change between benchmark runs, while the results file
does, and run records reference a sentence by `id` instead of duplicating its
text.

### Why the dependencies are split into two groups

`pyproject.toml` keeps `torch`/`transformers`/`datasets`/`huggingface-hub`
behind the optional `real` extra, separate from the base
`numpy`/`matplotlib`/`soundfile` install. `simulate.py` and `visualize.py` —
the "generate the report" path — only need the base group, so `uv run
visualize.py` never has to pull down PyTorch just to show you a chart. Only
`benchmark.py` (real model inference) needs `uv sync --extra real`.

### Why results are bucketed by sentence length

Inference time isn't independent of input length, and the 11 Gaudí sentences
range from 6 to 26 words -- so a single average pooled across all runs would
mostly reflect *which* sentences a model happened to get timed on, not how
fast the model actually is. Instead:

- `common.length_bucket(word_count)` sorts every sentence into **short**
  (≤8 words), **medium** (9-16), or **long** (17+).
- `common.balanced_sentence_sequence()` round-robins the timed runs evenly
  across those three buckets (short, medium, long, short, medium, long, ...),
  so results stay balanced regardless of `--runs` or how many sentences exist
  in each bucket.
- Each run record carries its own `word_count` and `length_bucket`; each
  model's result carries a `by_bucket` summary (median/min/max per bucket) in
  addition to the overall pooled stats.
- `visualize.py` plots time **per bucket**, not pooled, so you can see how
  each model scales with input length -- and compare models fairly at a given
  length rather than on whatever sentence mix they happened to run.

## Running the real benchmark on the Arduino UNO Q

The UNO Q's Qualcomm QRB2210 side runs Debian Linux (Arduino App Lab), so it
has a normal Python environment — no cross-compiling or flashing needed for
this benchmark, just running it where it actually matters. [Install
`uv`](https://docs.astral.sh/uv/getting-started/installation/) on the board
if it isn't already there, then:

```
# on the board itself (SSH in, or a terminal in App Lab):
git clone <this-repo>   # or copy the repo over, e.g. scp
cd tts-benchmark
uv sync --extra real                      # pulls in the CPU torch wheel -- the QRB2210 has no CUDA
uv run benchmark.py                       # all models, uses all CPU cores by default
uv run benchmark.py --models mms-tts-eng,vits-ljs --runs 3 --threads 4  # customize models, runs, and thread count
```

Each model is loaded once, given one untimed warmup call (to absorb model
load / first-call overhead), then timed over N generations drawn evenly
across short/medium/long sentences from `data/gaudi_sentences.json` (see
"Why results are bucketed by sentence length" above), using
`time.perf_counter`. Generated audio is written to `audios/<slug>/sample_NN.wav`;
timings, run-level detail (sentence `id`, `word_count`, `length_bucket`),
on-disk weight size, per-bucket summaries, and the RAM-fit flags are written
to `data/inference_results.json`, along with the board's actual detected RAM
(read from `/proc/meminfo`).

There's no GPU/NPU acceleration path from plain PyTorch on this board, so
`detect_device()` always reports CPU (CUDA is still auto-detected as a
convenience if you happen to run the script elsewhere, but the numbers that
matter are the ones collected on the board). Given Bark's autoregressive
decoding, expect it to be dramatically slower here than on a desktop/server
CPU — that slowdown, and whether it fits in RAM at all, is itself one of the
things this benchmark is meant to surface.

`data/inference_results.json` currently contains **simulated sample data**
(clearly marked in `benchmark_meta.note`, with `RTF_PROFILES` in
`simulate.py` documenting the estimates and their basis) so `uv run
visualize.py` has something to plot out of the box — regenerate it for real
by running `benchmark.py` on the actual board.

## Visualizing results

```
uv run visualize.py
```

Prints a table (median time **per length bucket**, plus a "fits 2GB" column)
to the console and writes a two-panel chart to `results/comparison.png`: on
the left, median inference time **per sentence-length bucket** (log-scaled
y-axis, since the fastest and slowest models can differ by 50x+ on this
board) with a whisker spanning min-max per bucket, one line per model — on
the right, on-disk model size, with a callout on any bar that won't fit in
the 2GB RAM variant.

## Adding a new model

1. Append an entry to `models_config.json`:
   ```json
   {
     "slug": "my-new-model",
     "name": "My New Model",
     "model_id": "org/my-new-model",
     "architecture": "vits",
     "params_millions": 40,
     "disk_size_mb": 150.0
   }
   ```
   - `architecture` is free-form and only matters if the model needs special
     loading (see step 2) or if you want `simulate.py` to use a calibrated
     real-time-factor profile for it (see `RTF_PROFILES` in `simulate.py`,
     currently calibrated for the UNO Q's Cortex-A53 CPU). An unrecognized
     value still works — it just falls back to a generic profile/loader.
   - `disk_size_mb` is optional. If you know the real checkpoint size, put it
     here; otherwise both scripts estimate it (from `params_millions`, or by
     scanning the local Hugging Face cache for `benchmark.py`). It also
     drives the `fits_2GB_ram` / `fits_4GB_ram` flags.
2. If the model works through `transformers.pipeline("text-to-speech", ...)`
   as-is (true for most HF TTS checkpoints), **you're done** — no code
   changes needed. If it needs extra setup (a required speaker embedding, a
   separate vocoder, etc.), add one function to the `BACKENDS` registry at
   the top of `benchmark.py`, following the `speecht5` example already there.
3. Regenerate results and the chart:
   ```
   uv run simulate.py     # quick synthetic pass, no board/weights required
   # or, for a real measurement, on the board itself:
   uv sync --extra real && uv run benchmark.py --models my-new-model
   uv run visualize.py
   ```

Both `benchmark.py` and `simulate.py` iterate over every entry in
`models_config.json`, so a newly-added model is picked up automatically —
nothing else needs to be told about it.
