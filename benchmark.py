"""
TTS inference-time benchmark -- meant to run directly on the target board
(the Arduino UNO Q's Linux/Qualcomm QRB2210 side, or any similar ARM SBC),
not on a developer laptop or a cloud GPU, since the whole point is on-device
inference time.

For each model listed in models_config.json: loads it, runs a few warmup +
timed text-to-speech generations over the Gaudí-related sentences in
data/gaudi_sentences.json, saves the resulting audio under
audios/<model_slug>/, measures the on-disk size of the downloaded weights,
and writes the timing results to data/inference_results.json. Sentence text
and timing results are kept in separate files -- run records reference a
sentence by id rather than duplicating its text.

Sentences vary a lot in length (6 to 26 words), and inference time isn't
length-independent, so pooling all runs into one average would just reflect
whichever mix of sentence lengths a model happened to get. Instead, timed
runs are drawn via common.balanced_sentence_sequence() to round-robin evenly
across short/medium/long sentences, each run is tagged with its
`length_bucket`, and results are summarized per bucket (`by_bucket`) as well
as overall.

Only inference time (and on-disk model size / RAM fit) is measured -- audio
quality is out of scope for this benchmark.

The UNO Q's Qualcomm side has no discrete GPU/accelerator usable from plain
PyTorch, so this always runs on CPU; CUDA is still auto-detected as a
convenience in case you're sanity-checking the pipeline elsewhere, but the
numbers that matter are the ones collected on the board itself.

Usage:
    python benchmark.py [--runs N] [--warmup N] [--models slug1,slug2,...]

--runs defaults to 9 (3 short + 3 medium + 3 long) so the default run is
evenly balanced across buckets; any multiple of 3 keeps that balance.
"""

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from common import balanced_sentence_sequence, length_bucket, ram_fit_flags, summarize_by_bucket

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "models_config.json"
SENTENCES_PATH = ROOT / "data" / "gaudi_sentences.json"
AUDIO_DIR = ROOT / "audios"
OUTPUT_PATH = ROOT / "data" / "inference_results.json"

# A fixed speaker embedding index used only for SpeechT5, which has no
# built-in default voice (from the cmu-arctic-xvectors validation split).
SPEECHT5_XVECTOR_INDEX = 7306


def load_sentences():
    return json.loads(SENTENCES_PATH.read_text())["sentences"]


def detect_device():
    """Return (device_kwarg_for_pipeline, human_label). CPU unless CUDA happens to be present."""
    try:
        import torch

        if torch.cuda.is_available():
            return 0, torch.cuda.get_device_name(0)
    except Exception:
        pass

    return -1, "CPU"


def board_ram_mb():
    """Total system RAM in MB, read from /proc/meminfo (Linux/the board itself). None elsewhere."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except Exception:
        return None
    return None


def ram_fit_flags(disk_size_mb):
    estimated_peak_mb = disk_size_mb * RAM_OVERHEAD_FACTOR
    return {f"fits_{label}_ram": estimated_peak_mb <= ram_mb for label, ram_mb in ARDUINO_UNO_Q_RAM_MB.items()}


def dir_size_mb(path: Path) -> float:
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return round(total / (1024 * 1024), 2)


def model_disk_size_mb(*model_ids) -> float:
    """Size on disk of the given repo(s) in the local HF cache."""
    try:
        from huggingface_hub import scan_cache_dir

        cache = scan_cache_dir()
        total = 0
        for repo in cache.repos:
            if repo.repo_id in model_ids:
                total += repo.size_on_disk
        if total:
            return round(total / (1024 * 1024), 2)
    except Exception:
        pass
    return 0.0


# Backend registry: maps a model's "architecture" to the function that knows
# how to load it and return a synth(text) -> (audio_array, sampling_rate)
# callable. Most Hugging Face TTS checkpoints work through the plain
# `text-to-speech` pipeline, so that's the default for any architecture that
# isn't registered here -- adding a model that fits that common case needs
# *no* code change, just a new entry in models_config.json. Register a new
# backend only when a model needs extra plumbing (like SpeechT5's speaker
# embedding) that the generic pipeline call can't supply on its own.
BACKENDS = {}


def backend(*architectures):
    def register(fn):
        for arch in architectures:
            BACKENDS[arch] = fn
        return fn

    return register


@backend("speecht5")
def load_speecht5(entry, device):
    from datasets import load_dataset
    from transformers import pipeline
    import torch

    pipe = pipeline("text-to-speech", model=entry["model_id"], vocoder=entry["vocoder_id"], device=device)
    embeddings = load_dataset("Matthijs/cmu-arctic-xvectors", split="validation", trust_remote_code=True)
    speaker_embedding = torch.tensor(embeddings[SPEECHT5_XVECTOR_INDEX]["xvector"]).unsqueeze(0)

    def synth(text):
        out = pipe(text, forward_params={"speaker_embeddings": speaker_embedding})
        return out["audio"], out["sampling_rate"]

    return synth


def load_generic_pipeline(entry, device):
    """Default backend: any model the HF `text-to-speech` pipeline supports as-is."""
    from transformers import pipeline

    pipe = pipeline("text-to-speech", model=entry["model_id"], device=device)

    def synth(text):
        out = pipe(text)
        return out["audio"], out["sampling_rate"]

    return synth


def build_synthesizer(entry, device):
    """Return a callable synth(text) -> (audio_array, sampling_rate)."""
    loader = BACKENDS.get(entry.get("architecture"), load_generic_pipeline)
    return loader(entry, device)


def run_model(entry, device, num_warmup, num_runs, sentences):
    import soundfile as sf

    slug = entry["slug"]
    out_dir = AUDIO_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== {entry['name']} ({entry['model_id']}) ===")
    approx_mb = entry.get("disk_size_mb")
    if approx_mb:
        for label, fits in ram_fit_flags(approx_mb).items():
            if not fits:
                board = label.replace("fits_", "").replace("_ram", "")
                print(f"  !! warning: ~{approx_mb}MB checkpoint likely won't fit in the {board} UNO Q variant's RAM")

    synth = build_synthesizer(entry, device)

    for _ in range(num_warmup):
        synth(sentences[0]["text"])

    run_sentences = balanced_sentence_sequence(sentences)
    run_records = []
    for i in range(num_runs):
        sentence = next(run_sentences)
        word_count = len(sentence["text"].split())
        bucket = length_bucket(word_count)

        start = time.perf_counter()
        audio, sr = synth(sentence["text"])
        elapsed = time.perf_counter() - start

        audio = audio.squeeze()
        audio_file = out_dir / f"sample_{i + 1:02d}.wav"
        sf.write(audio_file, audio, sr)

        run_records.append(
            {
                "run": i + 1,
                "sentence_id": sentence["id"],
                "word_count": word_count,
                "length_bucket": bucket,
                "inference_time_sec": round(elapsed, 4),
                "audio_seconds": round(len(audio) / sr, 3),
                "audio_file": str(audio_file.relative_to(ROOT).as_posix()),
            }
        )
        print(f"  run {i + 1} [{bucket}, {word_count}w]: {elapsed:.3f}s")

    times = [r["inference_time_sec"] for r in run_records]
    ids = [entry["model_id"]]
    if "vocoder_id" in entry:
        ids.append(entry["vocoder_id"])
    # Prefer the actual size measured from the local HF cache; if the model
    # hasn't been downloaded through that cache (e.g. mirrored elsewhere),
    # fall back to the reference size declared in models_config.json.
    disk_mb = model_disk_size_mb(*ids) or entry.get("disk_size_mb", 0.0)

    return {
        "model_id": entry["model_id"],
        "name": entry["name"],
        "slug": slug,
        "architecture": entry["architecture"],
        "params_millions": entry.get("params_millions"),
        "disk_size_mb": disk_mb,
        **ram_fit_flags(disk_mb),
        "audio_dir": str(out_dir.relative_to(ROOT).as_posix()),
        "runs": run_records,
        "by_bucket": summarize_by_bucket(run_records),
        "avg_inference_time_sec": round(statistics.mean(times), 4),
        "std_inference_time_sec": round(statistics.pstdev(times), 4) if len(times) > 1 else 0.0,
        "min_inference_time_sec": round(min(times), 4),
        "max_inference_time_sec": round(max(times), 4),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=9, help="Timed runs per model (multiples of 3 keep bucket balance)")
    parser.add_argument("--warmup", type=int, default=1, help="Untimed warmup runs per model")
    parser.add_argument("--models", type=str, default=None, help="Comma-separated slugs to run (default: all)")
    args = parser.parse_args()

    all_models = json.loads(CONFIG_PATH.read_text())["models"]
    if args.models:
        wanted = set(args.models.split(","))
        all_models = [m for m in all_models if m["slug"] in wanted]

    sentences = load_sentences()
    device, device_label = detect_device()
    ram_mb = board_ram_mb()
    ram_note = f"{ram_mb} MB detected" if ram_mb else "unknown (not running on Linux? /proc/meminfo unavailable)"
    print(f"Running on device: {device_label}  |  board RAM: {ram_note}")

    results = []
    for entry in all_models:
        try:
            results.append(run_model(entry, device, args.warmup, args.runs, sentences))
        except Exception as exc:
            print(f"  !! skipped {entry['name']}: {exc}")

    payload = {
        "benchmark_meta": {
            "device": device_label,
            "board": "Arduino UNO Q (Qualcomm QRB2210, Cortex-A53, Linux)",
            "board_ram_mb_detected": ram_mb,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "warmup_runs": args.warmup,
            "timed_runs": args.runs,
            "sentences_file": str(SENTENCES_PATH.relative_to(ROOT).as_posix()),
        },
        "results": results,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
