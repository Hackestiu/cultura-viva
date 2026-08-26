"""Shared helpers used by benchmark.py, simulate.py, and visualize.py."""

import statistics
from collections import defaultdict
from itertools import cycle

# Arduino UNO Q ships in 2GB and 4GB RAM variants. A loaded model's peak RAM
# use runs somewhat above its on-disk checkpoint size (framework + activation
# overhead); RAM_OVERHEAD_FACTOR is a rough multiplier for flagging models
# that likely won't fit at all.
ARDUINO_UNO_Q_RAM_MB = {"2GB": 2048, "4GB": 4096}
RAM_OVERHEAD_FACTOR = 1.3


def ram_fit_flags(disk_size_mb):
    estimated_peak_mb = disk_size_mb * RAM_OVERHEAD_FACTOR
    return {f"fits_{label}_ram": estimated_peak_mb <= ram_mb for label, ram_mb in ARDUINO_UNO_Q_RAM_MB.items()}


# Sentence length buckets, by word count (upper bound inclusive; last bucket
# has no upper bound). A raw inference-time average pooled across sentences
# of very different lengths is confounded by *which* sentences a model
# happened to get, so timings are grouped by bucket instead.
LENGTH_BUCKETS = [("short", 8), ("medium", 16), ("long", None)]
BUCKET_ORDER = [name for name, _ in LENGTH_BUCKETS]


def length_bucket(word_count):
    for name, max_words in LENGTH_BUCKETS:
        if max_words is None or word_count <= max_words:
            return name
    return BUCKET_ORDER[-1]


def balanced_sentence_sequence(sentences):
    """Yield sentences round-robining across length buckets (short, medium,
    long, short, medium, long, ...), cycling within each bucket. This keeps
    any number of timed runs balanced across sentence lengths instead of
    however the sentences happen to be ordered in the file -- otherwise a
    model could end up timed mostly on short (or mostly on long) sentences
    just by the luck of --runs vs. sentence count.
    """
    buckets = defaultdict(list)
    for s in sentences:
        buckets[length_bucket(len(s["text"].split()))].append(s)

    order = [b for b in BUCKET_ORDER if buckets.get(b)]
    if not order:
        return
    iterators = {b: cycle(buckets[b]) for b in order}
    while True:
        for b in order:
            yield next(iterators[b])


def summarize_by_bucket(runs):
    """runs: list of dicts with "length_bucket" and "inference_time_sec".
    Returns {bucket: {"n":, "median_sec":, "min_sec":, "max_sec":}}.
    """
    by_bucket = defaultdict(list)
    for r in runs:
        by_bucket[r["length_bucket"]].append(r["inference_time_sec"])

    return {
        bucket: {
            "n": len(times),
            "median_sec": round(statistics.median(times), 4),
            "min_sec": round(min(times), 4),
            "max_sec": round(max(times), 4),
        }
        for bucket, times in by_bucket.items()
    }
