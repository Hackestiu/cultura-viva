"""Config loading and image-processor helpers shared across the gaudi-vision scripts."""

from __future__ import annotations

import os

import yaml

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.yaml")

# Fallbacks used when config.yaml has no `training_defaults` block. Keep these
# in sync with the `training_defaults` block in config.yaml.
DEFAULT_NUM_EPOCHS = 8
DEFAULT_BATCH_SIZE = 16
DEFAULT_LEARNING_RATE = 2e-5

# ImageNet statistics, used when a processor does not carry its own.
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

DEFAULT_IMAGE_SIZE = 224


def load_config(config_path: str = CONFIG_PATH, missing_ok: bool = False) -> dict:
    """Load a config.yaml. With missing_ok, a missing file yields an empty dict."""
    try:
        with open(config_path) as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        if missing_ok:
            return {}
        raise


def get_processor_size(processor) -> int:
    """The square input resolution a backbone's processor expects.

    Backbones disagree on where they record it: MobileNetV2 and ConvNeXt use
    "shortest_edge", ViT and Swin use "height"/"width", so check each variant.
    """
    size = getattr(processor, "size", None)
    if isinstance(size, dict):
        for key in ("shortest_edge", "height"):
            if key in size:
                return int(size[key])
        if size:
            return int(next(iter(size.values())))
    elif isinstance(size, (int, float)):
        return int(size)
    return DEFAULT_IMAGE_SIZE


def monument_data_dir(cfg: dict, monument_name: str, config_path: str = CONFIG_PATH) -> str:
    """The HF `data_dir` subfolder configured for a monument."""
    for monument in cfg.get("monuments", []):
        if monument.get("name") == monument_name:
            return monument["data_dir"]
    available = [m["name"] for m in cfg.get("monuments", [])]
    raise ValueError(
        f"Monument '{monument_name}' not found in {config_path}. Available: {available}"
    )
