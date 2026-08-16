"""
MobileNetV2 fine-tuning for image classification of a Gaudi dataset
by using Hugging Face

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
    MobileNetV2ForImageClassification,
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
HF_DATA_DIR = config["dataset"]["data_dir"]
HF_TOKEN = os.environ["HF_TOKEN"]  # do export HF_TOKEN=hf_xxxx before running this script
VISION_MODEL_NAME = config["model"]["vision_model_name"]
OUTPUT_DIR = config["model"]["output_dir"]
NUM_EPOCHS = config["training"]["num_epochs"]
BATCH_SIZE = config["training"]["batch_size"]
LEARNING_RATE = float(config["training"]["learning_rate"])
VAL_SIZE = config["dataset"]["val_size"]
TEST_SIZE = config["dataset"]["test_size"]
SEED = config["dataset"]["seed"]  # for reproducibility

WANDB_PROJECT = config["wandb"]["project"]
WANDB_RUN_NAME = config["wandb"]["run_name"]

# load the dataset from Hugging Face

raw_dataset = load_dataset(HF_DATASET_NAME, data_dir=HF_DATA_DIR, token=HF_TOKEN)

if "test" not in raw_dataset and "validation" not in raw_dataset:
    split1 = raw_dataset["train"].train_test_split(
        test_size=VAL_SIZE + TEST_SIZE, seed=SEED, stratify_by_column="label"
    )
    train_split = split1["train"]
    val_test_pool = split1["test"]

    split2 = val_test_pool.train_test_split(
        test_size=TEST_SIZE / (VAL_SIZE + TEST_SIZE), seed=SEED, stratify_by_column="label"
    )
    dataset = DatasetDict(
        {
            "train": train_split,
            "validation": split2["train"],
            "test": split2["test"],
        }
    )
else:
    dataset = raw_dataset

# extract labels from dataset
labels = dataset["train"].features["label"].names
id2label = {i: name for i, name in enumerate(labels)}
label2id = {name: i for i, name in enumerate(labels)}
num_classes = len(labels)

print(f"Detected classes ({num_classes}): {labels}")
print(f"Train: {len(dataset['train'])} images | Val: {len(dataset['validation'])} images | Test: {len(dataset['test'])} images")

# process images + data augmentation
processor = AutoImageProcessor.from_pretrained(VISION_MODEL_NAME)

image_mean = processor.image_mean
image_std = processor.image_std
size = processor.size["shortest_edge"] if "shortest_edge" in processor.size else processor.size["height"]

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
    """Applies the training transformations to the images in the dataset."""
    examples["pixel_values"] = [
        train_transforms(img.convert("RGB")) for img in examples["image"]
    ]
    return examples


def apply_val_transforms(examples) -> dict:
    """Applies the validation transformations to the images in the dataset."""
    examples["pixel_values"] = [
        val_transforms(img.convert("RGB")) for img in examples["image"]
    ]
    return examples


dataset["train"].set_transform(apply_train_transforms)
dataset["validation"].set_transform(apply_val_transforms)
dataset["test"].set_transform(apply_val_transforms)


def collate_fn(batch) -> dict:
    """Collate function to combine a list of samples into a batch."""
    pixel_values = torch.stack([item["pixel_values"] for item in batch])
    labels_tensor = torch.tensor([item["label"] for item in batch])
    return {"pixel_values": pixel_values, "labels": labels_tensor}


# load the pre-trained MobileNetV2 model for image classification
model = MobileNetV2ForImageClassification.from_pretrained(
    VISION_MODEL_NAME,
    num_labels=num_classes,
    id2label=id2label,
    label2id=label2id,
    ignore_mismatched_sizes=True,
)

accuracy_metric = evaluate.load("accuracy")
f1_metric = evaluate.load("f1")


def compute_metrics(eval_pred) -> dict:
    """Compute accuracy and F1 score for evaluation."""
    predictions = np.argmax(eval_pred.predictions, axis=1)
    acc = accuracy_metric.compute(predictions=predictions, references=eval_pred.label_ids)
    f1 = f1_metric.compute(predictions=predictions, references=eval_pred.label_ids, average="macro")

    wandb.log({
        "confusion_matrix": wandb.plot.confusion_matrix(
            probs=None,
            y_true=eval_pred.label_ids,
            preds=predictions,
            class_names=labels
        )
    })

    return {
        "accuracy": acc["accuracy"],
        "f1": f1["f1"],
    }


wandb.init(
    project=WANDB_PROJECT,
    name=WANDB_RUN_NAME,
    config={
        "model": VISION_MODEL_NAME,
        "num_classes": num_classes,
        "classes": labels,
        "epochs": NUM_EPOCHS,
        "batch_size": BATCH_SIZE,
        "learning_rate": LEARNING_RATE,
        "train_size": len(dataset["train"]),
        "val_size": len(dataset["validation"]),
        "test_size": len(dataset["test"]),
    },
)


# training arguments for the Trainer
training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    per_device_train_batch_size=BATCH_SIZE,
    per_device_eval_batch_size=BATCH_SIZE,
    num_train_epochs=NUM_EPOCHS,
    learning_rate=LEARNING_RATE,
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
    compute_metrics=compute_metrics,
)

if __name__ == "__main__":
    trainer.train()

    # save the fine-tuned model and processor to the output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    trainer.save_model(OUTPUT_DIR)
    processor.save_pretrained(OUTPUT_DIR)
    print(f"\nFine-tuned model saved to: {OUTPUT_DIR}")

    wandb.finish()
