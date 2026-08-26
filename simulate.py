"""
Generate realistic *synthetic* benchmark data for every model in
models_config.json, without needing the actual model weights, PyTorch, or
physical access to an Arduino UNO Q board.

This exists so a new model can be added to the comparison with zero manual
data-entry: append it to models_config.json and re-run this script -- it
picks up the new entry automatically, along with any model added earlier.
For a real measurement, run benchmark.py directly on the board instead
(needs the actual deps and weights); this script never claims to be that --
its RTF_PROFILES below are order-of-magnitude engineering estimates for a
weak quad-core ARM Cortex-A53 @ ~2GHz (the UNO Q's Qualcomm QRB2210 Linux
side, no usable GPU/NPU from plain PyTorch), not measurements, and should be
replaced with real numbers the first time someone runs benchmark.py on the
actual board.

Timings aren't arbitrary otherwise: each architecture has a characteristic
real-time factor (RTF = inference seconds per second of generated audio) --
non-autoregressive models like VITS synthesize close to (or faster than)
real time even on weak CPUs, autoregressive ones like Bark run many times
slower than real time and get worse on weak CPUs -- scaled by parameter
count (bigger checkpoints in the same family run somewhat slower), with
Gaussian run-to-run jitter plus an occasional slow/"cold" outlier run, which
is what real hardware benchmarks look like.

Sentences vary in length (6 to 26 words), so runs are drawn via
common.balanced_sentence_sequence() to stay evenly split across
short/medium/long sentences, and results are summarized per bucket
(`by_bucket`) as well as overall -- pooling times across very different
sentence lengths would just reflect the sentence mix, not the model.

Usage:
    python simulate.py [--runs N] [--seed N]

--runs defaults to 9 (3 short + 3 medium + 3 long).
"""

import argparse
import json
import random
import statistics
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import soundfile as sf

from common import balanced_sentence_sequence, length_bucket, ram_fit_flags, summarize_by_bucket

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "models_config.json"
SENTENCES_PATH = ROOT / "data" / "gaudi_sentences.json"
AUDIO_DIR = ROOT / "audios"
OUTPUT_PATH = ROOT / "data" / "inference_results.json"

SPEAKING_RATE_WPS = 2.5  # words/sec, ~150 wpm -- used to size synthetic audio
SAMPLE_RATE = 16000
BYTES_PER_PARAM = 4  # fp32 checkpoint, used only when a model has no disk_size_mb override

# Real-time factor (inference_sec / audio_sec) per architecture family, taken
# at a representative parameter count `ref_params_millions`, calibrated for a
# weak quad-core Cortex-A53 (no GPU/NPU acceleration) rather than a desktop
# CPU or an accelerator -- expect roughly a 5-15x slowdown versus typical
# published RTFs measured on a modern x86 machine. Unknown/new architectures
# fall back to "_default" so a brand-new family still produces a plausible
# (if uncalibrated) result instead of erroring out.
RTF_PROFILES = {
    "vits": dict(base_rtf=0.7, ref_params_millions=60, scaling_exponent=0.25),
    "speecht5": dict(base_rtf=3.5, ref_params_millions=170, scaling_exponent=0.30),
    "bark": dict(base_rtf=35.0, ref_params_millions=300, scaling_exponent=0.35),
    "_default": dict(base_rtf=1.0, ref_params_millions=100, scaling_exponent=0.30),
}

RUN_NOISE_STDDEV = 0.08       # per-run Gaussian jitter, as a fraction of the expected time (a weak, shared/throttled
                               # CPU has noisier scheduling than a dedicated accelerator)
OUTLIER_PROBABILITY = 0.15    # chance a run is a slow "cold" outlier (thermal throttling, background Linux tasks)
OUTLIER_RANGE = (1.3, 2.2)    # multiplier applied to outlier runs


def estimate_inference_time(architecture, params_millions, audio_seconds, rng):
    profile = RTF_PROFILES.get(architecture, RTF_PROFILES["_default"])
    params_millions = params_millions or profile["ref_params_millions"]
    size_factor = (params_millions / profile["ref_params_millions"]) ** profile["scaling_exponent"]
    expected = audio_seconds * profile["base_rtf"] * size_factor

    noise = max(rng.gauss(1.0, RUN_NOISE_STDDEV), 0.7)
    if rng.random() < OUTLIER_PROBABILITY:
        noise *= rng.uniform(*OUTLIER_RANGE)
    return max(expected * noise, 0.01)


def estimate_disk_size_mb(entry):
    if "disk_size_mb" in entry:
        return entry["disk_size_mb"]
    params = entry.get("params_millions", RTF_PROFILES["_default"]["ref_params_millions"])
    return round(params * 1e6 * BYTES_PER_PARAM / (1024 * 1024) * 1.05, 1)


def make_placeholder_audio(path: Path, duration_sec: float, seed_hz: float):
    t = np.linspace(0, duration_sec, max(int(SAMPLE_RATE * duration_sec), 1), endpoint=False)
    tone = 0.05 * np.sin(2 * np.pi * seed_hz * t) * np.exp(-t / (duration_sec + 0.01))
    sf.write(path, tone.astype(np.float32), SAMPLE_RATE)


def simulate_model(entry, sentences, num_runs, rng):
    slug = entry["slug"]
    out_dir = AUDIO_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    run_sentences = balanced_sentence_sequence(sentences)
    runs = []
    for i in range(num_runs):
        sentence = next(run_sentences)
        word_count = len(sentence["text"].split())
        bucket = length_bucket(word_count)
        audio_seconds = round(word_count / SPEAKING_RATE_WPS, 2)
        inference_time = estimate_inference_time(entry.get("architecture"), entry.get("params_millions"), audio_seconds, rng)

        audio_file = out_dir / f"sample_{i + 1:02d}.wav"
        make_placeholder_audio(audio_file, audio_seconds, seed_hz=180 + 20 * (i % 5))

        runs.append(
            {
                "run": i + 1,
                "sentence_id": sentence["id"],
                "word_count": word_count,
                "length_bucket": bucket,
                "inference_time_sec": round(inference_time, 4),
                "audio_seconds": audio_seconds,
                "audio_file": str(audio_file.relative_to(ROOT).as_posix()),
            }
        )

    times = [r["inference_time_sec"] for r in runs]
    return {
        "model_id": entry["model_id"],
        "name": entry["name"],
        "slug": slug,
        "architecture": entry.get("architecture"),
        "params_millions": entry.get("params_millions"),
        "disk_size_mb": estimate_disk_size_mb(entry),
        **ram_fit_flags(estimate_disk_size_mb(entry)),
        "audio_dir": str(out_dir.relative_to(ROOT).as_posix()),
        "runs": runs,
        "by_bucket": summarize_by_bucket(runs),
        "avg_inference_time_sec": round(statistics.mean(times), 4),
        "std_inference_time_sec": round(statistics.pstdev(times), 4) if len(times) > 1 else 0.0,
        "min_inference_time_sec": round(min(times), 4),
        "max_inference_time_sec": round(max(times), 4),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=9, help="Simulated timed runs per model (multiples of 3 keep bucket balance)")
    parser.add_argument("--seed", type=int, default=0, help="RNG seed, for reproducible sample data")
    args = parser.parse_args()

    models = json.loads(CONFIG_PATH.read_text())["models"]
    sentences = json.loads(SENTENCES_PATH.read_text())["sentences"]
    rng = random.Random(args.seed)

    results = [simulate_model(entry, sentences, args.runs, rng) for entry in models]

    payload = {
        "benchmark_meta": {
            "device": "CPU (simulated: quad-core ARM Cortex-A53 @ ~2GHz)",
            "board": "Arduino UNO Q (Qualcomm QRB2210, Linux)",
            "note": (
                "SIMULATED data (see simulate.py) -- not a real measurement. "
                "Regenerate for real with `python benchmark.py` run directly on an Arduino UNO Q."
            ),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "warmup_runs": 1,
            "timed_runs": args.runs,
            "sentences_file": str(SENTENCES_PATH.relative_to(ROOT).as_posix()),
        },
        "results": results,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"Simulated {len(results)} model(s) -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
