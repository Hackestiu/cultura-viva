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
    python train_classifier.py --config other_config.yaml
"""

from __future__ import annotations

import argparse
import os
import sys
from functools import lru_cache

import evaluate
import numpy as np
import torch
import wandb
from datasets import DatasetDict
from torchvision.transforms import (
    CenterCrop,
    ColorJitter,
    Compose,
    Normalize,
    RandomHorizontalFlip,
    RandomResizedCrop,
    RandomRotation,
    Resize,
    ToTensor,
)
from transformers import (
    AutoImageProcessor,
    AutoModelForImageClassification,
    Trainer,
    TrainingArguments,
)

from common import (
    CONFIG_PATH,
    DEFAULT_BATCH_SIZE,
    DEFAULT_LEARNING_RATE,
    DEFAULT_NUM_EPOCHS,
    IMAGENET_MEAN,
    IMAGENET_STD,
    get_processor_size,
    load_config,
)
from dataset import load_monument_dataset

@lru_cache(maxsize=None)
def _metrics():
    """Accuracy and macro-F1, loaded on first use (both need scikit-learn)."""
    return evaluate.load("accuracy"), evaluate.load("f1")


def make_compute_metrics(labels):
    """Returns a compute_metrics function bound to the current run's labels."""

    def compute_metrics(eval_pred) -> dict:
        accuracy_metric, f1_metric = _metrics()
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

        return {"accuracy": acc["accuracy"], "f1": f1["f1"]}

    return compute_metrics


def collate_fn(batch) -> dict:
    """Collate function to combine a list of samples into a batch."""
    pixel_values = torch.stack([item["pixel_values"] for item in batch])
    labels_tensor = torch.tensor([item["label"] for item in batch])
    return {"pixel_values": pixel_values, "labels": labels_tensor}


def build_transforms(processor) -> tuple[Compose, Compose]:
    """Training transforms (augmented) and eval transforms (deterministic).

    Augmentation applies to training only; validation and test get a plain
    resize + center crop so their metrics stay comparable across epochs.
    """
    size = get_processor_size(processor)
    normalize = Normalize(
        mean=getattr(processor, "image_mean", IMAGENET_MEAN),
        std=getattr(processor, "image_std", IMAGENET_STD),
    )

    train_transforms = Compose([
        RandomResizedCrop(size, scale=(0.7, 1.0)),
        RandomHorizontalFlip(p=0.5),
        RandomRotation(degrees=15),
        ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2, hue=0.05),
        ToTensor(),
        normalize,
    ])
    eval_transforms = Compose([
        Resize(size),
        CenterCrop(size),
        ToTensor(),
        normalize,
    ])
    return train_transforms, eval_transforms


def train_one(monument_cfg: dict, model_cfg: dict, dataset: DatasetDict, cfg: dict) -> None:
    """Fine-tunes one (monument, model) combination with a fresh head."""
    monument_name = monument_cfg["name"]
    model_name = model_cfg["name"]
    vision_model_name = model_cfg["vision_model_name"]
    defaults = cfg.get("training_defaults", {})

    run_id = f"{monument_name}-{model_name}"
    output_dir = model_cfg.get("output_dir") or monument_cfg.get("output_dir")
    output_dir = (
        output_dir.format(monument=monument_name, model=model_name)
        if output_dir
        else f"./outputs/{run_id}-finetuned"
    )

    run_name = model_cfg.get("run_name")
    run_name = run_name.format(monument=monument_name, model=model_name) if run_name else run_id

    num_epochs = model_cfg.get("num_epochs", defaults.get("num_epochs", DEFAULT_NUM_EPOCHS))
    batch_size = model_cfg.get("batch_size", defaults.get("batch_size", DEFAULT_BATCH_SIZE))
    learning_rate = float(
        model_cfg.get("learning_rate", defaults.get("learning_rate", DEFAULT_LEARNING_RATE))
    )

    # Element classes are whatever this monument's subfolders contained.
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

    processor = AutoImageProcessor.from_pretrained(vision_model_name)
    train_transforms, eval_transforms = build_transforms(processor)

    def apply(transforms):
        def _apply(examples) -> dict:
            examples["pixel_values"] = [transforms(img.convert("RGB")) for img in examples["image"]]
            return examples
        return _apply

    dataset["train"].set_transform(apply(train_transforms))
    dataset["validation"].set_transform(apply(eval_transforms))
    dataset["test"].set_transform(apply(eval_transforms))

    # Fresh classification head sized to this monument's class count.
    model = AutoModelForImageClassification.from_pretrained(
        vision_model_name,
        num_labels=num_classes,
        id2label=id2label,
        label2id=label2id,
        ignore_mismatched_sizes=True,
    )

    wandb.init(
        project=cfg.get("wandb", {}).get("project", "cultura-viva"),
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

    test_metrics = trainer.evaluate(eval_dataset=dataset["test"], metric_key_prefix="test")
    print(f"\nTest Metrics for {run_id}: {test_metrics}")

    os.makedirs(output_dir, exist_ok=True)
    trainer.save_model(output_dir)
    processor.save_pretrained(output_dir)
    print(f"Saved checkpoint and processor to: {output_dir}\n")

    wandb.finish()


def _parse_filters(items) -> set | None:
    """Flattens repeated and comma-separated --monuments/--models values."""
    if not items:
        return None
    names = {piece.strip() for item in items for piece in str(item).split(",")}
    return {name for name in names if name} or None


def _select(entries: list, filters: set | None, kind: str) -> list:
    """Entries matching the filter, or all of them when no filter was given."""
    selected = [e for e in entries if not filters or e["name"] in filters]
    if not selected:
        available = [e["name"] for e in entries]
        sys.exit(f"[Error] No {kind} matched {sorted(filters)}. Available {kind}: {available}")
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description="Train monument classifiers.")
    parser.add_argument(
        "--config", default=CONFIG_PATH,
        help="Path to the config.yaml file (default: config.yaml or $CONFIG_PATH)",
    )
    parser.add_argument(
        "--monuments", "-m", nargs="+",
        help="Specific monument name(s) to train on (e.g. --monuments sagrada_familia casa_batllo)",
    )
    parser.add_argument(
        "--models", "-M", nargs="+",
        help="Specific model name(s) to train (e.g. --models vit mobilenetv2)",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    monuments = _select(cfg["monuments"], _parse_filters(args.monuments), "monuments")
    models = _select(cfg["models"], _parse_filters(args.models), "models")

    print("\n[Run Plan]")
    print(f"  Monuments ({len(monuments)}): {[m['name'] for m in monuments]}")
    print(f"  Models ({len(models)}): {[m['name'] for m in models]}\n")

    for monument_cfg in monuments:
        # Load + split this monument's dataset ONCE, reuse across all models
        monument_dataset = load_monument_dataset(cfg, monument_cfg["name"], monument_cfg["data_dir"])
        for model_cfg in models:
            train_one(monument_cfg, model_cfg, monument_dataset, cfg)

    print("\nAll (monument, model) classifiers finished training successfully.")


if __name__ == "__main__":
    main()
