"""
Generic image-classification fine-tuning for the Gaudi dataset using
Hugging Face `transformers`.

A single config.yaml drives everything:
  - `monuments:` lists each monument (its own HF data_dir, e.g.
    culturaviva/gaudi_image/sagrada_familia). Each monument has its own set
    of "element" classes, auto-detected from its own subfolders, and its own
    train/val/test split.
  - `models:` lists each vision backbone to train (MobileNetV2, ResNet, ViT,
    EfficientNet, ConvNeXt, Swin, or any checkpoint supported by
    AutoModelForImageClassification).

This script trains every (monument, model) combination as a completely
separate run -- separate dataset, separate model instance, separate output
directory, separate W&B run. With 4 monuments and N models that's 4xN
trained versions from a single `python train_classifier.py`.

Usage:
    export HF_TOKEN=hf_xxxx
    python train_classifier.py
    CONFIG_PATH=other_config.yaml python train_classifier.py
"""

import os
import numpy as np
import torch
import wandb
import evaluate
import yaml
from datasets import DatasetDict, load_dataset
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
HF_TOKEN = os.environ["HF_TOKEN"]  # do export HF_TOKEN=hf_xxxx before running this script
VAL_SIZE = config["dataset"]["val_size"]
TEST_SIZE = config["dataset"]["test_size"]
SEED = config["dataset"]["seed"]  # for reproducibility

TRAINING_DEFAULTS = config.get("training_defaults", {})
WANDB_PROJECT = config["wandb"]["project"]

MONUMENT_CONFIGS = config["monuments"]
MODEL_CONFIGS = config["models"]

accuracy_metric = evaluate.load("accuracy")
f1_metric = evaluate.load("f1")


def load_monument_dataset(data_dir: str) -> DatasetDict:
    """Loads and splits one monument's dataset (train/validation/test)."""
    raw_dataset = load_dataset(HF_DATASET_NAME, data_dir=data_dir, token=HF_TOKEN)

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
    if "shortest_edge" in processor.size:
        return processor.size["shortest_edge"]
    elif "height" in processor.size:
        return processor.size["height"]
    return list(processor.size.values())[0]


def train_one(monument_cfg: dict, model_cfg: dict, dataset: DatasetDict) -> None:
    """Fine-tunes one (monument, model) combination."""
    monument_name = monument_cfg["name"]
    model_name = model_cfg["name"]
    vision_model_name = model_cfg["vision_model_name"]

    run_id = f"{monument_name}-{model_name}"
    output_dir = model_cfg.get("output_dir") or monument_cfg.get("output_dir")
    output_dir = output_dir or f"./outputs/{run_id}-finetuned"
    run_name = model_cfg.get("run_name") or run_id

    num_epochs = model_cfg.get("num_epochs", TRAINING_DEFAULTS.get("num_epochs"))
    batch_size = model_cfg.get("batch_size", TRAINING_DEFAULTS.get("batch_size"))
    learning_rate = float(model_cfg.get("learning_rate", TRAINING_DEFAULTS.get("learning_rate")))

    labels = dataset["train"].features["label"].names
    id2label = {i: name for i, name in enumerate(labels)}
    label2id = {name: i for i, name in enumerate(labels)}
    num_classes = len(labels)

    print("\n" + "=" * 70)
    print(f"Monument: {monument_name} | Model: {model_name} ({vision_model_name})")
    print(f"Classes ({num_classes}): {labels}")
    print(f"Train: {len(dataset['train'])} | Val: {len(dataset['validation'])} | Test: {len(dataset['test'])}")
    print("=" * 70)

    # process images + data augmentation, specific to this backbone's processor
    processor = AutoImageProcessor.from_pretrained(vision_model_name)
    image_mean = processor.image_mean
    image_std = processor.image_std
    size = get_processor_size(processor)
    normalize = Normalize(mean=image_mean, std=image_std)

    # augmentation ONLY for training: resize + crop + flip + rotation + color jitter + normalization
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

    # validation without augmentation: resize + center crop + normalization
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

    # load the pre-trained vision backbone for image classification.
    # AutoModelForImageClassification resolves the correct model class
    # based on vision_model_name, so any HF checkpoint can be listed in config.yaml.
    model = AutoModelForImageClassification.from_pretrained(
        vision_model_name,
        num_labels=num_classes,
        id2label=id2label,
        label2id=label2id,
        ignore_mismatched_sizes=True,
    )

    wandb.init(
        project=WANDB_PROJECT,
        name=run_name,
        reinit=True,
        config={
            "monument": monument_name,
            "model": vision_model_name,
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

    os.makedirs(output_dir, exist_ok=True)
    trainer.save_model(output_dir)
    processor.save_pretrained(output_dir)
    print(f"\nSaved '{run_id}' to: {output_dir}")

    wandb.finish()


if __name__ == "__main__":
    for monument_cfg in MONUMENT_CONFIGS:
        # load + split this monument's dataset ONCE, reuse it for every model
        monument_dataset = load_monument_dataset(monument_cfg["data_dir"])

        for model_cfg in MODEL_CONFIGS:
            train_one(monument_cfg, model_cfg, monument_dataset)

    print("\nAll (monument, model) versions finished training.")