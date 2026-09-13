"""
Generic image-classification fine-tuning for the Gaudi dataset using
Hugging Face `transformers`.

A single config.yaml drives everything:
  - `monuments:` lists each monument (its own HF data_dir, e.g.
    culturaviva/image_1080/sagrada_familia). Each monument has its own set
    of "element" classes (e.g. cupula, facana_naixement, escalinata_drac),
    auto-detected from its own subfolders, and its own train/val/test split.
  - `models:` lists each vision backbone to train (MobileNetV2, ResNet, ViT,
    EfficientNet, ConvNeXt, Swin, or any checkpoint supported by
    AutoModelForImageClassification).

This script trains every (monument, model) combination as a completely
separate run -- separate dataset split, fresh vision backbone classification head,
separate output directory, and separate W&B run.

Usage:
    export HF_TOKEN=hf_xxxx
    python train_classifier.py
    python train_classifier.py --models vit --monuments sagrada_familia
    CONFIG_PATH=other_config.yaml python train_classifier.py
"""

import argparse
import os
import time
import numpy as np
import torch
import wandb
import evaluate
import yaml
import datasets
from datasets import ClassLabel, DatasetDict, load_dataset
from transformers import (
    AutoImageProcessor,
    AutoModelForImageClassification,
    TrainingArguments,
    Trainer,
)
from torchvision.transforms import (
    Compose,
    RandomResizedCrop,
    RandomHorizontalFlip,
    RandomRotation,
    ColorJitter,
    ToTensor,
    Normalize,
    Resize,
    CenterCrop,
)

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.yaml")
with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

HF_DATASET_NAME = config["dataset"]["name"]
HF_TOKEN = os.environ.get("HF_TOKEN")  # export HF_TOKEN=hf_xxxx or rely on huggingface-cli login
VAL_SIZE = config["dataset"]["val_size"]
TEST_SIZE = config["dataset"]["test_size"]
SEED = config["dataset"]["seed"]  # for reproducibility

TRAINING_DEFAULTS = config.get("training_defaults", {})
WANDB_PROJECT = config.get("wandb", {}).get("project", "cultura-viva")

MONUMENT_FILTER = os.environ.get("MONUMENT")
MODEL_FILTER = os.environ.get("MODEL")

MONUMENT_CONFIGS = [m for m in config["monuments"] if not MONUMENT_FILTER or m["name"] == MONUMENT_FILTER]
MODEL_CONFIGS = [m for m in config["models"] if not MODEL_FILTER or m["name"] == MODEL_FILTER]

accuracy_metric = evaluate.load("accuracy")
f1_metric = evaluate.load("f1")


def _is_offline_error(err_str: str) -> bool:
    """Returns True if the error indicates that the Hub couldn't be reached due to offline mode
    or that a cached version of the dataset was not found."""
    err_lower = err_str.lower()
    return (
        "couldn't find cache" in err_lower
        or "offlinemodeisenabledvalue" in err_lower
        or "offlinemodeisdenabled" in err_lower
        or "offlinemodeisen" in err_lower
        or "OfflineModeIsEnabled" in err_str  # exact-case match too
        or ("couldn't reach" in err_lower and "offline" in err_lower)
    )


def _try_load(load_kwargs: dict) -> "datasets.DatasetDict":
    """Calls load_dataset with retry logic for 429 rate limits.
    Re-raises immediately on offline / cache-miss errors so the caller can try fallbacks."""
    max_retries = 5
    backoff_factor = 30
    for attempt in range(1, max_retries + 1):
        try:
            return load_dataset(HF_DATASET_NAME, **load_kwargs)
        except Exception as e:
            err_str = str(e)
            is_rate_limit = "429" in err_str or "too many requests" in err_str.lower() or "rate limit" in err_str.lower()
            if _is_offline_error(err_str):
                # Re-raise immediately so the caller can try the fallback strategy
                raise
            if is_rate_limit and attempt < max_retries:
                wait_time = attempt * backoff_factor
                print(f"\n[Warning] Hit Hugging Face rate limit (429) on attempt {attempt}/{max_retries}.")
                print(f"Waiting {wait_time} seconds before retrying...")
                time.sleep(wait_time)
            else:
                raise


def load_monument_dataset(monument_name: str, data_dir: str) -> DatasetDict:
    """Loads and splits one monument's dataset (train/validation/test).

    Strategy:
      1. Try loading with data_dir (monument-specific subset).
      2. If offline and only the full-dataset cache exists, load the whole
         dataset and filter rows whose class label path starts with data_dir,
         then remap labels so class indices are monument-local (0-based).
    """
    base_kwargs = {}
    if HF_TOKEN:
        base_kwargs["token"] = HF_TOKEN

    is_offline = bool(os.environ.get("HF_DATASETS_OFFLINE") or os.environ.get("HF_HUB_OFFLINE"))

    # --- Attempt 1: load the per-monument subset directly ---
    try:
        raw_dataset = _try_load({**base_kwargs, "data_dir": data_dir})
    except Exception as e:
        err_str = str(e)

        if _is_offline_error(err_str):
            # --- Fallback: load full cached dataset and filter by monument ---
            print(f"\n[Info] Per-monument cache not found for '{data_dir}'.")
            print(f"[Info] Loading full cached dataset and filtering for '{monument_name}'...")
            full_dataset = _try_load({**base_kwargs})

            # The 'label' feature names encode the subfolder path.
            # We keep only rows whose label name starts with the monument's data_dir prefix.
            all_label_names = full_dataset["train"].features["label"].names

            # Find which label indices belong to this monument
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

            # Build a local label mapping: original_index -> local_index
            local_label_names = [all_label_names[i].split("/")[-1].split("\\")[-1] for i in monument_label_indices]
            old_to_new = {old: new for new, old in enumerate(monument_label_indices)}

            def filter_and_remap(split):
                filtered = split.filter(lambda ex: ex["label"] in monument_label_indices)
                filtered = filtered.map(lambda ex: {"label": old_to_new[ex["label"]]})
                new_features = filtered.features.copy()
                new_features["label"] = ClassLabel(names=local_label_names)
                return filtered.cast(new_features)

            raw_dataset = DatasetDict({k: filter_and_remap(v) for k, v in full_dataset.items()})
            print(f"[Info] Filtered to {len(monument_label_indices)} classes for '{monument_name}': {local_label_names}")
        else:
            print(f"\n[Error] Failed to load dataset: {e}")
            print("\nTip: If you already have the dataset cached locally, you can run in offline mode by setting:")
            print("  $env:HF_DATASETS_OFFLINE=1  (PowerShell)  or  export HF_DATASETS_OFFLINE=1  (Bash)")
            raise

    if "test" not in raw_dataset and "validation" not in raw_dataset:
        split1 = raw_dataset["train"].train_test_split(
            test_size=VAL_SIZE + TEST_SIZE, seed=SEED, stratify_by_column="label"
        )
        train_split = split1["train"]
        val_test_pool = split1["test"]

        split2 = val_test_pool.train_test_split(
            test_size=TEST_SIZE / (VAL_SIZE + TEST_SIZE), seed=SEED, stratify_by_column="label"
        )
        return DatasetDict(
            {
                "train": train_split,
                "validation": split2["train"],
                "test": split2["test"],
            }
        )
    return raw_dataset


def make_compute_metrics(labels):
    """Returns a compute_metrics function bound to the current run's labels."""

    def compute_metrics(eval_pred) -> dict:
        predictions = np.argmax(eval_pred.predictions, axis=1)
        acc = accuracy_metric.compute(predictions=predictions, references=eval_pred.label_ids)
        f1 = f1_metric.compute(predictions=predictions, references=eval_pred.label_ids, average="macro")

        if wandb.run is not None:
            wandb.log({
                "confusion_matrix": wandb.plot.confusion_matrix(
                    probs=None,
                    y_true=eval_pred.label_ids,
                    preds=predictions,
                    class_names=labels,
                )
            })

        return {
            "accuracy": acc["accuracy"],
            "f1": f1["f1"],
        }

    return compute_metrics


def collate_fn(batch) -> dict:
    """Collate function to combine a list of samples into a batch."""
    pixel_values = torch.stack([item["pixel_values"] for item in batch])
    labels_tensor = torch.tensor([item["label"] for item in batch])
    return {"pixel_values": pixel_values, "labels": labels_tensor}


def get_processor_size(processor) -> int:
    """Different backbones expose the target resolution under different keys
    (MobileNetV2/ConvNeXt use "shortest_edge", ViT/Swin/EfficientNet use
    "height"/"width", etc.), so check the common variants generically."""
    if hasattr(processor, "size"):
        if isinstance(processor.size, dict):
            if "shortest_edge" in processor.size:
                return processor.size["shortest_edge"]
            elif "height" in processor.size:
                return processor.size["height"]
            return list(processor.size.values())[0]
        elif isinstance(processor.size, (int, float)):
            return int(processor.size)
    return 224


def train_one(monument_cfg: dict, model_cfg: dict, dataset: DatasetDict) -> None:
    """Fine-tunes one (monument, model) combination with a fresh head."""
    monument_name = monument_cfg["name"]
    model_name = model_cfg["name"]
    vision_model_name = model_cfg["vision_model_name"]

    run_id = f"{monument_name}-{model_name}"
    output_dir = model_cfg.get("output_dir") or monument_cfg.get("output_dir")
    if output_dir:
        output_dir = output_dir.format(monument=monument_name, model=model_name)
    else:
        output_dir = f"./outputs/{run_id}-finetuned"

    run_name = model_cfg.get("run_name")
    if run_name:
        run_name = run_name.format(monument=monument_name, model=model_name)
    else:
        run_name = run_id

    num_epochs = model_cfg.get("num_epochs", TRAINING_DEFAULTS.get("num_epochs", 100))
    batch_size = model_cfg.get("batch_size", TRAINING_DEFAULTS.get("batch_size", 8))
    learning_rate = float(model_cfg.get("learning_rate", TRAINING_DEFAULTS.get("learning_rate", 3e-5)))

    # Auto-detect element classes for this monument
    labels = dataset["train"].features["label"].names
    id2label = {i: name for i, name in enumerate(labels)}
    label2id = {name: i for i, name in enumerate(labels)}
    num_classes = len(labels)

    print("\n" + "=" * 70)
    print(f"Monument: {monument_name} | Model: {model_name} ({vision_model_name})")
    print(f"Classes ({num_classes}): {labels}")
    print(f"Train: {len(dataset['train'])} | Val: {len(dataset['validation'])} | Test: {len(dataset['test'])}")
    print(f"Output Directory: {output_dir}")
    print(f"W&B Run: {run_name}")
    print("=" * 70)

    # Process images + data augmentation, specific to this backbone's processor
    processor = AutoImageProcessor.from_pretrained(vision_model_name)
    image_mean = getattr(processor, "image_mean", [0.485, 0.456, 0.406]) #standard ImageNet mean across the Red, Green, and Blue channels
    image_std = getattr(processor, "image_std", [0.229, 0.224, 0.225]) #standard ImageNet standard deviation across the Red, Green, and Blue channels
    size = get_processor_size(processor)
    normalize = Normalize(mean=image_mean, std=image_std)

    # Augmentation ONLY for training: resize + crop + flip + rotation + color jitter + normalization
    train_transforms = Compose(
        [
            RandomResizedCrop(size, scale=(0.7, 1.0)),
            RandomHorizontalFlip(p=0.5),
            RandomRotation(degrees=15),
            ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2, hue=0.05),
            ToTensor(),
            normalize,
        ]
    )

    # Validation & test without augmentation: resize + center crop + normalization
    val_transforms = Compose(
        [
            Resize(size),
            CenterCrop(size),
            ToTensor(),
            normalize,
        ]
    )

    def apply_train_transforms(examples) -> dict:
        examples["pixel_values"] = [
            train_transforms(img.convert("RGB")) for img in examples["image"]
        ]
        return examples

    def apply_val_transforms(examples) -> dict:
        examples["pixel_values"] = [
            val_transforms(img.convert("RGB")) for img in examples["image"]
        ]
        return examples

    dataset["train"].set_transform(apply_train_transforms)
    dataset["validation"].set_transform(apply_val_transforms)
    dataset["test"].set_transform(apply_val_transforms)

    # Instantiate fresh vision backbone head with num_labels=len(monument_classes)
    model = AutoModelForImageClassification.from_pretrained(
        vision_model_name,
        num_labels=num_classes,
        id2label=id2label,
        label2id=label2id,
        ignore_mismatched_sizes=True,
    )

    # Initialize separate W&B run for this monument-model combination
    wandb.init(
        project=WANDB_PROJECT,
        name=run_name,
        reinit=True,
        config={
            "monument": monument_name,
            "model_name": model_name,
            "vision_backbone": vision_model_name,
            "num_classes": num_classes,
            "classes": labels,
            "epochs": num_epochs,
            "batch_size": batch_size,
            "learning_rate": learning_rate,
            "train_size": len(dataset["train"]),
            "val_size": len(dataset["validation"]),
            "test_size": len(dataset["test"]),
        },
    )

    training_args = TrainingArguments(
        output_dir=output_dir,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        num_train_epochs=num_epochs,
        learning_rate=learning_rate,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        logging_steps=5,
        remove_unused_columns=False,  # necessary because we use set_transform with "image"
        push_to_hub=False,
        report_to="wandb",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset["train"],
        eval_dataset=dataset["validation"],
        data_collator=collate_fn,
        compute_metrics=make_compute_metrics(labels),
    )

    trainer.train()

    # Evaluate on test set
    test_metrics = trainer.evaluate(eval_dataset=dataset["test"], metric_key_prefix="test")
    print(f"\nTest Metrics for {run_id}: {test_metrics}")

    os.makedirs(output_dir, exist_ok=True)
    trainer.save_model(output_dir)
    processor.save_pretrained(output_dir)
    print(f"Saved checkpoint and processor to: {output_dir}\n")

    wandb.finish()


def _normalize_filter_args(items):
    """Normalizes a list of filter strings which may contain comma-separated values."""
    if not items:
        return None
    res = set()
    for item in items:
        for piece in str(item).split(","):
            cleaned = piece.strip()
            if cleaned:
                res.add(cleaned)
    return res


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train monument classifiers.")
    parser.add_argument(
        "--config",
        type=str,
        default=CONFIG_PATH,
        help="Path to the config.yaml file (default: config.yaml or $CONFIG_PATH)",
    )
    parser.add_argument(
        "--monuments",
        "-m",
        nargs="+",
        help="Specific monument name(s) to train on (e.g. --monuments sagrada_familia casa_batllo)",
    )
    parser.add_argument(
        "--models",
        "-M",
        nargs="+",
        help="Specific model name(s) to train (e.g. --models vit mobilenetv2)",
    )
    args = parser.parse_args()

    # If --config is passed and differs from default CONFIG_PATH, reload config
    if args.config != CONFIG_PATH:
        with open(args.config) as f:
            config = yaml.safe_load(f)
        HF_DATASET_NAME = config["dataset"]["name"]
        VAL_SIZE = config["dataset"]["val_size"]
        TEST_SIZE = config["dataset"]["test_size"]
        SEED = config["dataset"]["seed"]
        TRAINING_DEFAULTS = config.get("training_defaults", {})
        WANDB_PROJECT = config.get("wandb", {}).get("project", "cultura-viva")

    monument_filters = _normalize_filter_args(args.monuments) or (
        _normalize_filter_args([MONUMENT_FILTER]) if MONUMENT_FILTER else None
    )
    model_filters = _normalize_filter_args(args.models) or (
        _normalize_filter_args([MODEL_FILTER]) if MODEL_FILTER else None
    )

    monuments_to_run = [
        m for m in config["monuments"]
        if not monument_filters or m["name"] in monument_filters
    ]
    models_to_run = [
        m for m in config["models"]
        if not model_filters or m["name"] in model_filters
    ]

    if not monuments_to_run:
        available = [m["name"] for m in config.get("monuments", [])]
        print(f"[Error] No monuments matched filter '{args.monuments}'. Available monuments: {available}")
        exit(1)

    if not models_to_run:
        available = [m["name"] for m in config.get("models", [])]
        print(f"[Error] No models matched filter '{args.models}'. Available models: {available}")
        exit(1)

    print(f"\n[Run Plan]")
    print(f"  Monuments ({len(monuments_to_run)}): {[m['name'] for m in monuments_to_run]}")
    print(f"  Models ({len(models_to_run)}): {[m['name'] for m in models_to_run]}\n")

    for monument_cfg in monuments_to_run:
        # Load + split this monument's dataset ONCE, reuse across all models
        monument_dataset = load_monument_dataset(monument_cfg["name"], monument_cfg["data_dir"])

        for model_cfg in models_to_run:
            train_one(monument_cfg, model_cfg, monument_dataset)

    print("\nAll (monument, model) classifiers finished training successfully.")