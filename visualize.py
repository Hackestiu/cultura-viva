"""Comprehensive visualization tool for STT benchmark results.

Usage:
    uv run visualize.py
    uv run visualize.py --input-dir results_arduino
    uv run visualize.py --input-dir results_computer
    uv run visualize.py --input-dir results_arduino --compare-with results_computer
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Ensure stdout handles unicode cleanly on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import matplotlib
matplotlib.use("Agg")  # Default to non-interactive backend for headless / file export
import matplotlib.pyplot as plt
import numpy as np

APP_DIR = Path(__file__).resolve().parent
REPO_DIR = APP_DIR

# Set modern plotting aesthetic
plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "axes.labelsize": 10,
    "axes.labelweight": "bold",
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.titlesize": 14,
    "figure.titleweight": "bold",
})

# Model color palette
PALETTE = [
    "#2563EB",  # Royal Blue
    "#10B981",  # Emerald Green
    "#F59E0B",  # Amber
    "#8B5CF6",  # Purple
    "#EC4899",  # Pink
    "#06B6D4",  # Cyan
    "#EF4444",  # Red
    "#64748B",  # Slate
]


@dataclass
class EngineSummary:
    engine: str
    avg_wer: float
    avg_cer: float
    avg_keyword_spotting_accuracy: float | None
    avg_inference_time_sec: float
    avg_inference_latency_ms: float
    avg_rtf: float | None
    max_peak_ram_mb: float
    model_size_mb: float | None
    domain_bias_applied: bool
    num_utterances: int
    # Detailed per-utterance lists from predictions
    wer_list: list[float] = field(default_factory=list)
    cer_list: list[float] = field(default_factory=list)
    latency_ms_list: list[float] = field(default_factory=list)
    rtf_list: list[float] = field(default_factory=list)
    keyword_accuracy_list: list[float] = field(default_factory=list)
    predictions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class BenchmarkData:
    source_dir: Path
    platform_name: str
    timestamp: str
    engines: dict[str, EngineSummary] = field(default_factory=dict)


def find_default_results_dir() -> Path:
    """Find the most relevant results directory."""
    candidates = [APP_DIR / "results_arduino", APP_DIR / "results_computer"]
    for path in candidates:
        if path.is_dir() and (
            (path / "summary.json").is_file() or (path / "predictions").is_dir()
        ):
            return path
    return APP_DIR / "results_computer"


def load_benchmark_data(results_dir: Path) -> BenchmarkData:
    """Load summary and detailed predictions from a results directory."""
    if not results_dir.exists():
        raise FileNotFoundError(f"Results directory not found: {results_dir}")

    summary_file = results_dir / "summary.json"
    predictions_dir = results_dir / "predictions"

    summary_rows: list[dict[str, Any]] = []
    if summary_file.is_file():
        try:
            summary_rows = json.loads(summary_file.read_text(encoding="utf-8"))
        except Exception as err:
            print(f"[WARN] Failed to read {summary_file}: {err}")

    # Load prediction files
    prediction_files = list(predictions_dir.glob("*.json")) if predictions_dir.is_dir() else []
    
    platform_name = "Unknown Platform"
    timestamp = "Unknown Date"
    by_engine_preds: dict[str, list[dict[str, Any]]] = {}

    for p_file in prediction_files:
        try:
            content = json.loads(p_file.read_text(encoding="utf-8"))
            meta = content.get("metadata", {})
            platform_name = meta.get("platform", platform_name)
            timestamp = meta.get("execution_timestamp_utc", timestamp)
            model_name = meta.get("model_name")
            preds = content.get("predictions", [])
            
            if preds and not model_name:
                model_name = preds[0].get("engine", p_file.stem)
            
            if model_name:
                by_engine_preds[model_name] = preds
        except Exception as err:
            print(f"[WARN] Failed to read prediction file {p_file}: {err}")

    engines: dict[str, EngineSummary] = {}

    # Build from summary rows
    for row in summary_rows:
        eng_name = row["engine"]
        preds = by_engine_preds.get(eng_name, [])
        
        wer_list = [p["wer"] for p in preds if "wer" in p and p["wer"] == p["wer"]]
        cer_list = [p["cer"] for p in preds if "cer" in p and p["cer"] == p["cer"]]
        lat_list = [p["inference_latency_ms"] for p in preds if "inference_latency_ms" in p]
        rtf_list = [p["rtf"] for p in preds if "rtf" in p and p["rtf"] is not None]
        kw_list = [p["keyword_spotting_accuracy"] for p in preds if p.get("keyword_spotting_accuracy") is not None]

        avg_rtf = (sum(rtf_list) / len(rtf_list)) if rtf_list else None
        if avg_rtf is None and row.get("avg_inference_time_sec"):
            avg_rtf = row.get("avg_inference_time_sec") / 10.0

        engines[eng_name] = EngineSummary(
            engine=eng_name,
            avg_wer=row.get("avg_wer", 0.0),
            avg_cer=row.get("avg_cer", 0.0),
            avg_keyword_spotting_accuracy=row.get("avg_keyword_spotting_accuracy"),
            avg_inference_time_sec=row.get("avg_inference_time_sec", 0.0),
            avg_inference_latency_ms=row.get("avg_inference_latency_ms", 0.0),
            avg_rtf=avg_rtf,
            max_peak_ram_mb=row.get("max_peak_ram_mb", 0.0),
            model_size_mb=row.get("model_size_mb"),
            domain_bias_applied=row.get("domain_bias_applied", False),
            num_utterances=row.get("num_utterances", len(preds)),
            wer_list=wer_list,
            cer_list=cer_list,
            latency_ms_list=lat_list,
            rtf_list=rtf_list,
            keyword_accuracy_list=kw_list,
            predictions=preds,
        )

    # Also include any engines present in predictions/ that weren't in summary.json
    for eng_name, preds in by_engine_preds.items():
        if eng_name in engines:
            continue
        wer_list = [p["wer"] for p in preds if "wer" in p and p["wer"] == p["wer"]]
        cer_list = [p["cer"] for p in preds if "cer" in p and p["cer"] == p["cer"]]
        lat_list = [p["inference_latency_ms"] for p in preds if "inference_latency_ms" in p]
        rtf_list = [p["rtf"] for p in preds if "rtf" in p and p["rtf"] is not None]
        kw_list = [p["keyword_spotting_accuracy"] for p in preds if p.get("keyword_spotting_accuracy") is not None]
        ram_list = [p["peak_ram_mb"] for p in preds if "peak_ram_mb" in p]

        engines[eng_name] = EngineSummary(
            engine=eng_name,
            avg_wer=sum(wer_list) / len(wer_list) if wer_list else 0.0,
            avg_cer=sum(cer_list) / len(cer_list) if cer_list else 0.0,
            avg_keyword_spotting_accuracy=sum(kw_list) / len(kw_list) if kw_list else None,
            avg_inference_time_sec=(sum(lat_list) / len(lat_list) / 1000.0) if lat_list else 0.0,
            avg_inference_latency_ms=sum(lat_list) / len(lat_list) if lat_list else 0.0,
            avg_rtf=sum(rtf_list) / len(rtf_list) if rtf_list else None,
            max_peak_ram_mb=max(ram_list) if ram_list else 0.0,
            model_size_mb=preds[0].get("model_size_mb") if preds else None,
            domain_bias_applied=preds[0].get("domain_bias_applied", False) if preds else False,
            num_utterances=len(preds),
            wer_list=wer_list,
            cer_list=cer_list,
            latency_ms_list=lat_list,
            rtf_list=rtf_list,
            keyword_accuracy_list=kw_list,
            predictions=preds,
        )

    return BenchmarkData(
        source_dir=results_dir,
        platform_name=platform_name,
        timestamp=timestamp,
        engines=engines,
    )


# ---------------------------------------------------------------------------
# Plot Generation Functions
# ---------------------------------------------------------------------------


def plot_dashboard(data: BenchmarkData, output_path: Path) -> None:
    """Generate an all-in-one multi-metric scorecard dashboard."""
    engines = list(data.engines.values())
    if not engines:
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"STT Models Benchmark Summary Dashboard\nSource: {data.source_dir.name} ({len(engines)} Models Evaluated)", fontsize=14, y=0.98)

    labels = [e.engine for e in engines]
    colors = [PALETTE[i % len(PALETTE)] for i in range(len(engines))]
    x = np.arange(len(labels))
    width = 0.26

    # 1. Top-Left: Accuracy & Error Rates
    ax = axes[0, 0]
    wer_vals = [e.avg_wer * 100 for e in engines]
    cer_vals = [e.avg_cer * 100 for e in engines]
    kw_vals = [((e.avg_keyword_spotting_accuracy or 0) * 100) for e in engines]

    b1 = ax.bar(x - width, wer_vals, width, label="WER % (Lower is better)", color="#EF4444", alpha=0.85)
    b2 = ax.bar(x, cer_vals, width, label="CER % (Lower is better)", color="#F59E0B", alpha=0.85)
    b3 = ax.bar(x + width, kw_vals, width, label="Domain Keyword Acc % (Higher is better)", color="#10B981", alpha=0.85)

    ax.set_title("Recognition Accuracy & Error Rates")
    ax.set_ylabel("Percentage (%)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.legend(loc="upper right", framealpha=0.9)
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    for bar in list(b1) + list(b2) + list(b3):
        h = bar.get_height()
        if h > 0:
            ax.annotate(f"{h:.1f}%", xy=(bar.get_x() + bar.get_width() / 2, h),
                        xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=7.5)

    # 2. Top-Right: Latency and Real-Time Factor (RTF)
    ax = axes[0, 1]
    lat_vals = [e.avg_inference_latency_ms for e in engines]
    rtf_vals = [(e.avg_rtf if e.avg_rtf is not None else (e.avg_inference_latency_ms / 10000.0)) for e in engines]

    ax_twin = ax.twinx()
    b_lat = ax.bar(x - width/2, lat_vals, width, label="Avg Latency (ms)", color="#2563EB", alpha=0.85)
    b_rtf = ax_twin.bar(x + width/2, rtf_vals, width, label="RTF (Real-Time Factor)", color="#8B5CF6", alpha=0.85)

    ax_twin.axhline(1.0, color="#DC2626", linestyle="--", linewidth=1.5, label="RTF = 1.0 (Real-Time Limit)")

    ax.set_title("Inference Latency & Real-Time Factor (RTF)")
    ax.set_ylabel("Latency (ms)", color="#2563EB")
    ax_twin.set_ylabel("RTF (Inference Time / Audio Duration)", color="#8B5CF6")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax_twin.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left", framealpha=0.9)

    for bar in b_lat:
        h = bar.get_height()
        ax.annotate(f"{h:.0f}ms", xy=(bar.get_x() + bar.get_width() / 2, h),
                    xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=7.5)
    for bar in b_rtf:
        h = bar.get_height()
        ax_twin.annotate(f"{h:.2f}x", xy=(bar.get_x() + bar.get_width() / 2, h),
                         xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=7.5)

    # 3. Bottom-Left: Memory & Storage Footprint
    ax = axes[1, 0]
    ram_vals = [e.max_peak_ram_mb for e in engines]
    size_vals = [(e.model_size_mb or 0) for e in engines]

    b_ram = ax.bar(x - width/2, ram_vals, width, label="Peak RAM (MB)", color="#06B6D4", alpha=0.85)
    b_size = ax.bar(x + width/2, size_vals, width, label="Model Size (MB)", color="#64748B", alpha=0.85)

    ax.set_title("Memory & Storage Footprint")
    ax.set_ylabel("Megabytes (MB)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.legend(loc="upper left", framealpha=0.9)
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    for bar in list(b_ram) + list(b_size):
        h = bar.get_height()
        if h > 0:
            ax.annotate(f"{h:.1f}M", xy=(bar.get_x() + bar.get_width() / 2, h),
                        xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=7.5)

    # 4. Bottom-Right: Latency vs Accuracy Trade-off
    ax = axes[1, 1]
    for i, e in enumerate(engines):
        acc = (1.0 - min(e.avg_wer, 1.0)) * 100
        lat = e.avg_inference_latency_ms
        size = max(50, (e.model_size_mb or 100) * 1.5)
        ax.scatter(lat, acc, s=size, color=colors[i], label=f"{e.engine} ({size_vals[i]:.0f}MB)", alpha=0.8, edgecolors="black")
        ax.annotate(f" {e.engine}\n ({lat:.0f}ms, {acc:.1f}%)", xy=(lat, acc), fontsize=8, ha="left", va="center")

    ax.set_title("Trade-off: Accuracy vs Latency (Bubble size = Model Disk Size)")
    ax.set_xlabel("Inference Latency (ms) - Lower is better")
    ax.set_ylabel("Word Accuracy % (100 - WER) - Higher is better")
    ax.grid(True, linestyle="--", alpha=0.5)

    plt.tight_layout(rect=(0, 0, 1, 0.95))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


def plot_accuracy_vs_latency(data: BenchmarkData, output_path: Path) -> None:
    """Generate a detailed Accuracy vs Latency Pareto frontier plot."""
    engines = list(data.engines.values())
    if not engines:
        return

    fig, ax = plt.subplots(figsize=(10, 6.5))
    
    latencies = [e.avg_inference_latency_ms for e in engines]
    accuracies = [(1.0 - min(e.avg_wer, 1.0)) * 100 for e in engines]
    names = [e.engine for e in engines]
    
    for i, e in enumerate(engines):
        color = PALETTE[i % len(PALETTE)]
        kw_acc = (e.avg_keyword_spotting_accuracy or 0) * 100
        size = 180 + (kw_acc * 2.5)
        
        ax.scatter(
            e.avg_inference_latency_ms,
            (1.0 - min(e.avg_wer, 1.0)) * 100,
            s=size,
            color=color,
            alpha=0.85,
            edgecolors="black",
            linewidth=1.2,
            zorder=4,
            label=f"{e.engine} (Keyword Acc: {kw_acc:.0f}%, RAM: {e.max_peak_ram_mb:.0f}MB)",
        )
        
        offset_y = 1.2 if (i % 2 == 0) else -2.5
        ax.annotate(
            f"{e.engine}\nWER: {e.avg_wer*100:.1f}% | {e.avg_inference_latency_ms:.0f}ms",
            xy=(e.avg_inference_latency_ms, (1.0 - min(e.avg_wer, 1.0)) * 100),
            xytext=(10, offset_y),
            textcoords="offset points",
            fontweight="bold",
            fontsize=8.5,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.85, edgecolor=color, linewidth=1),
            zorder=5,
        )

    # Sort for Pareto frontier
    sorted_points = sorted(zip(latencies, accuracies, names), key=lambda p: p[0])
    pareto_frontier = []
    max_acc = -1
    for lat, acc, name in sorted_points:
        if acc > max_acc:
            pareto_frontier.append((lat, acc))
            max_acc = acc
    
    if len(pareto_frontier) > 1:
        px, py = zip(*pareto_frontier)
        ax.plot(px, py, "--", color="#2563EB", alpha=0.6, linewidth=2, label="Pareto Frontier (Optimal Trade-off)", zorder=3)

    ax.set_title("STT Models: Accuracy vs. Inference Latency Trade-off\n(Target: High Accuracy [Top] & Low Latency [Left])", fontsize=13)
    ax.set_xlabel("Average Inference Latency (ms) - [Faster <--]", fontsize=11)
    ax.set_ylabel("Word Recognition Accuracy % (100 - WER) - [Better ^]", fontsize=11)
    ax.grid(True, linestyle="--", alpha=0.6)
    ax.legend(loc="lower right", framealpha=0.92, fontsize=9)

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


def plot_realtime_factor(data: BenchmarkData, output_path: Path) -> None:
    """Plot Real-Time Factor (RTF) with streaming edge feasibility zones."""
    engines = list(data.engines.values())
    if not engines:
        return

    fig, ax = plt.subplots(figsize=(9, 5.5))
    
    labels = [e.engine for e in engines]
    rtf_vals = [e.avg_rtf if e.avg_rtf is not None else (e.avg_inference_latency_ms / 10000.0) for e in engines]
    colors = ["#10B981" if rtf <= 1.0 else "#EF4444" for rtf in rtf_vals]
    
    y_pos = np.arange(len(labels))
    bars = ax.barh(y_pos, rtf_vals, color=colors, alpha=0.85, height=0.55, edgecolor="black", linewidth=0.8)
    
    # Real-time threshold
    ax.axvline(1.0, color="#B91C1C", linestyle="--", linewidth=2, zorder=5, label="RTF = 1.0 (Real-Time Boundary)")
    
    # Shaded zones
    max_x = max(max(rtf_vals) * 1.15, 1.5)
    ax.axvspan(0, 1.0, color="#10B981", alpha=0.12, label="Real-Time Capable (RTF < 1.0)")
    ax.axvspan(1.0, max_x, color="#EF4444", alpha=0.10, label="Lagging / Buffering (RTF > 1.0)")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontweight="bold")
    ax.invert_yaxis()
    ax.set_xlabel("Real-Time Factor (RTF = Inference Duration / Audio Duration) - Lower is better", fontsize=10)
    ax.set_title("Edge STT Feasibility: Real-Time Factor (RTF) Comparison", fontsize=12)
    ax.set_xlim(0, max_x)
    ax.grid(axis="x", linestyle="--", alpha=0.5)
    ax.legend(loc="lower right", framealpha=0.9)

    for bar, rtf in zip(bars, rtf_vals):
        w = bar.get_width()
        status = "[Real-Time]" if rtf <= 1.0 else "[Slower]"
        speed = f"{1.0/rtf:.1f}x real-time" if rtf > 0 else ""
        ax.annotate(f" {rtf:.3f}x ({speed}, {status})", xy=(w, bar.get_y() + bar.get_height() / 2),
                    xytext=(5, 0), textcoords="offset points", ha="left", va="center", fontsize=8.5, fontweight="bold")

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


def plot_error_distributions(data: BenchmarkData, output_path: Path) -> None:
    """Plot per-utterance error and latency distributions across test queries."""
    engines = [e for e in data.engines.values() if e.wer_list]
    if not engines:
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))
    fig.suptitle("Per-Utterance Robustness & Variance Across Test Audio Clips", fontsize=13, y=0.98)

    labels = [e.engine for e in engines]
    wer_data = [[w * 100 for w in e.wer_list] for e in engines]
    lat_data = [e.latency_ms_list for e in engines]

    # WER Boxplot
    b1 = ax1.boxplot(wer_data, tick_labels=labels, patch_artist=True, showmeans=True,
                     meanprops=dict(marker="D", markerfacecolor="red", markeredgecolor="black", markersize=6))
    for patch, color in zip(b1["boxes"], PALETTE):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    
    ax1.set_title("Word Error Rate (WER %) Distribution")
    ax1.set_ylabel("WER % (Lower is better)")
    ax1.set_xticklabels(labels, rotation=20, ha="right")
    ax1.grid(axis="y", linestyle="--", alpha=0.5)

    # Latency Boxplot
    b2 = ax2.boxplot(lat_data, tick_labels=labels, patch_artist=True, showmeans=True,
                     meanprops=dict(marker="D", markerfacecolor="red", markeredgecolor="black", markersize=6))
    for patch, color in zip(b2["boxes"], PALETTE):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    ax2.set_title("Inference Latency (ms) Distribution")
    ax2.set_ylabel("Latency in ms (Lower is better)")
    ax2.set_xticklabels(labels, rotation=20, ha="right")
    ax2.grid(axis="y", linestyle="--", alpha=0.5)

    plt.tight_layout(rect=(0, 0, 1, 0.95))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


def plot_hardware_comparison(data_arduino: BenchmarkData, data_computer: BenchmarkData, output_path: Path) -> None:
    """Generate comparative performance chart between Arduino UNO Q and Computer."""
    common_engines = [
        eng for eng in data_arduino.engines if eng in data_computer.engines
    ]
    if not common_engines:
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("Hardware Scaling: Arduino UNO Q vs. Host Computer", fontsize=13, y=0.98)

    x = np.arange(len(common_engines))
    width = 0.35

    # Latency comparison
    ax = axes[0]
    lat_ard = [data_arduino.engines[eng].avg_inference_latency_ms for eng in common_engines]
    lat_cmp = [data_computer.engines[eng].avg_inference_latency_ms for eng in common_engines]

    b1 = ax.bar(x - width/2, lat_cmp, width, label="Host Computer CPU", color="#3B82F6", alpha=0.85)
    b2 = ax.bar(x + width/2, lat_ard, width, label="Arduino UNO Q", color="#10B981", alpha=0.85)

    ax.set_title("Inference Latency (ms)")
    ax.set_ylabel("Latency (ms)")
    ax.set_xticks(x)
    ax.set_xticklabels(common_engines, rotation=15, ha="right")
    ax.legend()
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    for bar in list(b1) + list(b2):
        h = bar.get_height()
        ax.annotate(f"{h:.0f}ms", xy=(bar.get_x() + bar.get_width()/2, h),
                    xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=8)

    # WER comparison
    ax = axes[1]
    wer_ard = [data_arduino.engines[eng].avg_wer * 100 for eng in common_engines]
    wer_cmp = [data_computer.engines[eng].avg_wer * 100 for eng in common_engines]

    b1 = ax.bar(x - width/2, wer_cmp, width, label="Host Computer WER %", color="#6366F1", alpha=0.85)
    b2 = ax.bar(x + width/2, wer_ard, width, label="Arduino UNO Q WER %", color="#EC4899", alpha=0.85)

    ax.set_title("Word Error Rate (WER %)")
    ax.set_ylabel("WER %")
    ax.set_xticks(x)
    ax.set_xticklabels(common_engines, rotation=15, ha="right")
    ax.legend()
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    for bar in list(b1) + list(b2):
        h = bar.get_height()
        ax.annotate(f"{h:.1f}%", xy=(bar.get_x() + bar.get_width()/2, h),
                    xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=8)

    plt.tight_layout(rect=(0, 0, 1, 0.95))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


# ---------------------------------------------------------------------------
# HTML Report Generator
# ---------------------------------------------------------------------------


def generate_html_report(data: BenchmarkData, plot_files: dict[str, Path], output_path: Path) -> None:
    """Generate a self-contained responsive HTML evaluation report."""
    engines = list(data.engines.values())
    if not engines:
        return

    def compute_score(e: EngineSummary) -> float:
        acc_score = max(0, 1.0 - e.avg_wer) * 40
        kw_score = (e.avg_keyword_spotting_accuracy or 0) * 20
        rtf_val = e.avg_rtf if e.avg_rtf is not None else (e.avg_inference_latency_ms / 10000.0)
        speed_score = min(25, (1.0 / max(0.1, rtf_val)) * 15)
        ram_score = max(0, 15 - (e.max_peak_ram_mb / 40.0))
        return acc_score + kw_score + speed_score + ram_score

    scored_engines = sorted(engines, key=compute_score, reverse=True)
    best_engine = scored_engines[0] if scored_engines else None

    table_rows = []
    for rank, e in enumerate(scored_engines, 1):
        rtf_val = e.avg_rtf if e.avg_rtf is not None else (e.avg_inference_latency_ms / 10000.0)
        rtf_badge = '<span style="color:#059669;font-weight:bold;">Real-Time</span>' if rtf_val <= 1.0 else '<span style="color:#DC2626;font-weight:bold;">Lagging</span>'
        kw_str = f"{(e.avg_keyword_spotting_accuracy or 0)*100:.1f}%" if e.avg_keyword_spotting_accuracy is not None else "N/A"
        bias_str = '<span style="color:#2563EB;font-weight:600;">Yes</span>' if e.domain_bias_applied else '<span style="color:#64748B;">No</span>'
        
        table_rows.append(f"""
        <tr style="border-bottom:1px solid #E2E8F0; {'background:#F0FDF4;' if rank == 1 else ''}">
            <td style="padding:10px 14px; text-align:center; font-weight:bold;">#{rank}</td>
            <td style="padding:10px 14px; font-weight:bold; color:#1E293B;">{html.escape(e.engine)}</td>
            <td style="padding:10px 14px; text-align:right; font-weight:bold; color:{'#16A34A' if e.avg_wer < 0.25 else '#DC2626'};">{e.avg_wer*100:.1f}%</td>
            <td style="padding:10px 14px; text-align:right;">{e.avg_cer*100:.1f}%</td>
            <td style="padding:10px 14px; text-align:right;">{kw_str}</td>
            <td style="padding:10px 14px; text-align:right; font-weight:bold;">{e.avg_inference_latency_ms:.0f} ms</td>
            <td style="padding:10px 14px; text-align:center;">{rtf_val:.3f}x ({rtf_badge})</td>
            <td style="padding:10px 14px; text-align:right;">{e.max_peak_ram_mb:.1f} MB</td>
            <td style="padding:10px 14px; text-align:right;">{f"{e.model_size_mb:.1f} MB" if e.model_size_mb else "N/A"}</td>
            <td style="padding:10px 14px; text-align:center;">{bias_str}</td>
        </tr>
        """)

    image_cards = []
    for title, plot_file in plot_files.items():
        if plot_file.is_file():
            rel_path = plot_file.name
            image_cards.append(f"""
            <div style="background:white; border-radius:10px; padding:16px; box-shadow:0 2px 8px rgba(0,0,0,0.06); margin-bottom:24px; border:1px solid #E2E8F0;">
                <h3 style="margin-top:0; color:#1E293B; font-size:16px; border-bottom:1px solid #F1F5F9; padding-bottom:8px;">{title}</h3>
                <img src="{rel_path}" alt="{title}" style="width:100%; height:auto; border-radius:6px; display:block;" />
            </div>
            """)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>STT Models Benchmark Evaluation - Cultura Viva</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #F8FAFC; color: #334155; margin: 0; padding: 24px; line-height: 1.5; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ background: white; padding: 24px 32px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); margin-bottom: 24px; border-left: 6px solid #2563EB; }}
        .card {{ background: white; padding: 24px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); margin-bottom: 24px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
        th {{ background: #F1F5F9; color: #475569; padding: 12px 14px; text-align: left; font-weight: 600; }}
        .recommendation {{ background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 10px; padding: 16px 20px; margin-bottom: 24px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 style="margin:0 0 8px 0; color:#0F172A; font-size:24px;">STT Benchmark Model Evaluation Report</h1>
            <p style="margin:0; color:#64748B; font-size:14px;">Source: <strong>{html.escape(str(data.source_dir))}</strong> | Platform: <strong>{html.escape(data.platform_name)}</strong> | Tested Models: <strong>{len(engines)}</strong></p>
        </div>

        {f'''
        <div class="recommendation">
            <h3 style="margin:0 0 6px 0; color:#1D4ED8; font-size:16px;">Recommendation for Arduino UNO Q Deployment</h3>
            <p style="margin:0; color:#1E40AF; font-size:14px;">
                <strong>{html.escape(best_engine.engine)}</strong> achieves the most balanced edge profile: 
                <strong>{best_engine.avg_wer*100:.1f}% WER</strong>, 
                <strong>{best_engine.avg_inference_latency_ms:.0f} ms latency</strong> 
                ({(best_engine.avg_rtf or best_engine.avg_inference_latency_ms/10000.0):.2f}x RTF), 
                and <strong>{best_engine.max_peak_ram_mb:.0f} MB peak RAM</strong>.
            </p>
        </div>
        ''' if best_engine else ''}

        <div class="card">
            <h2 style="margin-top:0; font-size:18px; color:#0F172A;">Performance Scorecard & Metrics</h2>
            <div style="overflow-x:auto;">
                <table>
                    <thead>
                        <tr>
                            <th style="text-align:center;">Rank</th>
                            <th>Model / Engine</th>
                            <th style="text-align:right;">Avg WER</th>
                            <th style="text-align:right;">Avg CER</th>
                            <th style="text-align:right;">Keyword Acc</th>
                            <th style="text-align:right;">Latency (ms)</th>
                            <th style="text-align:center;">RTF / Real-Time</th>
                            <th style="text-align:right;">Peak RAM</th>
                            <th style="text-align:right;">Model Size</th>
                            <th style="text-align:center;">Domain Bias</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(table_rows)}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="card">
            <h2 style="margin-top:0; font-size:18px; color:#0F172A;">Visual Performance Representations</h2>
            {''.join(image_cards)}
        </div>
    </div>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_content, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI & Terminal Output
# ---------------------------------------------------------------------------


def print_terminal_summary(data: BenchmarkData) -> None:
    """Print a clean, rich ASCII performance scorecard to the console."""
    engines = list(data.engines.values())
    if not engines:
        print("[WARN] No benchmark results found to display.")
        return

    sorted_by_wer = sorted(engines, key=lambda e: e.avg_wer)
    sorted_by_lat = sorted(engines, key=lambda e: e.avg_inference_latency_ms)

    print("\n" + "=" * 88)
    print("CULTURA VIVA STT BENCHMARK EVALUATION SUMMARY")
    print(f"   Source Directory: {data.source_dir}")
    print(f"   Platform:         {data.platform_name}")
    print(f"   Models Evaluated: {len(engines)}")
    print("=" * 88)
    
    header = f"{'Engine':<26} | {'WER':<8} | {'CER':<8} | {'Kw Acc':<8} | {'Latency':<10} | {'RTF':<9} | {'Peak RAM':<9} | {'Size':<8}"
    print(header)
    print("-" * 88)
    
    for e in sorted_by_wer:
        rtf_val = e.avg_rtf if e.avg_rtf is not None else (e.avg_inference_latency_ms / 10000.0)
        kw_str = f"{(e.avg_keyword_spotting_accuracy or 0)*100:.1f}%" if e.avg_keyword_spotting_accuracy is not None else "N/A"
        size_str = f"{e.model_size_mb:.1f}M" if e.model_size_mb else "N/A"
        rtf_str = f"{rtf_val:.3f}x"
        
        print(f"{e.engine:<26} | {e.avg_wer*100:>6.1f}% | {e.avg_cer*100:>6.1f}% | {kw_str:>8} | {e.avg_inference_latency_ms:>7.0f} ms | {rtf_str:>9} | {e.max_peak_ram_mb:>6.1f} MB | {size_str:>8}")

    print("-" * 88)
    
    print("\nKEY INSIGHTS & RANKINGS:")
    if sorted_by_wer:
        print(f"  [Highest Accuracy] {sorted_by_wer[0].engine} (WER: {sorted_by_wer[0].avg_wer*100:.1f}%)")
    if sorted_by_lat:
        print(f"  [Lowest Latency]   {sorted_by_lat[0].engine} ({sorted_by_lat[0].avg_inference_latency_ms:.0f} ms, {(sorted_by_lat[0].avg_rtf or sorted_by_lat[0].avg_inference_latency_ms/10000.0):.2f}x RTF)")
    
    realtime_engines = [e.engine for e in engines if (e.avg_rtf or e.avg_inference_latency_ms/10000.0) <= 1.0]
    if realtime_engines:
        print(f"  [Real-Time Capable] {', '.join(realtime_engines)}")
    else:
        print("  [Warning] No models achieved RTF < 1.0 real-time processing threshold.")
    print("=" * 88 + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize and evaluate performance of Speech-to-Text models benchmarked on Arduino or Computer."
    )
    parser.add_argument(
        "-i", "--input-dir", "--results-dir",
        dest="input_dir",
        default=None,
        help="Path to results directory (default: auto-detect results_arduino or results_computer)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        dest="output_dir",
        default=None,
        help="Directory to save generated visualization plots and HTML report (default: <input-dir>/plots)",
    )
    parser.add_argument(
        "--compare-with",
        dest="compare_with",
        default=None,
        help="Optional second results directory to compare with (e.g. comparing results_arduino with results_computer)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display interactive matplotlib figures in GUI windows",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Skip generating standalone HTML evaluation report",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Determine input directory
    if args.input_dir:
        input_dir = Path(args.input_dir).resolve()
    else:
        input_dir = find_default_results_dir().resolve()

    print(f"Loading benchmark results from: {input_dir}")
    if not input_dir.exists():
        print(f"[ERROR] Results directory does not exist: {input_dir}")
        print("Tip: Run the benchmark first (e.g. on Arduino or locally: `uv run python main.py`).")
        sys.exit(1)

    data = load_benchmark_data(input_dir)
    if not data.engines:
        print(f"[ERROR] No valid benchmark predictions or summary found in {input_dir}.")
        sys.exit(1)

    # Determine output directory
    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    else:
        output_dir = input_dir / "plots"

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Saving visualizations to: {output_dir}")

    plot_files: dict[str, Path] = {}

    p_dash = output_dir / "dashboard_summary.png"
    plot_dashboard(data, p_dash)
    plot_files["Comprehensive Performance Dashboard"] = p_dash

    p_pareto = output_dir / "accuracy_vs_latency_pareto.png"
    plot_accuracy_vs_latency(data, p_pareto)
    plot_files["Accuracy vs. Latency Pareto Frontier"] = p_pareto

    p_rtf = output_dir / "rtf_realtime_factor.png"
    plot_realtime_factor(data, p_rtf)
    plot_files["Real-Time Factor (RTF) Edge Feasibility"] = p_rtf

    if any(e.wer_list for e in data.engines.values()):
        p_dist = output_dir / "error_distribution_boxplots.png"
        plot_error_distributions(data, p_dist)
        plot_files["Per-Utterance Error & Latency Distributions"] = p_dist

    compare_dir = None
    if args.compare_with:
        compare_dir = Path(args.compare_with).resolve()
    elif input_dir.name == "results_arduino" and (APP_DIR / "results_computer").is_dir():
        compare_dir = APP_DIR / "results_computer"

    if compare_dir and compare_dir.exists():
        try:
            data_cmp = load_benchmark_data(compare_dir)
            p_hw = output_dir / "hardware_comparison.png"
            plot_hardware_comparison(data, data_cmp, p_hw)
            plot_files["Hardware Scaling (Arduino vs. Computer)"] = p_hw
            print(f"Generated hardware comparison against: {compare_dir}")
        except Exception as err:
            print(f"[WARN] Could not generate hardware comparison: {err}")

    # Generate HTML report
    if not args.no_html:
        html_report_path = output_dir / "evaluation_report.html"
        generate_html_report(data, plot_files, html_report_path)
        print(f"Generated interactive HTML report: {html_report_path}")

    # Print rich terminal scorecard
    print_terminal_summary(data)

    print(f"Visual representations successfully saved in: {output_dir}")
    print(f"  * Dashboard Overview:   {p_dash.name}")
    print(f"  * Pareto Frontier:      {p_pareto.name}")
    print(f"  * Real-Time Factor:     {p_rtf.name}")
    if not args.no_html:
        print(f"  * HTML Report:          evaluation_report.html")

    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
