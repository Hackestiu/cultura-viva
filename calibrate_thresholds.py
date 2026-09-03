"""
Calibrate OOD thresholds for a gaudi-vision ONNX checkpoint.

Loads the validation split of the specified monument from Hugging Face (using the
same splitting logic as train_classifier.py), runs inference on every validation
image, then:
  - Prints a calibration summary table.
  - Suggests entropy and confidence thresholds that keep >= recall_target of
    in-distribution (ID) validation images accepted.
  - Saves calibration_results.json and calibration_plot.png to the output dir.
  - Prints a config.yaml snippet you can paste directly into the monument or
    model entry to override the global inference defaults.

Usage:
    python calibrate_thresholds.py <checkpoint_dir> <monument_name> [options]

Examples:
    python calibrate_thresholds.py onnx_export/sagrada_familia-vit sagrada_familia
    python calibrate_thresholds.py onnx_export/park_guell-vit park_guell --recall-target 0.97
    python calibrate_thresholds.py onnx_export/sagrada_familia-vit sagrada_familia --output-dir reports/sf-vit
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import yaml

# Reuse the inference helpers; inference.py must be in the same directory.
sys.path.insert(0, str(Path(__file__).parent))
from inference import MonumentClassifier, shannon_entropy

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.yaml")


# -- Config / dataset helpers --------------------------------------------------


def _load_config(config_path: str) -> dict:
    with open(config_path) as fh:
        return yaml.safe_load(fh) or {}


def _monument_data_dir(cfg: dict, monument_name: str, config_path: str) -> str:
    for m in cfg.get("monuments", []):
        if m.get("name") == monument_name:
            return m["data_dir"]
    raise ValueError(
        f"Monument '{monument_name}' not found in {config_path}. "
        f"Available: {[m['name'] for m in cfg.get('monuments', [])]}"
    )


def _is_offline_error(err_str: str) -> bool:
    err_lower = err_str.lower()
    return (
        "couldn't find cache" in err_lower
        or "offlinemodeisenabledvalue" in err_lower
        or "offlinemodeisdenabled" in err_lower
        or "offlinemodeisen" in err_lower
        or "OfflineModeIsEnabled" in err_str
        or ("couldn't reach" in err_lower and "offline" in err_lower)
    )


def _try_load(hf_dataset_name: str, load_kwargs: dict):
    from datasets import load_dataset
    max_retries = 5
    backoff_factor = 30
    for attempt in range(1, max_retries + 1):
        try:
            return load_dataset(hf_dataset_name, **load_kwargs)
        except Exception as e:
            err_str = str(e)
            is_rate_limit = "429" in err_str or "too many requests" in err_str.lower() or "rate limit" in err_str.lower()
            if _is_offline_error(err_str):
                raise
            if is_rate_limit and attempt < max_retries:
                wait_time = attempt * backoff_factor
                print(f"\n[Warning] Hit Hugging Face rate limit (429) on attempt {attempt}/{max_retries}.")
                print(f"Waiting {wait_time} seconds before retrying...")
                time.sleep(wait_time)
            else:
                raise


def _load_val_split(cfg: dict, monument_name: str, data_dir: str):
    """Load the HF dataset and return the validation split, replicating train_classifier.py logic."""
    from datasets import ClassLabel, DatasetDict

    hf_dataset_name = cfg["dataset"]["name"]
    hf_token = os.environ.get("HF_TOKEN")
    seed = cfg["dataset"]["seed"]
    val_size = cfg["dataset"]["val_size"]
    test_size = cfg["dataset"]["test_size"]

    base_kwargs: dict = {}
    if hf_token:
        base_kwargs["token"] = hf_token

    is_offline = bool(os.environ.get("HF_DATASETS_OFFLINE") or os.environ.get("HF_HUB_OFFLINE"))

    print(f"Loading HF dataset  : {hf_dataset_name} / {data_dir}")
    try:
        raw = _try_load(hf_dataset_name, {**base_kwargs, "data_dir": data_dir})
    except Exception as e:
        err_str = str(e)
        if _is_offline_error(err_str):
            print(f"\n[Info] Per-monument cache not found for '{data_dir}'.")
            print(f"[Info] Loading full cached dataset and filtering for '{monument_name}'...")
            full_dataset = _try_load(hf_dataset_name, {**base_kwargs})
            all_label_names = full_dataset["train"].features["label"].names
            monument_label_indices = [
                i for i, name in enumerate(all_label_names)
                if name.startswith(data_dir + "/") or name.startswith(data_dir + "\\")
                or f"/{data_dir}/" in name or f"\\{data_dir}\\" in name
                or name.split("/")[0] == data_dir or name.split("\\")[0] == data_dir
            ]
            if not monument_label_indices:
                raise ValueError(
                    f"Could not find any labels for monument '{monument_name}' (data_dir='{data_dir}') "
                    f"in the full cached dataset. Available labels: {all_label_names}"
                )
            local_label_names = [all_label_names[i].split("/")[-1].split("\\")[-1] for i in monument_label_indices]
            old_to_new = {old: new for new, old in enumerate(monument_label_indices)}

            def filter_and_remap(split):
                filtered = split.filter(lambda ex: ex["label"] in monument_label_indices)
                filtered = filtered.map(lambda ex: {"label": old_to_new[ex["label"]]})
                new_features = filtered.features.copy()
                new_features["label"] = ClassLabel(names=local_label_names)
                return filtered.cast(new_features)

            raw = DatasetDict({k: filter_and_remap(v) for k, v in full_dataset.items()})
        else:
            raise

    if "validation" in raw:
        return raw["validation"]
    if "test" in raw:
        return raw["test"]

    # Replicate train_classifier.py stratified splitting
    split1 = raw["train"].train_test_split(
        test_size=val_size + test_size, seed=seed, stratify_by_column="label"
    )
    split2 = split1["test"].train_test_split(
        test_size=test_size / (val_size + test_size), seed=seed, stratify_by_column="label"
    )
    return split2["train"]


# -- Inference sweep -----------------------------------------------------------


def _collect_results(classifier: MonumentClassifier, val_split) -> dict:
    """Run the classifier on every validation image and record entropy, confidence, correctness."""
    label_names = val_split.features["label"].names
    n = len(val_split)

    entropies    = np.empty(n, dtype=np.float32)
    confidences  = np.empty(n, dtype=np.float32)
    correct      = np.empty(n, dtype=bool)

    print(f"Running inference on {n} validation images...")
    for i, example in enumerate(val_split):
        if i % 50 == 0:
            print(f"  [{i + 1:>{len(str(n))}}/{n}]", end="\r", flush=True)

        from PIL import Image as PILImage
        img = example["image"]
        if not hasattr(img, "convert"):
            img = PILImage.fromarray(img)

        result = classifier.predict(img.convert("RGB"))
        true_label = label_names[example["label"]]
        top_pred   = max(result.probabilities, key=result.probabilities.get)

        entropies[i]   = result.entropy
        confidences[i] = result.confidence
        correct[i]     = top_pred == true_label

    print(f"  [{n}/{n}] done.       ")
    return {"entropies": entropies, "confidences": confidences, "correct": correct}


# -- Threshold suggestion ------------------------------------------------------


def _suggest_entropy_threshold(entropies: np.ndarray, recall_target: float) -> float:
    """
    Largest entropy value such that `recall_target` fraction of validation images fall below it.
    Equivalent to the recall_target-th percentile of the entropy distribution.
    """
    return float(np.quantile(entropies, recall_target))


def _suggest_confidence_threshold(confidences: np.ndarray, recall_target: float) -> float:
    """
    Smallest confidence value such that `recall_target` fraction of validation images are above it.
    Equivalent to the (1-recall_target)-th percentile of the confidence distribution.
    """
    return float(np.quantile(confidences, 1.0 - recall_target))


# -- Plotting ------------------------------------------------------------------


def _plot_distributions(
    entropies: np.ndarray,
    confidences: np.ndarray,
    entropy_thresh: float,
    confidence_thresh: float,
    auto_entropy_thresh: float,
    out_dir: Path,
) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")          # headless-safe backend
        import matplotlib.pyplot as plt
    except ImportError:
        print("[Warning] matplotlib not installed; skipping plot.")
        print("          Install with:  pip install matplotlib")
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(
        "OOD Threshold Calibration -- In-Distribution Validation Images",
        fontsize=13, fontweight="bold",
    )

    # -- Entropy panel --
    ax = axes[0]
    ax.hist(entropies, bins=40, color="#4A90D9", edgecolor="white", alpha=0.85,
            label="Validation images")
    ax.axvline(entropy_thresh,      color="#E74C3C", linewidth=2,   linestyle="--",
               label=f"Suggested  ({entropy_thresh:.3f})")
    ax.axvline(auto_entropy_thresh, color="#F39C12", linewidth=1.5, linestyle=":",
               label=f"Auto 0.5*ln(N)  ({auto_entropy_thresh:.3f})")
    ax.set_xlabel("Shannon Entropy H(p)  [nats]", fontsize=11)
    ax.set_ylabel("Count", fontsize=11)
    ax.set_title("Entropy Distribution", fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)

    # -- Confidence panel --
    ax = axes[1]
    ax.hist(confidences, bins=40, color="#27AE60", edgecolor="white", alpha=0.85,
            label="Validation images")
    ax.axvline(confidence_thresh, color="#E74C3C", linewidth=2, linestyle="--",
               label=f"Suggested  ({confidence_thresh:.3f})")
    ax.set_xlabel("max Softmax Probability", fontsize=11)
    ax.set_ylabel("Count", fontsize=11)
    ax.set_title("Confidence Distribution", fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    plot_path = out_dir / "calibration_plot.png"
    plt.savefig(str(plot_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Plot saved to       : {plot_path}")


# -- Main ----------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="calibrate_thresholds.py",
        description="Calibrate entropy/confidence OOD thresholds from the HF validation split.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "checkpoint_dir",
        help="Path to the onnx_export/<monument-model>/ directory.",
    )
    parser.add_argument(
        "monument_name",
        help="Monument name as defined in config.yaml (e.g. sagrada_familia).",
    )
    parser.add_argument(
        "--recall-target", type=float, default=0.95, metavar="R",
        help="Minimum fraction of ID validation images to keep (0.0 - 1.0).",
    )
    parser.add_argument(
        "--output-dir", default=None, metavar="PATH",
        help="Where to save calibration_plot.png and calibration_results.json. "
             "Default: <checkpoint_dir>/calibration/",
    )
    parser.add_argument(
        "--config", default=CONFIG_PATH, metavar="PATH",
        help="Path to config.yaml.",
    )
    args = parser.parse_args()

    if not 0.0 < args.recall_target < 1.0:
        parser.error("--recall-target must be strictly between 0 and 1.")

    cfg      = _load_config(args.config)
    data_dir = _monument_data_dir(cfg, args.monument_name, args.config)
    out_dir  = Path(args.output_dir) if args.output_dir else Path(args.checkpoint_dir) / "calibration"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load classifier WITHOUT any threshold override -- we are calibrating
    classifier = MonumentClassifier(checkpoint_dir=args.checkpoint_dir, config_path=args.config)
    auto_entropy_thresh = 0.5 * math.log(classifier.num_classes)

    print(f"\nMonument            : {args.monument_name}")
    print(f"Checkpoint          : {args.checkpoint_dir}")
    print(f"Num classes (N)     : {classifier.num_classes}")
    print(f"Auto entropy thresh : 0.5 * ln({classifier.num_classes}) = {auto_entropy_thresh:.4f}")
    print(f"Recall target       : {args.recall_target * 100:.1f}%")
    print(f"Output dir          : {out_dir}")

    # Load HF validation split
    val_split = _load_val_split(cfg, args.monument_name, data_dir)
    print(f"Validation split size: {len(val_split)} images\n")

    # Run inference sweep
    results     = _collect_results(classifier, val_split)
    entropies   = results["entropies"]
    confidences = results["confidences"]

    # Suggest thresholds
    entropy_thresh    = _suggest_entropy_threshold(entropies,   args.recall_target)
    confidence_thresh = _suggest_confidence_threshold(confidences, args.recall_target)

    # Compute recall at suggested thresholds
    recall_entropy    = float((entropies   <= entropy_thresh).mean())
    recall_confidence = float((confidences >= confidence_thresh).mean())
    recall_combined   = float(((entropies  <= entropy_thresh) & (confidences >= confidence_thresh)).mean())
    accuracy          = float(results["correct"].mean())

    w = 58
    print(f"\n{'=' * w}")
    print(f"  {'CALIBRATION RESULTS':^{w - 4}}")
    print(f"{'=' * w}")
    print(f"  {'Metric':<40} {'Value':>12}")
    print(f"  {'-' * (w - 4)}")
    print(f"  {'Validation images':<40} {len(entropies):>12}")
    print(f"  {'Top-1 accuracy (no OOD gate)':<40} {accuracy:>11.1%}")
    print(f"  {'Mean entropy':<40} {entropies.mean():>12.4f}")
    print(f"  {'Mean confidence':<40} {confidences.mean():>12.4f}")
    print(f"  {'-' * (w - 4)}")
    print(f"  {'Suggested entropy_threshold':<40} {entropy_thresh:>12.4f}")
    print(f"  {'Suggested confidence_threshold':<40} {confidence_thresh:>12.4f}")
    print(f"  {'Auto entropy  0.5*ln(N)':<40} {auto_entropy_thresh:>12.4f}")
    print(f"  {'-' * (w - 4)}")
    print(f"  {'ID recall -- entropy gate only':<40} {recall_entropy:>11.1%}")
    print(f"  {'ID recall -- confidence gate only':<40} {recall_confidence:>11.1%}")
    print(f"  {'ID recall -- combined gates':<40} {recall_combined:>11.1%}")
    print(f"{'=' * w}\n")

    # Config.yaml snippet
    print("Paste this under the matching monument or model entry in config.yaml:")
    print(f"""
      inference:
        entropy_threshold: {entropy_thresh:.4f}
        confidence_threshold: {confidence_thresh:.4f}
""")

    # Save JSON summary
    summary = {
        "monument": args.monument_name,
        "checkpoint_dir": str(args.checkpoint_dir),
        "num_classes": classifier.num_classes,
        "validation_images": int(len(entropies)),
        "recall_target": args.recall_target,
        "top1_accuracy": accuracy,
        "suggested_entropy_threshold": entropy_thresh,
        "suggested_confidence_threshold": confidence_thresh,
        "auto_entropy_threshold": auto_entropy_thresh,
        "id_recall_entropy_gate": recall_entropy,
        "id_recall_confidence_gate": recall_confidence,
        "id_recall_combined_gates": recall_combined,
        "entropy_stats": {
            "mean":  float(entropies.mean()),
            "std":   float(entropies.std()),
            "p50":   float(np.percentile(entropies, 50)),
            "p95":   float(np.percentile(entropies, 95)),
            "p99":   float(np.percentile(entropies, 99)),
        },
        "confidence_stats": {
            "mean":  float(confidences.mean()),
            "std":   float(confidences.std()),
            "p05":   float(np.percentile(confidences,  5)),
            "p50":   float(np.percentile(confidences, 50)),
        },
    }
    json_path = out_dir / "calibration_results.json"
    with open(json_path, "w") as fh:
        json.dump(summary, fh, indent=2)
    print(f"Results saved to    : {json_path}")

    # Plot
    _plot_distributions(
        entropies, confidences,
        entropy_thresh, confidence_thresh, auto_entropy_thresh,
        out_dir,
    )


if __name__ == "__main__":
    main()

