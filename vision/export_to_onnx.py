"""
Convert a fine-tuned Hugging Face image classifier (the checkpoint folder
produced by train_classifier.py, e.g. ./outputs/sagrada_familia-vit-finetuned)
into a single ONNX file + a labels.json, ready to copy onto the Arduino Uno Q.

Run this on your TRAINING machine (the one with the checkpoint), not on the
Uno Q itself.

Usage:
    python export_to_onnx.py /path/to/checkpoint_dir /path/to/output_dir

Example:
    python export_to_onnx.py ./outputs/sagrada_familia-vit-finetuned ./onnx_export/sagrada_familia-vit
"""

import json
import os
import sys

import torch
from transformers import AutoImageProcessor, AutoModelForImageClassification

from common import IMAGENET_MEAN, IMAGENET_STD, get_processor_size


def export(checkpoint_dir: str, output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)

    print(f"Loading model + processor from: {checkpoint_dir}")
    model = AutoModelForImageClassification.from_pretrained(checkpoint_dir)
    processor = AutoImageProcessor.from_pretrained(checkpoint_dir)
    model.eval()

    # Same resolution the model was trained at, resolved the same way
    size = get_processor_size(processor)
    image_mean = getattr(processor, "image_mean", IMAGENET_MEAN)
    image_std = getattr(processor, "image_std", IMAGENET_STD)

    dummy_input = torch.randn(1, 3, size, size)

    onnx_path = os.path.join(output_dir, "model.onnx")
    print(f"Exporting to ONNX at: {onnx_path}")
    torch.onnx.export(
        model,
        dummy_input,
        onnx_path,
        input_names=["pixel_values"],
        output_names=["logits"],
        dynamic_axes={"pixel_values": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17,
        dynamo=False,  # use the legacy exporter; avoids needing the onnxscript package
    )

    # Save everything the Uno Q inference script needs to preprocess images
    # and turn predicted indices back into monument-element names.
    meta = {
        "id2label": {str(i): label for i, label in model.config.id2label.items()},
        "num_classes": model.config.num_labels,
        "image_size": size,
        "image_mean": image_mean,
        "image_std": image_std,
    }
    meta_path = os.path.join(output_dir, "labels.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"Saved label/preprocessing metadata to: {meta_path}")
    print("\nDone. Copy these two files to the Uno Q:")
    print(f"  {onnx_path}")
    print(f"  {meta_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python export_to_onnx.py <checkpoint_dir> <output_dir>")
        sys.exit(1)
    export(sys.argv[1], sys.argv[2])
