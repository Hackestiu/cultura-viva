"""
Visualize the TTS benchmark: median inference time **per sentence-length
bucket** (short/medium/long) for each model, next to the on-disk model size,
so the size/speed/RAM tradeoff reads at a glance.

Inference time isn't independent of sentence length, so a single number
pooled across sentences of very different lengths would just reflect
whichever mix of lengths a model happened to get timed on. Results are
grouped by length bucket instead (see common.py) -- each point below is the
median over that bucket's runs, with a whisker spanning min-max.

Reads two separate data files:
  - data/gaudi_sentences.json     the Gaudí-related sentences used as input
  - data/inference_results.json   the timing results (references sentences by id)

Usage:
    python visualize.py [--results data/inference_results.json] [--output results/comparison.png]
"""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from common import BUCKET_ORDER

ROOT = Path(__file__).resolve().parent

# Categorical palette. Panel 1 is a multi-line chart, so any two colors can
# end up adjacent depending on the data (not just neighbors in legend order),
# which means it needs the stricter *all-pairs* CVD/contrast validation, not
# just adjacent-pair -- this exact 4-color set passes that (validated via
# validate_palette.js --pairs all; the default palette's 4th slot, yellow,
# fails all-pairs against orange, so it's swapped for violet here). Adding a
# 5th model needs re-validating, not just appending another slot.
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7"]

SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
STATUS_CRITICAL = "#d03b3b"  # reserved status color -- flags a model that won't fit in the 2GB UNO Q's RAM

BUCKET_LABELS = {"short": "short\n(≤ 8 words)", "medium": "medium\n(9–16 words)", "long": "long\n(17+ words)"}

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Segoe UI", "Arial", "sans-serif"]


def load_results(path: Path):
    payload = json.loads(path.read_text())
    results = sorted(
        payload["results"],
        key=lambda r: float(np.median([run["inference_time_sec"] for run in r["runs"]])),
    )
    return payload["benchmark_meta"], results


def print_table(meta, results):
    board = meta.get("board", "unknown board")
    print(f"\nDevice: {meta.get('device', 'unknown')}  |  board: {board}  |  sentences: {meta.get('sentences_file', 'n/a')}")

    buckets_present = [b for b in BUCKET_ORDER if any(b in r.get("by_bucket", {}) for r in results)]
    header = f"{'model':<28}" + "".join(f"{b + ' (s)':>14}" for b in buckets_present) + f"{'size (MB)':>12}{'fits 2GB':>10}"
    print(header)
    print("-" * len(header))
    for r in results:
        by_bucket = r.get("by_bucket", {})
        row = f"{r['name']:<28}"
        for b in buckets_present:
            stats = by_bucket.get(b)
            row += f"{stats['median_sec']:>14.3f}" if stats else f"{'-':>14}"
        fits_2gb = "yes" if r.get("fits_2GB_ram", True) else "NO"
        row += f"{r['disk_size_mb']:>12.1f}{fits_2gb:>10}"
        print(row)


def render(meta, results, output_path: Path):
    sizes = [r["disk_size_mb"] for r in results]
    colors = [COLORS[i % len(COLORS)] for i in range(len(results))]
    n = len(results)
    positions = list(range(n, 0, -1))  # top-to-bottom = fastest-to-slowest (panel 2 order)

    buckets_present = [b for b in BUCKET_ORDER if any(b in r.get("by_bucket", {}) for r in results)]
    bucket_x = {b: i for i, b in enumerate(buckets_present)}

    fig, (ax_time, ax_size) = plt.subplots(1, 2, figsize=(13, 0.9 * n + 2.6))
    fig.patch.set_facecolor(SURFACE)

    device = meta.get("device", "unknown device")
    board = meta.get("board", "")
    fig.suptitle(
        "TTS inference time by sentence length, vs. model size",
        color=INK_PRIMARY, fontsize=16, fontweight="bold", x=0.03, y=0.975, ha="left",
    )
    fig.text(
        0.03, 0.915,
        f"{board or device}  ·  median ± min/max per length bucket, over Gaudí-related sentences",
        color=INK_SECONDARY, fontsize=10.5,
    )

    # --- Panel 1: inference time, per length bucket ---
    ax_time.set_facecolor(SURFACE)
    for r, color in zip(results, colors):
        by_bucket = r.get("by_bucket", {})
        xs, ys, lo, hi = [], [], [], []
        for b in buckets_present:
            stats = by_bucket.get(b)
            if not stats:
                continue
            xs.append(bucket_x[b])
            ys.append(stats["median_sec"])
            lo.append(stats["median_sec"] - stats["min_sec"])
            hi.append(stats["max_sec"] - stats["median_sec"])

        ax_time.errorbar(
            xs, ys, yerr=[lo, hi], fmt="o-", color=color, linewidth=2, markersize=6,
            capsize=4, elinewidth=1.2, ecolor=color, alpha=0.9, label=r["name"],
        )
        # Direct end-label (<=4 series) at the last bucket this model has data for.
        value_label = f"{ys[-1]:.0f}s" if ys[-1] >= 10 else f"{ys[-1]:.2g}s"
        ax_time.annotate(
            f"  {r['name']} ({value_label})", (xs[-1], ys[-1]),
            va="center", ha="left", color=INK_PRIMARY, fontsize=9,
        )

    ax_time.set_xticks(range(len(buckets_present)))
    ax_time.set_xticklabels([BUCKET_LABELS.get(b, b) for b in buckets_present], color=INK_PRIMARY, fontsize=10)
    ax_time.set_xlim(-0.4, len(buckets_present) - 0.4 + 1.6)  # headroom for end-labels
    ax_time.set_ylabel("Inference time (s, log scale)", color=INK_SECONDARY, fontsize=10.5)
    ax_time.set_title("Inference time by sentence length (lower = faster)", color=INK_PRIMARY, fontsize=11.5, loc="left", pad=10)
    # Log scale: the fastest and slowest models can differ by 50x+ on this board.
    ax_time.set_yscale("log")
    ax_time.yaxis.set_major_formatter(plt.matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax_time.yaxis.set_minor_locator(plt.matplotlib.ticker.NullLocator())
    # Headroom above the highest point keeps the legend (placed there) clear of the data.
    ymin, ymax = ax_time.get_ylim()
    ax_time.set_ylim(ymin, ymax * 3)
    ax_time.grid(axis="y", color=GRIDLINE, linewidth=0.8, zorder=0)
    ax_time.set_axisbelow(True)
    ax_time.spines["top"].set_visible(False)
    ax_time.spines["right"].set_visible(False)
    ax_time.spines["left"].set_visible(False)
    ax_time.spines["bottom"].set_color(BASELINE)
    ax_time.tick_params(axis="x", length=0)
    ax_time.tick_params(axis="y", colors=INK_MUTED, labelsize=9.5)
    ax_time.legend(loc="upper left", fontsize=8.5, frameon=False, labelcolor=INK_SECONDARY)

    # --- Panel 2: on-disk size ---
    ax_size.set_facecolor(SURFACE)
    ax_size.barh(positions, sizes, color=colors, height=0.55, alpha=0.9)
    ax_size.set_yticks(positions)
    ax_size.set_yticklabels([r["name"] for r in results], color=INK_PRIMARY, fontsize=10.5)
    ax_size.set_xlabel("Model size on disk (MB)", color=INK_SECONDARY, fontsize=10.5)
    ax_size.set_title("Disk footprint vs. Arduino UNO Q RAM (lower = smaller)", color=INK_PRIMARY, fontsize=11.5, loc="left", pad=10)
    for pos, s, r in zip(positions, sizes, results):
        label = f"{s / 1024:.2f} GB" if s >= 1024 else f"{s:.0f} MB"
        ax_size.text(s + max(sizes) * 0.03, pos, label, va="center", color=INK_SECONDARY, fontsize=9.5)
        if not r.get("fits_2GB_ram", True):
            ax_size.text(
                s + max(sizes) * 0.03, pos - 0.32, "⚠ won't fit in 2GB RAM",
                va="center", color=STATUS_CRITICAL, fontsize=8.5, fontweight="bold",
            )

    ax_size.set_ylim(0.3, n + 0.7)
    ax_size.spines["top"].set_visible(False)
    ax_size.spines["right"].set_visible(False)
    ax_size.spines["left"].set_visible(False)
    ax_size.spines["bottom"].set_color(BASELINE)
    ax_size.tick_params(axis="x", colors=INK_MUTED, labelsize=9.5)
    ax_size.tick_params(axis="y", length=0)
    ax_size.grid(axis="x", color=GRIDLINE, linewidth=0.8, zorder=0)
    ax_size.set_axisbelow(True)
    ax_size.margins(x=0.18)

    fig.tight_layout(rect=(0, 0, 1, 0.86))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, facecolor=SURFACE)
    print(f"\nSaved chart to {output_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ROOT / "data" / "inference_results.json")
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "comparison.png")
    args = parser.parse_args()

    meta, results = load_results(args.results)
    if not results:
        print("No results found in", args.results)
        return

    print_table(meta, results)
    render(meta, results, args.output)


if __name__ == "__main__":
    main()
